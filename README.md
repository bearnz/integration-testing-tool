# Integration Platform Application Automated Test Tool

** This application is currently being refactored **

- Version: 1.0
- Developer: Josh Smith
- Contact: jsm137@gmail.com

Runs on Python 3.7 or later, developed on Python 3.11

This is python script to automate testing of APIs and other integrations built using a platform such as Mulesoft or Boomi.

##Installation

Windows: Ensure python is on your PATH variables

Ensure pip is installed:
- `python -m ensurepip --upgrade`

Use the pipenv module to manage dependencies:
- Windows: `pip install pipenv`
- Mac: `pip3 install pipenv`
- Install dependencies: `pipenv install -e .`

Alternatively, acquire the following pip dependencies:

Windows:

    pip install requests
    pip install pycryptodome
    pip install cryptography
    pip install boto3
    pip install PyJWT
    pip install pyjks
    pip install lxml

Mac:

    pip3 install requests
    pip3 install pycryptodome
    pip3 install cryptography
    pip3 install boto3
    pip3 install PyJWT
    pip3 install pyjks
    pip3 install lxml
If your terminal complains about authorisation errors when running the above, ensure you run your terminal as an admin and/or prepend the above commands with:
 `python -m`

**NOTE: pyjks requires some additional dependencies. If you encounter errors, information is available here:** https://pyjks.readthedocs.io/en/latest/

##Usage: 
Use the following command in the terminal when navigated to the mule-tester directory:
- Windows: `python tester.py {app_name} {integration_id} {env} {verbose_responses} {debug_requests}`
- Mac: `python3 tester.py {app_name} {integration_id} {env} {verbose_responses} {debug_requests}`

Prepend these commands with `pipenv run` if not using pip.

##Parameters:
- `{app_name}`: The name of the application you want to test. Eg: cb-customer-billing
- `{integration_id}`: The String code of the integration you are wanting to test. If you want to test all integrations, use 'all'
	- Eg: APP_DOMAIN-INT-CODE-123
- `{env}`: The enum value of the environment you want to run the tests in.
	- values: `[ 'local', 'dev', 'qa', 'uat', 'prod' ]`
- `{verbose_responses}`: a boolean value for returning the body of the response for each http test.
	- Defaults to False.
    - values: `[ "True": Each http test with return the response body JSON with the status code, "False": Each http test will only return the Http status code ]`
- `{debug_requests}`: a boolean value for surfacing the request details for each test.
	- Defaults to False.
    - values: `[ "True": Print the Test Parameters, "False": Don't surface the debug info ]`

##/config/ files:

`creds.json`: Encrypted credentials for generating the API gateway access token.

`secureKey.txt`: The value of the secureKey. This file is in .gitignore and should NOT be pushed to this repo.

Credentials are encrypted with AES using a 32-byte secure key and then base64 encoded to enable reading them from the JSON file structure. To encrypt strings when adding new tests, call the encryptString() function from within this script.

For http testing any deployed application hosted in a cloud environment, access will usually be authenticated by an api gateway. As such, an OAuth access token will need to first be acquired and included in the headers of all the http test requests.

Salesforce tests are authenticated with the same jks keystores used by the integration applications.

Kinesis tests are authenticated using the AccessKey and SecretKey key-values from AWS Secrets Manager. These keys have access to all kinesis streams in their respective accounts: Dev, QA/TEST

##/tests/ files:

 `{application-name}/{application-name}.json`: A breakdown of tests to run per integration and environment

`{application-name}/test_files/`: Any xml or other file formats that form part of the request being made that can't be parsed in JSON. Generally, if payloads are longer than a few lines it's best to put them in one of these files.

##Adding new applications:

In the /tests/ directory, create a new folder with the name of the integration application you are adding. Copy the `app-template.json` file into this folder and rename it to match the directory name.
**NOTE: the casing of the name of the file and the folder must match.**
 
Inside the `{application-name}.json` file, replace ` app-name-here` in the http hosts with the same mule application name.

##Adding new integrations for testing:

`{application-name}.json`
Add a new [integrations] element under the appropriate trigger category with the key of your integration being the integration code assigned to it.
- ie: CB3-PO-3

The value for this element can just be an empty array if you are not adding any tests immediately.
- ie: []

##Adding new tests:

Adding tests is straightforward and does not require altering the main script. 
In your `{application-name}.json` file, within the array for the integration you are adding a test for, add a new JSON element with the appropriate fields set as required for the test.
Copying and pasting a working element from another test of the same category or from another application's test config file and then changing the values to suit is encouraged.

For integrations that rely on a synchronous trigger (Salesforce Events and Kinesis Streams), a sleep function has been implemented to allow the integration to execute before the next test is run. 
The length of sleep required to allow the integration to fully execute will differ depending on how much complexity is involved. The `execTime` flag in the test config should be used to control the duration of this sleep.

You can define payloads that are well-formed JSON inline within this config file, although if the payload is more than 1-2 lines long or not JSON, it is highly recommended 
to set the `useFiles` flag in the test element to `"True"` and use an external file reference to pass the payload into the test.

To do this, copy and paste your payload into a new file in the `test_files` directory within your `{application-name}` folder. If the `test_files` directory does not exist, create it.
Name the file `{integrationId}_{testName}_{additionalInfo (optional)}.{extension}`. 

Back in `{application-name}.json` change the value of the `payload` field of the test to a string specifying the name of the test file you just created, including the test_files directory:
eg: `"payload": "test_files/{testFileName}.xml"`

When the test runs, it will pull the contents of this file into the payload of the test.

**NOTE: Http test array elements require all fields for each test, however the values can be blanked as needed (such as for blank query parameters or no additional headers).
For Kinesis and Salesforce tests, the platform event values and stream names are set once per integration. If your integration can be triggered off more than a single event or stream,
these will need to be added as distinct integrations within the test config.**

An example can be seen in cb-fault-management:

    "kinesis": {
		"integrations": {
			"CB5-CO-16-1": {
				"streamName": "int-work-order-comment",
				"useFile": "True",
				"tests": [
					{
						"id": "Smoke Test - Asset Tracker",
						"payload": "test_files/CB5-CO-16_smokeTest_AssetTracker.json"
					}
				]
			},
			"CB5-CO-16-2": {
				"streamName": "int-work-order-status",
				"useFile": "True",
				"tests": [
					{
						"id": "Smoke Test - Maintenance Order",
						"payload": "test_files/CB5-CO-16_smokeTest_MaintenanceOrder.json"
					}
				]
			}
		}
    }

CB5-CO-16 has 2 kinesis stream triggers, so each integration Id has been postpended with an additional number so that they can be triggered seperately and can each have
their own series of tests. When the main script is called, the integrationId parameter to run these tests will also have to postpend with the id of the specific integration
that needs to be tested. 

##Test Responses:

Http: If the verbose_responses flag is set to `"True"` when the test application is run, http tests will return the body of the http response in the terminal once the test has been run.
If the response code returned to the testing application matches the value specified in the test `expectedResponse` field, the testing application will log that the test was a success.

Salesforce: If the payload for a platform event is invalid then the Salesforce API will respond with an error code and message which will be surfaced in the terminal. 
This is just a validation on the schema for the payload being posted to the platform event and is not an indication on the success or failure of the application integration.
Review the runtime logs in the cloud environment to verify the success of the test.

Kinesis: If the kinesis payload is invalid or any other error is encountered, the error message will be surfaced in the terminal after the test has been run. 
If no error is returned from kinesis, this does not indicate the success or failure of the application integration execution. Review the runtime logs in the cloud environment to 
validate the outcome of the test.

##Log retrieval from Mulesoft Cloudhub

After the test suite has been run, the tool will then attempt to retrieve the logs from Cloudhub via the Cloudhub API. The tool will attempt to grab all logs from within the execution timeframe
after a wait period has elapsed to allow the logs to be retrievable.
The log file will be available in `execution.log` in the mule-tester directory. 
**NOTE: The Cloudhub API is very unreliable and retrieving the log files using it is not recommended. If the output log file is incomplete or empty, revert to reviewing the logs in Runtime Manager in Cloudhub. Logs will be truncated if they exceed the cloudhub character limit.**
**Once logs are piped into an external service, this functionality should be deprecated.**