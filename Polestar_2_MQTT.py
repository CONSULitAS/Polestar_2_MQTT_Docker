#!/usr/bin/python3

#
# Polestar_2_MQTT.py
#
# (c) @CONSULitAS 2024
# 

# TODO: PKCE challenge
# TODO: token refresh
# TODO: openWB URL
# TODO: better error handling
# TODO: report online/offline state on MQTT

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

#####################################
# read ENVIRONMENT variables

# general
TZ                      =     os.getenv('TZ',                "Europe/Berlin")

# credentials for Polestar API
POLESTAR_EMAIL          =     os.getenv('POLESTAR_EMAIL')
POLESTAR_PASSWORD       =     os.getenv('POLESTAR_PASSWORD')
POLESTAR_VIN            =     os.getenv('POLESTAR_VIN')
POLESTAR_CYCLE          = int(os.getenv('POLESTAR_CYCLE',    "300")) # seconds

# MQTT broker
MQTT_BROKER             =     os.getenv("MQTT_BROKER",       "localhost") # IP or DNS name
MQTT_PORT               = int(os.getenv("MQTT_PORT",         1883))
MQTT_KEEPALIVE_INTERVAL = int(os.getenv("MQTT_KEEPALIVE",    60))
MQTT_USER               =     os.getenv("MQTT_USER",         "")
MQTT_PASSWORD           =     os.getenv("MQTT_PASSWORD",     "")
BASE_TOPIC              =     os.getenv("BASE_TOPIC",     "polestar2")

# openWB - optional
OPENWB_PUBLISH          =     os.getenv("OPENWB_PUBLISH", False) # default: no openWB 
OPENWB_HOST             =     os.getenv("OPENWB_HOST",    "localhost")
OPENWB_PORT             = int(os.getenv("OPENWB_PORT",    1883))
OPENWB_LP_NUM           = int(os.getenv("OPENWB_LP_NUM",  1)) # can be 1 to 8
#OPENWB_TOPIC            =     os.getenv("OPENWB_TOPIC",   "openWB/set/lp{OPENWB_LP_NUM}/%Soc")

#####################################
# global init

# constants
SLEEP_INTERVAL        = 0.1

# API config
POLESTAR_BASE_URL     = "https://pc-api.polestar.com/eu-north-1"
POLESTAR_API_URL_V2   = f"{POLESTAR_BASE_URL}/mystar-v2"
POLESTAR_REDIRECT_URI = "https://www.polestar.com/sign-in-callback"
POLESTAR_ID_URI       = "https://polestarid.eu.polestar.com/as"
CLIENT_ID             = "l3oopkc_10"
CODE_VERIFIER         = "polestar-ios-widgets-are-enabled-by-scriptable" # TODO: real challenge
CODE_CHALLENGE        = "adYJTSAVqq6CWBJn7yNdGKwcsmJb8eBewG8WpxnUzaE"

# setup MQTT-Client
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

# setup MQTT-Client for openWB if needed
if (OPENWB_PUBLISH):
    OPENWB_TOPIC  = "openWB/set/lp/" + str(OPENWB_LP_NUM) + "/%Soc" # TODO: use ENV string
    client_openwb = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

#####################################
# MQTT helper functions

# callback for MQTT connection handling
def on_connect(client, userdata, flags, rc, properties):
    print(f"MQTT connected with result code '{rc}'.")

# callback for MQTT disconnection handling
def on_disconnect(client, userdata, rc, properties, reason_code):
    if rc != 0:
        print("MQTT disconnected unexpected with reason code '{reason_code}'.")
        # try to reconnect
        client.reconnect()

# connect to MQTT broker
def connect_mqtt():   
    # MQTT_USER and MQTT_PASSWORD have to be empty if no login to broker configured
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)   
    client.on_connect     = on_connect
    client.on_disconnect  = on_disconnect
    client.connect(MQTT_BROKER, MQTT_PORT, MQTT_KEEPALIVE_INTERVAL)
    client.loop_start()

# connect to OpenWB built in MQTT broker
def connect_mqtt_openwb():   
    client_openwb.on_connect    = on_connect
    client_openwb.on_disconnect = on_disconnect
    client_openwb.connect(OPENWB_HOST, OPENWB_PORT, MQTT_KEEPALIVE_INTERVAL)
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

# get login token and cookies (polestar-xxx-widget.js: getLoginFlowTokens())
def get_path_token():
    # dictionary with parameters encoded in URL
    params = urllib.parse.urlencode({
        "response_type":         "code",
        "client_id":             CLIENT_ID,
        "redirect_uri":          POLESTAR_REDIRECT_URI,
        "scope":                 "openid profile email customer:attributes",
        "state":                 "ea5aa2860f894a9287a4819dd5ada85c",
        "code_challenge":        CODE_CHALLENGE,
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
    print(f"  cookies    = {cookies}")
    print(f"  cookie     = {cookie}")
    print(f"  path_token = {path_token}")
    
    return path_token, cookie

# login with token and credentials to get the code
def perform_login(email, password, path_token, cookie):
    url = f"{POLESTAR_ID_URI}/{path_token}/resume/as/authorization.ping?client_id={CLIENT_ID}"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Cookie": cookie
    }
    data = f"pf.username={email}&pf.pass={password}"
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
    
    return code

# get API tokens
def get_api_token(tokenRequestCode):
    url = f"{POLESTAR_ID_URI}/token.oauth2"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    # dictionary for URL encoded data (requests will to the encoding)
    payload = {
        "grant_type":    "authorization_code",
        "code":          tokenRequestCode,
        "code_verifier": CODE_VERIFIER,
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
    print("  access_token  = " + str(access_token)[0:39] + "...")
    print("  refresh_token = {refresh_token}")
    print("  expires_in    = {expires_in}")
    print("  expiry_time   = " + get_local_time(TZ, expiry_time))
    
    return access_token, expiry_time, refresh_token

def get_token(email, password):
    print(" get_path_token()")
    path_token, cookie = get_path_token()
    print(" perform_login()")
    auth_code = perform_login(email, password, path_token, cookie)
    print(" get_api_token()")
    access_token, expiry_time, refresh_token = get_api_token(auth_code)

    return access_token, expiry_time, refresh_token

# unbekannter API-Endpoint
#        "query": "\n  query getCarSpecifications($locale: SiteLocale) {\n    loggedinCarSpecification(locale: $locale) {\n      title {\n        key\n        value\n      }\n      specificationGroups {\n        groupId\n        label {\n          key\n          value\n        }\n        rows {\n          specificationId\n          label {\n            key\n            value\n          }\n        }\n      }\n      chargeport {\n        value\n      }\n    }\n  }\n",

#####################################
# read data from Polestar API

# Funktion zum Abrufen von Fahrzeugdaten
def get_car_data(vin, access_token):
    url = POLESTAR_API_URL_V2
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
    # Quelle für GQL-String: https://github.com/evcc-io/evcc/blob/master/vehicle/polestar/query.gql
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
        print("  response.status_code = " + str(response.status_code))
        print(response)
        raise Exception("get_car_data() Datenabfrage fehlgeschlagen")
    car_data = response.json()['data']
    
    # Filtern der Daten nach der gegebenen VIN
    filtered_car_data = next((car for car in car_data['getConsumerCarsV2'] if car['vin'] == vin), None)
    
    if filtered_car_data is None:
        raise ValueError(f"get_car_data(): Keine Daten für VIN {vin} gefunden.")

    return filtered_car_data


# Funktion zum Abrufen von Batteriedaten
def get_battery_data(vin, access_token):
    url = POLESTAR_API_URL_V2
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
    payload = {
        "query": "query GetBatteryData($vin:String!) {"
                    "getBatteryData(vin:$vin) {"
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
                "}",
        "variables": {"vin": vin}
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code != 200:
        print("  response.status_code = " + str(response.status_code))
        raise Exception("get_battery_data() Datenabfrage fehlgeschlagen")
    battery_data = response.json()['data']
    return battery_data

# Funktion zum Abrufen von Odometerdaten
def get_odometer_data(vin, access_token):
    url = POLESTAR_API_URL_V2
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
    # Quelle für GQL-String: https://github.com/evcc-io/evcc/blob/master/vehicle/polestar/query.gql
    payload = {
        "query": "query GetOdometerData($vin:String!) {"
                    "getOdometerData(vin:$vin) {"
                        "averageSpeedKmPerHour,"
                        "odometerMeters,"
                        "tripMeterAutomaticKm,"
                        "tripMeterManualKm,"
                        "eventUpdatedTimestamp {"
                            "iso,"
                            "unix"
                        "}"
                    "}"
                "}",
        "variables": {"vin": vin}
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code != 200:
        print("  response.status_code = " + str(response.status_code))
        raise Exception("get_odometer_data() Datenabfrage fehlgeschlagen")
    odometer_data = response.json()['data']
    return odometer_data

# Rekursives Durchlaufen des JSON-Objekts und Senden der Daten als MQTT-Nachrichten
def publish_json_as_mqtt(topic, json_obj):
    if isinstance(json_obj, dict):
        for key, value in json_obj.items():
            sub_topic = f"{topic}/{key}"
            publish_json_as_mqtt(sub_topic, value)
    else:
        json_payload = json.dumps(json_obj)
        client.publish(topic, json_payload, qos=1, retain=True)

def publish_soc_to_openwb(battery_data):
    if isinstance(battery_data, dict):
        soc = battery_data['getBatteryData']['batteryChargeLevelPercentage']
        print(f'publishing SoC {soc} to OpenWB {OPENWB_TOPIC}')
        client_openwb.publish(OPENWB_TOPIC,soc,qos=1, retain=True)


# Hauptprogramm
def main():
    print("Polestar_2_MQTT.py startet")
    print("==========================")

    expiry_time        = None
    last_car_data      = None
    last_battery_data  = None
    last_odometer_data = None

    # init sinal handler
    signal.signal(signal.SIGTERM, signal_handler)

    # Starten der MQTT-Verbindung
    connect_mqtt()
    if (OPENWB_PUBLISH):
        connect_mqtt_openwb()

    while True:
        if expiry_time == None or datetime.now() >= expiry_time:
            # TODO WORKAROUND: neu einloggen, statt refresh_token nutzen
            print("get_token()")
            access_token, expiry_time, refresh_token = get_token(POLESTAR_EMAIL, POLESTAR_PASSWORD)

        print("get_car_data()")
        car_data = get_car_data(POLESTAR_VIN, access_token)
        if car_data != last_car_data:
            print(json.dumps(car_data, indent=4))
            last_car_data = car_data
            # send changed JSON as MQTT tree
            publish_json_as_mqtt(BASE_TOPIC +"/getConsumerCarsV2", car_data)

        print("get_battery_data()")
        battery_data = get_battery_data(POLESTAR_VIN, access_token)
        if battery_data != last_battery_data:
            print(json.dumps(battery_data, indent=4))
            last_battery_data = battery_data
            # send changed JSON as MQTT tree
            publish_json_as_mqtt(BASE_TOPIC, battery_data)
            if OPENWB_PUBLISH:
                publish_soc_to_openwb(battery_data)
        
        print("get_odometer_data()")
        odometer_data = get_odometer_data(POLESTAR_VIN, access_token)
        if odometer_data != last_odometer_data:
            print(json.dumps(odometer_data, indent=4))
            last_odometer_data = odometer_data
            # send changed JSON as MQTT tree
            publish_json_as_mqtt(BASE_TOPIC, odometer_data)

        # wait POLESTAR_CYCLE seconds, but don't block
        print( "********************************************************************************")
        print(f"wait for {POLESTAR_CYCLE} seconds")
        for _ in range(int(POLESTAR_CYCLE/SLEEP_INTERVAL)):
            time.sleep(SLEEP_INTERVAL)

# Signal-Handler für SIGTERM
def signal_handler(sig, frame):
    print("SIGTERM received: stop run")
    server.shutdown()
    client.disconnect()
    if (OPENWB_PUBLISH):
        client_openwb.disconnect()
    sys.exit(0)

try:
    main()
except Exception as e:
    print(f"Fehler: {str(e)}")

    exc_type, exc_value, exc_traceback = sys.exc_info()
    # extrahiere die letzte Zeile des Tracebacks
    line_number = traceback.extract_tb(exc_traceback)[-1][1]
    print("Fehler in Zeile:", line_number)
    print("Fehlertyp und Nachricht:", exc_type.__name__, exc_value)

    print(traceback.format_exc())

# ***** EOF *****
