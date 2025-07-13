import os
import ast
import jks
import jwt
import sys
import copy
import json
import time
import boto3
import random
import requests
import textwrap
import cryptography
import lxml.etree as ET
from Crypto.Cipher import AES
from Crypto.PublicKey import RSA 
from base64 import b64encode, b64decode

"""
------------------------------------------------------------------------------------------------------------
----------------------------------- Mule Application Automated Test Tool -----------------------------------
------------------------------------------------------------------------------------------------------------
- Version:   1.0
- Developer: Josh Smith
- Contact:   josh.smith@integration.works
-
- Runs on Python 3.11 or later, developed on Python 3.11
- Python must be on PATH
- 
- This is python script to automate testing of Mule Applications. 
- Config JSON files are located in the /config/ directory. 
-
- View the README for details on installation and usage
------------------------------------------------------------------------------------------------------------
"""

def encrypt_string(secureKey, nonce, data):
    '''Encrypt and base64 encode strings for the creds.json file, using an AES compliant secureKey'''
    cipher = AES.new(secureKey, AES.MODE_EAX, nonce = nonce)
    ciphertext, tag = cipher.encrypt_and_digest(data.encode())
    return b64encode(ciphertext).decode()

def debug_test(testParams, testType):
    '''Enables the surfacing of the test request information to validate the test is being executed correctly'''
    integrationId = testParams['integrationId']
    testId = testParams['testId']
    payload = testParams['payload']
    lineBreak = ('-' * 60)
    print(lineBreak)
    if testType.lower() == 'http':
        method = testParams['method']
        host = testParams['host']
        endpoint = testParams['endpoint']
        headers = testParams['headers']
        queryParams = testParams['queryParams']
        print("|  DEBUG  \n|  Integration: {0} \n|  TestId: {1} \n|  Http method: {2} \n|  Request URL: {3}{4} \n|  Headers: {5} \n|  QueryParams: {6} \n|  Body: {7}".format(integrationId, testId, method, host, endpoint, headers, queryParams, payload))
    elif testType.lower() == 'kinesis':
        streamName = testParams['streamName']
        print("|  DEBUG  \n|  Integration: {0} \n|  TestId: {1} \n|  StreamName: {2} \n|  Body: {3}".format(integrationId, testId, streamName, payload))
    elif testType.lower() == 'salesforce':
        eventName = testParams['eventName']
        print("|  DEBUG  \n|  Integration: {0} \n|  TestId: {1} \n|  EventName: {2} \n|  Body: {3}".format(integrationId, testId, eventName, payload))
    else:
        print("|  DEBUGGER ERROR: Test Type {0} not found".format(testType))
    print(lineBreak)

def validate_args(args):
    '''Validate the arguments received when calling this script, abort if invalid args found'''
    # Enum of environment values
    environments = ['local', 'dev', 'qa', 'test-1']

    # Read CLI arguments into variables and validate length
    # if len(args) == 1: # Default values for tool dev, remove once done
    #     appName = 'cb-customer-billing'
    #     integrationId = 'none'
    #     env = 'dev'
    #     secureKey = open('config/secureKey.txt', 'r').read().encode() # This file is kept out of git 
    #     verboseResponses = False
    if len(args) in range(4, 7):
        appName = args[1]
        integrationId = args[2]
        env = args[3]
        secureKey = open('config/secureKey.txt', 'r').read().encode() # This file is kept out of git
        verboseResponses = args[4].lower() == 'true' if len(args) in [5, 6] else False
        debug = args[5].lower() == 'true' if len(args) == 6 else False
    else:
        print('Invalid length of system arguments: aborting')
        return 0
    
    # Validate CLI arguement values
    if env not in environments:
        print('Invalid environment: {0}. Value must be one of: {1}'.format(env, environments))
        return 0
    if len(secureKey) % 32 != 0:
        print('Invalid secureKey length, must be a multiple of 32')
        return 0
    if verboseResponses not in [True, False]:
        print('verbose_responses expects True or False but got {0}'.format(verboseResponses))
        return 0   
    
    return appName, integrationId, env, secureKey, verboseResponses, debug

def get_auth_http(environment, secureKey, nonce):
    '''Gets the access token from the flex gateway by posting the client secrets to the endpoint'''
    # Variables for token request
    grant_type = 'client_credentials'
    
    # Read config file for encrypted credentials
    creds = json.load(open('config/creds.json', 'r'))[environment]['http']
    encClient_id = b64decode(creds['client_id'])
    encClient_secret = b64decode(creds['client_secret'])
    endpoint = creds['endpoint']
    scope = creds['scope']
    
    # Decrypt client_id
    cipher = AES.new(secureKey, AES.MODE_EAX, nonce = nonce)
    client_id = cipher.decrypt(encClient_id).decode()
    
    # Decrypt client_secret
    cipher = AES.new(secureKey, AES.MODE_EAX, nonce = nonce)
    client_secret = cipher.decrypt(encClient_secret).decode()
    
    # Construct token request body
    requestBody = {'grant_type': grant_type, 'client_id': client_id, 'client_secret': client_secret, 'scope': scope}
    response = requests.post(endpoint, data=requestBody, timeout = 30)
    
    return response.json()['access_token']

def get_client_kinesis(environment, secureKey, nonce):
    '''Inits a kinesis producer client for the given accessKey and secretKey'''
    # Read config file for encrypted credentials
    creds = json.load(open('config/creds.json', 'r'))[environment]['kinesis']
    encAccessKey = b64decode(creds['accessKey'])
    encSecretKey = b64decode(creds['secretKey'])
    region = creds['kinesisRegion']
    
    # Decrypt client_id
    cipher = AES.new(secureKey, AES.MODE_EAX, nonce = nonce)
    accessKey = cipher.decrypt(encAccessKey).decode()
    
    # Decrypt client_secret
    cipher = AES.new(secureKey, AES.MODE_EAX, nonce = nonce)
    secretKey = cipher.decrypt(encSecretKey).decode()
    
    # Init client
    client = boto3.client(
        'kinesis',
        aws_access_key_id=accessKey,
        aws_secret_access_key=secretKey,
        region_name=region
    )
    
    return client

def get_auth_salesforce(environment, secureKey, nonce):
    '''Retrieves the Salesforce composite API accesstoken and instance url'''
    # Read config file for encrypted credentials
    creds = json.load(open('config/creds.json', 'r'))[environment]['salesforce']
    encConsumerKey = b64decode(creds['consumerKey'])
    encStorePassword = b64decode(creds['storePassword'])
    keystore = creds['keyStore']
    certAlias = creds['certificateAlias']
    principal = creds['principal']
    endpoint = creds['tokenEndpoint']
    
    # Decrypt client_id
    cipher = AES.new(secureKey, AES.MODE_EAX, nonce = nonce)
    consumerKey = cipher.decrypt(encConsumerKey).decode()
    
    # Decrypt client_secret
    cipher = AES.new(secureKey, AES.MODE_EAX, nonce = nonce)
    storePassword = cipher.decrypt(encStorePassword).decode()
    
    # Construct encryption key, payload and excrypt
    privateKey = "-----BEGIN RSA PRIVATE KEY-----\n{0}\n-----END RSA PRIVATE KEY-----".format("\n".join(textwrap.wrap(b64encode(jks.KeyStore.load(keystore, storePassword).entries[certAlias].pkey).decode('ascii'), 64)))
    payload = {
        'iss': consumerKey,
        'exp': int(time.time()) + 300,
        'aud': endpoint,
        'sub': principal
    }
    encoded = jwt.encode(payload, privateKey, algorithm='RS256')
    response = requests.post(endpoint, data = {
    'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
    'assertion': encoded,
    })
    
    return response.json()['access_token'], response.json()['instance_url']

def get_auth_cloudhub(secureKey, nonce):
    creds = json.load(open('config/creds.json', 'r'))['cloudhub']
    encClientId = b64decode(creds['client_id'])
    encClientSecret = b64decode(creds['client_secret'])

    # Decrypt client_id
    cipher = AES.new(secureKey, AES.MODE_EAX, nonce = nonce)
    clientId = cipher.decrypt(encClientId).decode()
    
    # Decrypt client_secret
    cipher = AES.new(secureKey, AES.MODE_EAX, nonce = nonce)
    clientSecret = cipher.decrypt(encClientSecret).decode()

    headers = {"content-type": "application/x-www-form-urlencoded"}

    payload = {'client_id': clientId, 'client_secret': clientSecret, 'grant_type': 'client_credentials'}

    response = requests.post('https://anypoint.mulesoft.com/accounts/api/v2/oauth2/token', data=payload, headers=headers, timeout=30)
    accessToken = response.json()['access_token']
    if response.status_code < 400:
        return accessToken
    else:
        return 0

def get_cloudhub_app(token, environment, application, execTimes, sleepTime):
    '''Retrieves the cloudhub logfile in a given app and environment between execution time parameters'''
    # Load config and init vars
    chEnv = {}
    chApp = {}
    config = json.load(open('config/creds.json', 'r'))['cloudhub']
    orgId = config['org_id']
    headers = {"Authorization": token}
    
    print('Obtaining app information from Cloudhub')
    # Request cloudhub environments and validate response
    response = requests.get('https://anypoint.mulesoft.com/accounts/api/organizations/{0}/environments'.format(orgId), headers=headers)
    if response.status_code >= 400:
        print('ERROR: {0} received from cloudhub - {1}'.format(response.status_code, response.text))
        return 0
    environments = response.json()
    response = ''
    for env in environments['data']:
        if env['name'].upper() == environment.upper():
            chEnv = env
    
    if chEnv == {}:
        print('ERROR: Environment {0} not found in cloudhub, aborting...'.format(environment))
        return 0
    
    # Request app in cloudhub environment and validate response
    response = requests.get('https://anypoint.mulesoft.com/amc/application-manager/api/v2/organizations/{0}/environments/{1}/deployments'.format(orgId, chEnv['id']), headers=headers)
    if response.status_code >= 400:
        print('ERROR: Application {0} not available in cloudhub environment {1}'.format(application, environment))
        print(response)
        print(response.text)
        return 0
    apps = response.json()
    response = ''
    for app in apps['items']:
        if app['name'] == '{0}-{1}'.format(application, environment):
            chApp = app
    if chEnv == {}:
        print('ERROR: Application {0} not found in cloudhub environment {1}, aborting...'.format(application, environment))
        return 0

    # Requests spec id from application deployment in cloudhub
    response = requests.get('https://anypoint.mulesoft.com/amc/application-manager/api/v2/organizations/{0}/environments/{1}/deployments/{2}/specs/'.format(orgId, chEnv['id'], chApp['id']), headers=headers)
    if response.status_code >= 400:
        print('ERROR: Spec {0} for application {1} not available in cloudhub environment {2}'.format(chApp['id'], application, environment))
        print(response)
        print(response.text)
        return 0
    specId = response.json()[0]['version']
    response = ''

    # Request log file from cloudhub application, querying on execution times
    # Sleep the script to allow the logs to become available in cloudhub, and allow kinesis and salesforce operations to complete
    #########################
    print("Waiting {0} seconds for cloudhub logs to become available".format(sleepTime))
    for sec in range(sleepTime):
        print("[{0}{1}]".format("*" * (sec + 1), " " * (sleepTime - sec - 1)), end="\r")   
        time.sleep(1)
    #########################
    print()
    print("Done")
    print("Dumping Cloudhub logs to file...")
    queryParams = { "startTime": execTimes[0],  "endTime": execTimes[1],  "descending": 'false'}
    response = requests.get('https://anypoint.mulesoft.com/amc/application-manager/api/v2/organizations/{0}/environments/{1}/deployments/{2}/specs/{3}/logs/file'.format(orgId, chEnv['id'], chApp['id'], specId), headers=headers, params=queryParams)
    if response.text != '':
        print('Success - {0}'.format(response))
    else:
        print('WARNING: Cloudhub returned zero logs for time parameters - {0}'.format(response))
    
    # Write logs to file
    with open('execution.log', 'w') as file:
        file.write(response.text)
    
    #TODO: Return the chEnv[id], chApp[id] and specId values back to the main function, write new function to pull the log file using these params from the api combined with the search query params for integrationId and a timestamp
    # Alternatively: Manipulate the outputed log file to split out each correlationId value and create individual log files per-integration
    # See docs here: https://anypoint.mulesoft.com/exchange/portals/anypoint-platform/f1e97bc6-315a-4490-82a7-23abe036327a.anypoint-platform/amc-application-manager/minor/4.0/console/method/%231553/
    return

def run_test_http(application, environment, integrationId, testNum, accessToken, verboseResponses=False, debug=False):
    '''Runs the tests for a given application and integration defined in config/{application-name}.json'''
    # Init variables
    response = ''
    timeoutValue = 30
    
    # Read config for test info
    testConfig = json.load(open('tests/{0}/{1}.json'.format(application, application), 'r'))['http']
    host = testConfig['hosts'][environment]
    
    # Read integration-specific data
    endpoint = testConfig['integrations'][integrationId][testNum]['endpoint']
    method = testConfig['integrations'][integrationId][testNum]['method']
    queryParams = testConfig['integrations'][integrationId][testNum]['queryParams']
    headers = testConfig['integrations'][integrationId][testNum]['headers']
    testId = testConfig['integrations'][integrationId][testNum]['id']
    payload = testConfig['integrations'][integrationId][testNum]['payload']
    expectedResponse = testConfig['integrations'][integrationId][testNum]['expectedResponse']
    useFile = testConfig['integrations'][integrationId][testNum]['useFile'].lower() == 'true'
    
    # Add bearer token to headers if exists
    headersSansAuth = copy.deepcopy(headers)
    headers['Authorization'] = "Bearer {0}".format(accessToken)

    # Init error responses
    methodError = 'IntegrationId: {0} - ERROR: method {1} not implemented in test app'.format(integrationId, method)
    
    # Use a locally defined file, usually an XML or JSON 
    if useFile == True:
        # Parse file and execute test
        if payload[-5:] == '.json':
            dataFile = json.load(open('tests/{0}/{1}'.format(application, payload), 'r'))
            if debug == True:
                debug_test({'integrationId': integrationId, 'testId': testId, 'method': method, 'host': host, 'endpoint': endpoint, 'headers': headersSansAuth, 'queryParams': queryParams, 'payload': dataFile}, 'http')
            if method == 'post':
                response = requests.post('{0}{1}'.format(host, endpoint), json = dataFile, headers = headers, params = queryParams, timeout = timeoutValue)
            elif method == 'put':
                response = requests.put('{0}{1}'.format(host, endpoint), json = dataFile, headers = headers, params = queryParams, timeout = timeoutValue)
            else:
                print(methodError)
                return 0
        else:
            if payload[-4:] == '.xml':
                dataFile = ET.tostring(ET.parse("tests/{0}/{1}".format(application, payload)).getroot(), encoding='utf-8')
            else:
                dataFile = open("tests/{0}/{1}".format(application, payload), 'r')
            if debug == True:
                debug_test({'integrationId': integrationId, 'testId': testId, 'method': method, 'host': host, 'endpoint': endpoint, 'headers': headersSansAuth, 'queryParams': queryParams, 'payload': dataFile}, 'http')
            if method == 'post':
                response = requests.post('{0}{1}'.format(host, endpoint), data = dataFile, headers = headers, params = queryParams, timeout = timeoutValue)
            elif method == 'put':
                response = requests.put('{0}{1}'.format(host, endpoint), data = dataFile, headers = headers, params = queryParams, timeout = timeoutValue)
            else:
                print(methodError)
                return 0             
    else:
        # Execute tests for payloads defined in-line
        if debug == True:
            debug_test({'integrationId': integrationId, 'testId': testId, 'method': method, 'host': host, 'endpoint': endpoint, 'headers': headersSansAuth, 'queryParams': queryParams, 'payload': payload}, 'http')
        if method == 'get':
            response = requests.get('{0}{1}'.format(host, endpoint), headers = headers, params = queryParams, timeout = 30)
        elif method == 'post':
            response = requests.post('{0}{1}'.format(host, endpoint), json = payload, headers = headers, params = queryParams, timeout = 30)
        elif method == 'put':
            response = requests.put('{0}{1}'.format(host, endpoint), json = payload, headers = headers, params = queryParams, timeout = 30)
        else:
            print(methodError)
            return 0
    testStatus = 'PASS' if response.status_code == expectedResponse else 'FAIL expected {0}'.format(expectedResponse)
    
    # Print out response
    if verboseResponses == True:
        print('Integration: {0} - {1} - Status: {2} - {3} - Response Body: {4}'.format(integrationId, response, testStatus, testId, response.text))
    else:
        print('Integration: {0} - {1} - Status: {2} - {3}'.format(integrationId, response, testStatus, testId))
    return testStatus

def run_test_kinesis(application, environment, integrationId, testNum, client, debug=False):
    '''Sends the test payload to the kinesis stream for a given integrationId. Payloads must be in a value JSON format'''
    # Read config for test info
    testConfig = json.load(open('tests/{0}/{1}.json'.format(application, application), 'r'))['kinesis']
    
    # Read integration-specific data
    streamName = '{0}-{1}'.format(testConfig['integrations'][integrationId]['streamName'], environment)
    useFile = testConfig['integrations'][integrationId]['useFile'].lower() == 'true'
    execTime = testConfig['integrations'][integrationId]['execTime']
    testId = testConfig['integrations'][integrationId]['tests'][testNum]['id']
    payload = testConfig['integrations'][integrationId]['tests'][testNum]['payload']
    
    # Use a locally defined file, usually an XML or JSON 
    if useFile == True:
        if payload[-4:] == '.xml':
            dataFile = ET.tostring(ET.parse('tests/{0}/{1}'.format(application, payload)).getroot(), encoding='utf-8')
            response = client.put_record(StreamName = streamName, Data = dataFile, PartitionKey = 'partitionKey-{0}'.format(random.randint(0, 10)))
        elif payload[-5:] == '.json':
            dataFile = json.load(open("tests/{0}/{1}".format(application, payload), 'r'))
            response = client.put_record(StreamName = streamName, Data = json.dumps(dataFile).encode('utf-8'), PartitionKey = 'partitionKey-{0}'.format(random.randint(0, 10)))
        else:
            print('ERROR: Unknown file type for payload {0}'.format(payload))
            return 0
        # Print out response
        if debug == True:
            debug_test({'integrationId': integrationId, 'testId': testId, 'streamName': streamName, 'payload': dataFile}, 'kinesis')
        print('Integration: {0} - Kinesis message sent on Stream: {1} - {2}'.format(integrationId, streamName, testId))
    else:
        payload = json.dumps(payload).encode('utf-8')
        if debug == True:
            debug_test({'integrationId': integrationId, 'testId': testId, 'streamName': streamName, 'payload': payload}, 'kinesis')
        response = client.put_record(StreamName = streamName, Data = payload, PartitionKey = 'partitionKey-{0}'.format(random.randint(0, 10)))
        # Print out response
        print('Integration: {0} - Kinesis message sent on Stream: {1} - {2}'.format(integrationId, streamName, testId))
    return 'PASS', execTime

def run_test_salesforce(application, endpoint, integrationId, testNum, accessToken, debug=False):
    # Read config for test info
    testConfig = json.load(open('tests/{0}/{1}.json'.format(application, application), 'r'))['salesforce']
    
    # Read integration-specific data
    eventName = testConfig['integrations'][integrationId]['eventName']
    useFile = testConfig['integrations'][integrationId]['useFile'].lower() == 'true'
    execTime = testConfig['integrations'][integrationId]['execTime']
    testId = testConfig['integrations'][integrationId]['tests'][testNum]['id']
    payload = testConfig['integrations'][integrationId]['tests'][testNum]['payload']
    
    # Construct the request path and headers
    restPath = '{0}/services/data/v59.0/sobjects/{1}/'.format(endpoint, eventName)
    headers = {'Authorization': "Bearer {0}".format(accessToken)}

    # Load the payload file for the test if required
    if useFile == True:
        payload = json.load(open('tests/{0}/{1}'.format(application, payload), 'r'))
    
    # Send the request
    if debug == True:
            debug_test({'integrationId': integrationId, 'testId': testId, 'eventName': eventName, 'payload': payload}, 'salesforce')
    response = requests.post(restPath, json = payload, headers = headers, timeout = 30)

    # Print out response
    if response.status_code < 400:
        print('Integration: {0} - Salesforce Platform Event Sent to: {1} - Response: {2} - {3}'.format(integrationId, eventName, response.status_code, testId))
        return 'PASS', execTime
    else:
        print('Integration: {0} - Failed to send event to Salesforce - Response: {2} - {3} - Response Body: {4}'.format(integrationId, eventName, response.status_code, testId, response.json()))
        return 'FAIL', execTime
    

def main():
    # Variables
    nonce = b'W\xecz\xfc\x90\t\xaf6\xdb\x9c\xb0\xc0\xb2\xf1\x95' # Hardcoded nonce value for encryption of all application creds
    testPasses = 0
    testFailures = 0
    dumpCHLogs = True
    sleepTime = 15
    # Validate system arguments
    arg_validation = validate_args(sys.argv)
    if arg_validation != 0:
        appName, integrationId, env, secureKey, verboseResponses, debug = arg_validation
    else:
        return 0
    
    # Uncomment and populate these 2 lines if you want to encrypt new creds, copy and paste them into creds.json
    #print("client_id: {0}".format(encrypt_string(secureKey, nonce, "")))
    #print("client_secret: {0}".format(encrypt_string(secureKey, nonce, "")))

    # Load and Parse application config
    testConfig = json.load(open('tests/{0}/{1}.json'.format(appName, appName), 'r'))
    
    # Validate specified test exists, abort if not found
    httpIntegrations = list(testConfig['http']['integrations'].keys())
    kinesisIntegrations = list(testConfig['kinesis']['integrations'].keys())
    salesforceIntegrations = list(testConfig['salesforce']['integrations'].keys())
    allIntegrations = httpIntegrations + kinesisIntegrations + salesforceIntegrations
    if integrationId not in allIntegrations and integrationId not in ['all', 'none']:
        print('Error, no tests exist for integration: {0}'.format(integrationId))
        return 0
    
    # Run all tests
    startTime = int(time.time() * 1000)
    if integrationId == 'all':
        # Get access tokens and clients
        accessTokenHttp = get_auth_http(env, secureKey, nonce) if env != 'local' else ''
        kinesisClient = get_client_kinesis(env, secureKey, nonce)
        accessTokenSalesforce, endpointSalesforce = get_auth_salesforce(env, secureKey, nonce)
        # For each integrationId, run the associated test
        for integrationId in allIntegrations:
            if integrationId in httpIntegrations:
                for testNum in range(len(testConfig['http']['integrations'][integrationId])):
                    result = run_test_http(appName, env, integrationId, testNum, accessTokenHttp, verboseResponses, debug)
                    if result == 'PASS':
                        testPasses += 1
                    else:
                         testFailures += 1
            elif integrationId in kinesisIntegrations:
                for testNum in range(len(testConfig['kinesis']['integrations'][integrationId]['tests'])):
                    result, waitTime = run_test_kinesis(appName, env, integrationId, testNum, kinesisClient, debug)
                    if dumpCHLogs == True:
                        time.sleep(waitTime)
                    if result == 'PASS':
                        testPasses += 1
                    else:
                         testFailures += 1
            elif integrationId in salesforceIntegrations:
                for testNum in range(len(testConfig['salesforce']['integrations'][integrationId]['tests'])):
                    result, waitTime = run_test_salesforce(appName, endpointSalesforce, integrationId, testNum, accessTokenSalesforce, debug)
                    if dumpCHLogs == True:
                        time.sleep(waitTime)
                    if result == 'PASS':
                        testPasses += 1
                    else:
                         testFailures += 1
            else:
                print('Unexpected error: Test config for {0} not found'.format(integrationId))
    
    # Run http tests
    elif integrationId in httpIntegrations:
        # Get access token
        accessTokenHttp = get_auth_http(env, secureKey, nonce) if env != 'local' else ''
        # Run each test
        for testNum in range(len(testConfig['http']['integrations'][integrationId])):
            result = run_test_http(appName, env, integrationId, testNum, accessTokenHttp, verboseResponses, debug)
            if result == 'PASS':
                testPasses += 1
            else:
                testFailures += 1
    
    # Run kinesis tests
    elif integrationId in kinesisIntegrations:
        # Get kinesis client
        kinesisClient = get_client_kinesis(env, secureKey, nonce)
        # Run each test
        for testNum in range(len(testConfig['kinesis']['integrations'][integrationId]['tests'])):
            result, waitTime = run_test_kinesis(appName, env, integrationId, testNum, kinesisClient, debug)
            if dumpCHLogs == True:
                time.sleep(waitTime)
            if result == 'PASS':
                testPasses += 1
            else:
                testFailures += 1
    
    # Run salesforce tests
    elif integrationId in salesforceIntegrations:
        # Get access token
        accessTokenSalesforce, endpointSalesforce = get_auth_salesforce(env, secureKey, nonce)
        # Run each test
        for testNum in range(len(testConfig['salesforce']['integrations'][integrationId]['tests'])):
            result, waitTime = run_test_salesforce(appName, endpointSalesforce, integrationId, testNum, accessTokenSalesforce, debug)
            if dumpCHLogs == True:
                time.sleep(waitTime)
            if result == 'PASS':
                testPasses += 1
            else:
                testFailures += 1
    
    endTime = int((time.time() + 1) * 1000)
    totalTests = testFailures + testPasses
    
    if totalTests > 0:
        print()
        print("|  Test Summary \n|  Tests Run: {0} \n|  Test Passes: {1} \n|  Test Failures: {2} \n|  Test Pass Rate: {3}%".format(totalTests, testPasses, testFailures, round((testPasses/totalTests) * 100, 2)))
        print()
    
    if dumpCHLogs == True:
        cloudhubAuth = "Bearer {0}".format(get_auth_cloudhub(secureKey, nonce))
        get_cloudhub_app(cloudhubAuth, env, appName, [startTime, endTime], sleepTime)

if __name__ == '__main__':
    main()