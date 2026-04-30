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
import importlib.util
from pathlib import Path
import requests
import time
from datetime import datetime
import pytz
import json
import paho.mqtt.client as mqtt

from auth import AuthError, PolestarAuthClient, TokenError

LOCAL_GRAPHQL_QUERIES_PATH = Path("/local-files/graphql_queries.py")


def load_graphql_queries_module():
    if LOCAL_GRAPHQL_QUERIES_PATH.is_file():
        print(f"Loading local GraphQL overrides from {LOCAL_GRAPHQL_QUERIES_PATH}")
        spec = importlib.util.spec_from_file_location("local_graphql_queries", LOCAL_GRAPHQL_QUERIES_PATH)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load GraphQL overrides from {LOCAL_GRAPHQL_QUERIES_PATH}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    import graphql_queries as module
    return module


graphql_queries_module = load_graphql_queries_module()
build_cartelematicsv2_payload = graphql_queries_module.build_cartelematicsv2_payload
build_getconsumercarsv2_payload = graphql_queries_module.build_getconsumercarsv2_payload

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
MQTT_BASE_TOPIC         =     os.getenv("MQTT_BASE_TOPIC",   "polestar2")

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
MQTT_LWT_MESSAGE_ERROR = "error"
MQTT_LWT_MESSAGE_ALIVE = "online"
MQTT_TIMESTAMP_TOPIC   = f"{MQTT_BASE_TOPIC}/container/last_update"

# API config
POLESTAR_BASE_URL     = "https://pc-api.polestar.com/eu-north-1"
POLESTAR_API_URL_V2   = f"{POLESTAR_BASE_URL}/mystar-v2"
POLESTAR_REDIRECT_URI = "https://www.polestar.com/sign-in-callback"
POLESTAR_ID_URI       = "https://polestarid.eu.polestar.com/as"
CLIENT_ID             = "l3oopkc_10"

auth_client = PolestarAuthClient(POLESTAR_ID_URI, POLESTAR_REDIRECT_URI, CLIENT_ID, TZ)

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
    client.publish(MQTT_LWT_TOPIC, MQTT_LWT_MESSAGE_ERROR, qos=1, retain=True)
    time.sleep(POLESTAR_CYCLE)  # wait POLESTAR_CYCLE seconds to reduce retry count
    raise Exception(exception)
    
    return # never!

#####################################
# login to Polestar API is encapsulated in src/auth.py

#####################################
# read data from Polestar API

# get mostly static car data
def get_car_data(vin, access_token):
    url = POLESTAR_API_URL_V2
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
    response = requests.post(url, headers=headers, json=build_getconsumercarsv2_payload())

    try:
        response_json = response.json()
    except ValueError:
        response_json = {"raw_response": response.text}

    if response.status_code != 200:
        wait_and_die(f"  response.status_code = {response.status_code}\n"
                     + json.dumps(response_json, indent=2),
                     "get_car_data() no data received")

    car_data = response_json.get('data') or {}
    consumer_cars = car_data.get('getConsumerCarsV2')

    if not isinstance(consumer_cars, list):
        wait_and_die("get_car_data(): unexpected API response\n"
                     + json.dumps(response_json, indent=2),
                     "get_car_data(): getConsumerCarsV2 missing or invalid")

    filtered_car_data = next(
        (car for car in consumer_cars if isinstance(car, dict) and car.get('vin') == vin),
        None
    )

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
    response = requests.post(url, headers=headers, json=build_cartelematicsv2_payload(vin))
    if response.status_code != 200:
        print(response.json())
        wait_and_die("  response.status_code = {response.status_code}\n"
                     + json.dumps(response.json(), indent=2),
                     "get_car_telemetry_data() no data received")
    return response.json()['data']['carTelematicsV2']

# recursive parsing of the JSON object to build corresponding MQTT topics and send
def publish_json_as_mqtt(topic, json_obj):
    if isinstance(json_obj, dict):
         # dict → rekursiv
        for key, value in json_obj.items():
            sub_topic = f"{topic}/{key}"
            publish_json_as_mqtt(sub_topic, value) # call self to resolve next json level

    elif isinstance(json_obj, list):
         # list → Index im Topic
        for idx, item in enumerate(json_obj):
             sub_topic = f"{topic}/{idx}"
             publish_json_as_mqtt(sub_topic, item)

    else:
        if isinstance(json_obj, str):
            json_payload = json_obj
        else:
            json_payload = json.dumps(json_obj) # json.dumps für korrekte String-Repräsentation

        print(f"{topic}: {json_payload}")
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
        try:
            access_token, expiry_time, refresh_token = auth_client.ensure_valid_token(
                access_token,
                expiry_time,
                refresh_token,
                POLESTAR_EMAIL,
                POLESTAR_PASSWORD,
            )
        except (AuthError, TokenError) as exc:
            client.publish(MQTT_LWT_TOPIC, "auth_error", qos=1, retain=True)
            wait_and_die("Authentication flow failed", str(exc))

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
            publish_json_as_mqtt(MQTT_BASE_TOPIC +"/CarTelematicsV2", car_telemetry_data)
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

if __name__ == "__main__":
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
