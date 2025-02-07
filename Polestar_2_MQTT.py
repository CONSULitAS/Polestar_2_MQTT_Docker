#!/usr/bin/python3

#
# Polestar_2_MQTT.py
#
# (c) @CONSULitAS 2024
# 

# TODO: reconnect to MQTT is not stable
# TODO: openWB URL
# TODO: better error handling
# TODO: report online/offline state on MQTT (DONE)
#       report API errors to MQTT instead of throwing errors with MAX_RETRIES
# TODO: fix OPENWB_TOPIC to make it configurable in docker-compose.yml

import traceback
import os
import sys
import signal
import requests
import time
from datetime import datetime, timedelta
import pytz
import json
import paho.mqtt.client as mqtt
import urllib.parse
import base64
import hashlib

#####################################
# read ENVIRONMENT variables

# general
TZ                      =     os.getenv('TZ',                "Europe/Berlin")

# credentials for Polestar API
POLESTAR_EMAIL          =     os.getenv('POLESTAR_EMAIL')
POLESTAR_PASSWORD       =     os.getenv('POLESTAR_PASSWORD')
POLESTAR_VIN            =     os.getenv('POLESTAR_VIN')
POLESTAR_CYCLE          = int(os.getenv('POLESTAR_CYCLE',    "270")) # seconds

# MQTT broker
MQTT_BROKER             =     os.getenv("MQTT_BROKER",       "localhost") # IP or DNS name
MQTT_PORT               = int(os.getenv("MQTT_PORT",         1883))
MQTT_KEEPALIVE_INTERVAL = int(os.getenv("MQTT_KEEPALIVE",    60))
MQTT_USER               =     os.getenv("MQTT_USER",         "")
MQTT_PASSWORD           =     os.getenv("MQTT_PASSWORD",     "")
BASE_TOPIC              =     os.getenv("BASE_TOPIC",     "polestar2")
MQTT_BASE_TOPIC         =     BASE_TOPIC # TODO TMP: for backward compatibility

# openWB - optional
OPENWB_PUBLISH          =     os.getenv("OPENWB_PUBLISH", False) # default: no openWB 
OPENWB_HOST             =     os.getenv("OPENWB_HOST",    "localhost")
OPENWB_PORT             = int(os.getenv("OPENWB_PORT",    1883))
OPENWB_LP_NUM           = int(os.getenv("OPENWB_LP_NUM",  1)) # can be 1 to 8
#OPENWB_TOPIC            =     os.getenv("OPENWB_TOPIC",   "openWB/set/lp{OPENWB_LP_NUM}/%Soc")

#####################################
# global init

# internal constants
SLEEP_INTERVAL         = 0.1
MQTT_LWT_TOPIC         = f"{MQTT_BASE_TOPIC}/container/connected"
MQTT_LWT_MESSAGE_DEAD  = "offline"
MQTT_LWT_MESSAGE_ALIVE = "online"
MQTT_TIMESTAMP_TOPIC   = f"{MQTT_BASE_TOPIC}/container/last_update"

# API config
POLESTAR_BASE_URL     = "https://pc-api.polestar.com/eu-north-1"
POLESTAR_API_URL_V2   = f"{POLESTAR_BASE_URL}/mystar-v2"
POLESTAR_REDIRECT_URI = "https://www.polestar.com/sign-in-callback"
POLESTAR_ID_URI       = "https://polestarid.eu.polestar.com/as"
CLIENT_ID             = "l3oopkc_10"

# setup MQTT-Client
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
# Last Will and Testament (LWT)
client.will_set(
    topic   = MQTT_LWT_TOPIC,
    payload = MQTT_LWT_MESSAGE_DEAD,
    qos     = 1,
    retain  = True
)

# setup MQTT-Client for openWB if needed
if (OPENWB_PUBLISH):
    OPENWB_TOPIC  = "openWB/set/lp/" + str(OPENWB_LP_NUM) + "/%Soc" # TODO: use ENV string
    client_openwb = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

#####################################
# MQTT helper functions

# Backoff strategy to handle connection and reconnection attempts
def mqtt_backoff_attempt(client, method, max_retries=20, initial_delay=1, delay_max=300):
    """ 
    Implements an exponential backoff strategy for connecting or reconnecting to the MQTT broker.
    
    Parameters:
    client -- The MQTT client object
    method -- The method to call (e.g., client.connect or client.reconnect)
    max_retries -- Maximum number of attempts (default: 20)
    initial_delay -- Initial delay before retrying (default: 1 second)
    delay_max -- Maximum delay in seconds (default: 300 seconds)
    """
    client_address = "Unknown"
    delay = initial_delay  # Initial delay in seconds
    start_time = time.time()  # Record the start time of the connection/reconnection attempts

    for attempt in range(1, max_retries + 1):
        try:
            print(f"    MQTT ({client_address}): attempt {attempt} to {'connect' if method == client.connect else 'reconnect'}... (waiting {delay} seconds)")
            time.sleep(delay)  # Wait before trying to connect or reconnect
            method()  # Call the connect or reconnect method
            elapsed_time = time.time() - start_time  # Calculate elapsed time
            print(f"    MQTT ({client_address}): {'Connected' if method == client.connect else 'Reconnected'} successfully after {elapsed_time:.2f} seconds!")
            break  # If connection or reconnection is successful, exit the loop
        except Exception as e:
            print(f"    MQTT ({client_address}): attempt {attempt} failed: {e}")
            delay = min(delay * 2, delay_max)  # Double the delay but do not exceed delay_max
    else:
        elapsed_time = time.time() - start_time  # Calculate elapsed time
        wait_and_die(f"    MQTT ({client_address}): Could not {'connect' if method == client.connect else 'reconnect'} after {max_retries} attempts. Exiting.",
                     f"    MQTT ({client_address}): broker down for {elapsed_time:.0f} seconds!")

# callback for MQTT connection handling
def mqtt_on_connect(client, userdata, flags, rc, properties):
    print(f"    MQTT connected with result code '{rc}': {MQTT_LWT_TOPIC}={MQTT_LWT_MESSAGE_ALIVE}")
    # set LWT to alive status
    client.publish(MQTT_LWT_TOPIC, MQTT_LWT_MESSAGE_ALIVE, qos=1, retain=True)

# callback for MQTT disconnection handling
def mqtt_on_disconnect(client, userdata, rc, properties=None, reason_code=None):
    if rc != 0:  # rc = 0 indicates a normal disconnection
        print(f"    MQTT: disconnected unexpectedly with reason code '{reason_code}'.")
        mqtt_backoff_attempt(client, client.reconnect)

# connect to MQTT broker
def mqtt_connect():   
    # MQTT_USER and MQTT_PASSWORD have to be empty if no login to broker configured
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)   
    client.on_connect     = mqtt_on_connect
    client.on_disconnect  = mqtt_on_disconnect
    mqtt_backoff_attempt(client, lambda: client.connect(MQTT_BROKER, MQTT_PORT, MQTT_KEEPALIVE_INTERVAL))
    client.loop_start()

# connect to OpenWB built in MQTT broker
def mqtt_connect_openwb():   
    client_openwb.on_connect    = mqtt_on_connect
    client_openwb.on_disconnect = mqtt_on_disconnect
    mqtt_backoff_attempt(client_openwb, lambda: client_openwb.connect(OPENWB_HOST, OPENWB_PORT, MQTT_KEEPALIVE_INTERVAL))
    client_openwb.loop_start()

#####################################
# helper functions

def get_local_time(tz, time):
    # convert to local timezone in tz (e.g. Europe/Berlin)
    local_time = time.astimezone(pytz.timezone(tz))

    # as formated time stamp
    return local_time.strftime('%Y-%m-%d %H:%M:%S %Z%z')

def wait_and_die(message, exception):
    print(message)
    time.sleep(POLESTAR_CYCLE)  # wait POLESTAR_CYCLE seconds to reduce retry count
    raise Exception(exception)
    
    return # never!

#####################################
# login to Polestar API

# generate Code Verifiers and Code Challenge for PKCE
def generate_code_verifier_and_challenge():
    # use random value
    code_verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b'=').decode('utf-8')
    
    # Code Challenge is SHA256 hash of Code Verifier
    code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode('utf-8')).digest()).rstrip(b'=').decode('utf-8')
    
    return code_verifier, code_challenge

# get login_token, cookies and generate code_verifier, code_challenge
# (polestar-xxx-widget.js: getLoginFlowTokens())
def get_path_token():
    # new Code Verifier on every login
    code_verifier, code_challenge = generate_code_verifier_and_challenge()

    # dictionary with parameters encoded in URL
    params = urllib.parse.urlencode({
        "response_type":         "code",
        "client_id":             CLIENT_ID,
        "redirect_uri":          POLESTAR_REDIRECT_URI,
        "scope":                 "openid profile email customer:attributes",
        "state":                 "ea5aa2860f894a9287a4819dd5ada85c",
        "code_challenge":        code_challenge,
        "code_challenge_method": "S256",
    })
    url = f"{POLESTAR_ID_URI}/authorization.oauth2?{params}"
    response = requests.get(url, allow_redirects=False)
    
    if response.status_code not in [302, 303]: # = 'see other'
        wait_and_die(f"  response.status_code = {response.status_code}",
                     "get_login_tokens(): login token not successfuly received")
    
    cookies    = response.headers.get('Set-Cookie')
    cookie     = cookies.split(';')[0]
    path_token = response.headers.get('Location').split("resumePath=")[1].split("&")[0]
    print(f"  code_verifier  = {code_verifier}")
    print(f"  code_challenge = {code_challenge}")
    print(f"  cookies        = {cookies}")
    print(f"  cookie         = {cookie}")
    print(f"  path_token     = {path_token}")
    
    return path_token, cookie, code_verifier  # return code_verifier also

# login with token and credentials to get the code
def perform_login(email, password, path_token, cookie):
    url = f"{POLESTAR_ID_URI}/{path_token}/resume/as/authorization.ping?client_id={CLIENT_ID}"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Cookie": cookie
    }
    # Username and Password have to be URL encoded to avoid problems with special characters
    data = f"pf.username={urllib.parse.quote(email, safe='')}&pf.pass={urllib.parse.quote(password, safe='')}"
    
    response = requests.post(url, headers=headers, data=data, allow_redirects=False)
    
    if response.status_code not in [302, 303]:
        wait_and_die(f"  response.status_code = {response.status_code}",
                     "perform_login(): login not successful, check your credentials")

    max_age = response.headers['Strict-Transport-Security'].split("max-age=")[1].split(";")[0]
    print(    f"  max_age    = {max_age}")
    
    try:
        uid    = response.headers['Location'].split("uid=")[1].split("&")[0]
        print(f"  uid        = {uid}")
    except:
        uid = None
        print( "  uid        = NONE")
    
    try:
        code    = response.headers['Location'].split("code=")[1].split("&")[0]
        print(f"  code       = {code}")
    except:
        code = None
        print( "  code       = NONE")

    # handle missing code (e.g. accepting terms and conditions)
    if code is None and uid:
        print("   handle missing code")
        data = {"pf.submit": True, "subject": uid}
        url = f"{POLESTAR_ID_URI}/{path_token}/resume/as/authorization.ping?client_id={CLIENT_ID}"
        response = requests.post(url, headers=headers, data=data, allow_redirects=False)
        # TODO: try / except
        code    = response.headers['Location'].split("code=")[1].split("&")[0]
        print(f"   code = {code}")

    # no token received? problem with login
    if code is None:
        wait_and_die(f"  code = {code} and uid = {uid}",
                     "perform_login(): login not successfull: check your credentials at https://www.polestar.com/de/login/profile/")

    return code

# get API tokens
def get_api_token(tokenRequestCode, code_verifier):
    url = f"{POLESTAR_ID_URI}/token.oauth2"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    # dictionary for URL encoded data (requests will do the encoding)
    payload = {
        "grant_type":    "authorization_code",
        "code":          tokenRequestCode,
        "code_verifier": code_verifier,  # use code_verifier from parameters
        "client_id":     CLIENT_ID,
        "redirect_uri":  POLESTAR_REDIRECT_URI
    }
    response = requests.post(url, headers=headers, data=payload)
    
    if response.status_code != 200 or "errors" in response.json():
        wait_and_die("  response.status_code = {response.status_code}\n"
                     + json.dumps(response.json(), indent=2),
                     "get_api_token(): no API token received")
    
    api_creds     = response.json()
    access_token  = api_creds['access_token']
    refresh_token = api_creds['refresh_token']
    expires_in    = api_creds['expires_in']
    expiry_time   = datetime.now() + timedelta(seconds=expires_in)
    print( "  access_token  = " + str(access_token)[0:39] + "...")
    print(f"  refresh_token = {refresh_token}")
    print(f"  expires_in    = {expires_in} (seconds)")
    print( "  expiry_time   = " + get_local_time(TZ, expiry_time))
    
    return access_token, expiry_time, refresh_token

# login step by step
def get_token(email, password):
    print(" get_path_token()")
    path_token, cookie, code_verifier = get_path_token()  # code_verifier will be generated on each login
    print(" perform_login()")
    auth_code = perform_login(email, password, path_token, cookie)
    print(" get_api_token()")
    access_token, expiry_time, refresh_token = get_api_token(auth_code, code_verifier)  # code_verifier is needed to get token

    return access_token, expiry_time, refresh_token

# refresh the access token using the refresh token
def refresh_access_token(refresh_token):
    """
    Use the refresh token to obtain a new access token.
    This avoids the need for a complete re-login process.

    Args:
        refresh_token (str): The refresh token obtained from the initial login.

    Returns:
        tuple: A tuple containing the new access token, expiry time, and new refresh token.
    """
    url = f"{POLESTAR_ID_URI}/token.oauth2"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    payload = {
        "grant_type": "refresh_token",   # OAuth2 grant type for token refresh
        "refresh_token": refresh_token,  # use the current refresh token
        "client_id": CLIENT_ID           # client identifier for Polestar API
    }
    
    # send POST request to refresh the access token
    response = requests.post(url, headers=headers, data=payload)
    
    if response.status_code != 200 or "errors" in response.json():
        wait_and_die(f"  response.status_code = {response.status_code}\n"
                     + json.dumps(response.json(), indent=2),
                     "refresh_access_token(): No new access token received")
    
    api_creds     = response.json()
    access_token  = api_creds['access_token']   # new access token
    refresh_token = api_creds['refresh_token']  # new refresh token (may change)
    expires_in    = api_creds['expires_in']     # validity of the token in seconds
    expiry_time   = datetime.now() + timedelta(seconds=expires_in)  # calculate expiry time
    
    print( "  access_token  = " + str(access_token)[:39] + "...")
    print(f"  refresh_token = {refresh_token}")
    print(f"  expires_in    = {expires_in} seconds")
    print( "  expiry_time   = " + get_local_time(TZ, expiry_time))
    
    return access_token, expiry_time, refresh_token

def ensure_valid_token(access_token, expiry_time, refresh_token, email, password):
    """
    Ensure the access token is valid. 
    If the token is expired or close to expiry, it will be refreshed using the refresh token.
    If no refresh token is available or the refresh fails, a full login is performed.

    Args:
        access_token (str): Current access token.
        expiry_time (datetime): Expiration time of the current token.
        refresh_token (str): Current refresh token.
        email (str): User email to perform a full login if the refresh token is invalid.
        password (str): User password to perform a full login if the refresh token is invalid.

    Returns:
        tuple: Returns the updated access token, expiry time, and refresh token.
    """
    # Check if the token will expire in the next 60 seconds or if no expiry time is set
    if expiry_time is None or (datetime.now() >= expiry_time - timedelta(seconds=15)):
        if refresh_token:
            print(" refresh_access_token()")
            try:
                # Attempt to refresh the token
                access_token, expiry_time, refresh_token = refresh_access_token(refresh_token)
            except Exception as e:
                print("get_token(), refresh_access_token() failed")
                # If the refresh fails, fall back to the full login process
                access_token, expiry_time, refresh_token = get_token(email, password)
        else:
            print("get_token(), no refresh token available")
            access_token, expiry_time, refresh_token = get_token(email, password)
    return access_token, expiry_time, refresh_token

#####################################
# read data from Polestar API

# get mostly static car data
def get_car_data(vin, access_token):
    url = POLESTAR_API_URL_V2
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
    # source for GQL string: https://github.com/evcc-io/evcc/blob/master/vehicle/polestar/query.gql
    payload = {
        "query": "query GetConsumerCarsV2 {"
                    "getConsumerCarsV2 {"
                        "vin,"
                        "internalVehicleIdentifier,"
                        "modelYear,"
                        #"claims {"             # läuft, aber noch nicht besonders nützlich
                        #    "validFromDate,"
                        #    "validUntilDate,"
                        #    "validUntilMileage"
                        #"},"
                        "hasPerformancePackage,"
                        "software {"
                            "version,"
                            "versionTimestamp"
                        "},"
                        "registrationNo,"
                        "factoryCompleteDate,"
                        "registrationDate,"
                        "deliveryDate,"
                        "currentPlannedDeliveryDate"
                    "}"
                "}",
        "operationName": "GetConsumerCarsV2",
        "variables": "{}"
    }
    response = requests.post(url, headers=headers, json=payload)
    
    if response.status_code != 200:
        wait_and_die("  response.status_code = {response.status_code}\n"
                     + json.dumps(response.json(), indent=2),
                     "get_car_data() no data received")
    car_data = response.json()['data']
    
    # get the car with given VIN
    filtered_car_data = next((car for car in car_data['getConsumerCarsV2'] if car['vin'] == vin), None)
    
    if filtered_car_data is None:
        raise ValueError(f"get_car_data(): no data for car with VIN {vin}")

    return filtered_car_data

# get battery & odometer data
def get_car_telemetry_data(vin, access_token):
    url = POLESTAR_API_URL_V2
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
    payload = {
        "query": "query carTelematics($vin:String!) {"
                    "carTelematics(vin:$vin) {"
                        "battery {"
                            "averageEnergyConsumptionKwhPer100Km,"
                            "batteryChargeLevelPercentage,"
                            "chargerConnectionStatus,"
                            "chargingCurrentAmps,"
                            "chargingPowerWatts,"
                            "chargingStatus,"
                            "estimatedChargingTimeMinutesToTargetDistance,"
                            "estimatedChargingTimeToFullMinutes,"
                            "estimatedDistanceToEmptyKm,"
                            "estimatedDistanceToEmptyMiles,"
                            "eventUpdatedTimestamp {"
                                "iso,"
                                "unix"
                            "}"
                        "}"
                        "odometer {"
                            "averageSpeedKmPerHour,"
                            "odometerMeters,"
                            "tripMeterAutomaticKm,"
                            "tripMeterManualKm,"
                            "eventUpdatedTimestamp {"
                                "iso,"
                                "unix"
                            "}"
                        "}"
                    "}"
                "}",
        "variables": {"vin": vin}
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code != 200:
        wait_and_die("  response.status_code = {response.status_code}\n"
                     + json.dumps(response.json(), indent=2),
                     "get_car_telemetry_data() no data received")
    return response.json()['data']['carTelematics']

# recursive parsing of the JSON object to build corresponding MQTT topics and send
def publish_json_as_mqtt(topic, json_obj):
    if isinstance(json_obj, dict):
        for key, value in json_obj.items():
            sub_topic = f"{topic}/{key}"
            publish_json_as_mqtt(sub_topic, value) # call self to resolve next json level
    else:
        json_payload = json.dumps(json_obj)
        client.publish(topic, json_payload, qos=1, retain=True)

# extract SoC from battery data JSON and send to openWB via MQTT
def publish_soc_to_openwb(battery_data):
    if isinstance(battery_data, dict):
        soc = battery_data['batteryChargeLevelPercentage']
        print(f' publish SoC {soc} to OpenWB {OPENWB_TOPIC}')
        client_openwb.publish(OPENWB_TOPIC, soc, qos=1, retain=True)

#####################################
# MAIN

# main program: init and loop forever
def main():
    print("Polestar_2_MQTT.py startet")
    print("==========================")

    access_token              = None  # current access token
    refresh_token             = None  # current refresh token
    expiry_time               = None  # expiry time of the current access token
    last_car_data             = None  # cache of the last car data to detect changes
    last_car_telemetry_data   = None  # cache of the last battery & odometer data to detect changes

    # catch SIGTERM to ensure graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)

    # start MQTT clients
    mqtt_connect()
    if (OPENWB_PUBLISH):
        mqtt_connect_openwb()

    while True:
        # Ensure we have a valid access token (handle expiration, refresh, and full login)
        print("ensure_valid_token()")
        access_token, expiry_time, refresh_token = ensure_valid_token(
            access_token, 
            expiry_time, 
            refresh_token, 
            POLESTAR_EMAIL, 
            POLESTAR_PASSWORD
        )

        print("get_car_data()")
        car_data = get_car_data(POLESTAR_VIN, access_token)
        if car_data != last_car_data:
            print(json.dumps(car_data, indent=4))
            last_car_data = car_data
            # send changed JSON as MQTT tree
            publish_json_as_mqtt(MQTT_BASE_TOPIC +"/getConsumerCarsV2", car_data)

        print("get_car_telemetry_data()")
        car_telemetry_data = get_car_telemetry_data(POLESTAR_VIN, access_token)
        if car_telemetry_data != last_car_telemetry_data:
            print(json.dumps(car_telemetry_data, indent=4))
            last_car_telemetry_data = car_telemetry_data
            # send changed JSON as MQTT tree
            publish_json_as_mqtt(BASE_TOPIC +"/carTelematics", car_telemetry_data)
            if OPENWB_PUBLISH:
                publish_soc_to_openwb(car_telemetry_data['battery'])

        # timestamp for current cycle to MQTT
        timestamp = datetime.now().astimezone(pytz.timezone(TZ)).strftime('%Y-%m-%d %H:%M:%S %Z%z')
        client.publish(MQTT_TIMESTAMP_TOPIC, timestamp, qos=1, retain=True)

        # wait POLESTAR_CYCLE seconds, but don't block
        print( "********************************************************************************")
        print(f"wait for {POLESTAR_CYCLE} seconds")
        for _ in range(int(POLESTAR_CYCLE/SLEEP_INTERVAL)):
            time.sleep(SLEEP_INTERVAL)

# signal handler for SIGTERM
def signal_handler(sig, frame):
    print("SIGTERM received: stop run")
    #server.shutdown() # server is undefined - reason unclear
    client.disconnect()
    if (OPENWB_PUBLISH):
        client_openwb.disconnect()
    sys.exit(0)

# catch all exeptions in main to get tracheback output
try:
    main()
except Exception as e:
    exc_type, exc_value, exc_traceback = sys.exc_info()
    # extract last line of traceback fpr 
    line_number = traceback.extract_tb(exc_traceback)[-1][1]
    print(f"Error  : {str(e)}")
    print(f"in line: {line_number}")
    print(f"type   : {exc_type.__name__}")
    print(f"message: {exc_value}")
    print("************** Traceback ***************")
    print(traceback.format_exc())

# ***** EOF *****
