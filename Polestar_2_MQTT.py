#!/usr/bin/python3

import traceback
import os
import requests
import time
import json
from datetime import datetime, timedelta
import pytz

# Umgebungsvariablen lesen
POLESTAR_EMAIL    = os.getenv('POLESTAR_EMAIL')
POLESTAR_PASSWORD = os.getenv('POLESTAR_PASSWORD')
POLESTAR_VIN      = os.getenv('POLESTAR_VIN')
POLESTAR_CYCLE    = int(os.getenv('POLESTAR_CYCLE')) # Sekunden
TZ                = os.getenv('TZ') # z.B. 'Europe/Berlin'
# TODO: MQTT-Credentials

def get_local_time(tz, time):
    # Konvertierung in die Zeitzone tz (z.B. Europe/Berlin)
    local_time = time.astimezone(pytz.timezone(tz))

    # Ausgabe des Zeitstempels in tz
    return local_time.strftime('%Y-%m-%d %H:%M:%S %Z%z')

# Funktion zum Abrufen des Login-Tokens und der Cookies
def get_login_tokens():
    url = "https://polestarid.eu.polestar.com/as/authorization.oauth2?response_type=code&client_id=polmystar&redirect_uri=https://www.polestar.com%2Fsign-in-callback&scope=openid+profile+email+customer%3Aattributes"
    response = requests.get(url, allow_redirects=False)
    if response.status_code != 303: # = 'see other'
        print("  response.status_code = " + str(response.status_code))
        raise Exception("get_login_tokens(): Login-Token-Anfrage fehlgeschlagen")
    cookies    = response.headers.get('Set-Cookie')
    cookie     = cookies.split(';')[0]
    path_token = response.headers.get('Location').split("resumePath=")[1].split("&")[0]
    print("  cookies    = " + str(cookies))
    print("  cookie     = " + str(cookie))
    print("  path_token = " + str(path_token))
    return path_token, cookie

# Funktion zum Einloggen und Abrufen des autorisierten Codes
def perform_login(email, password, path_token, cookie):
    url = f"https://polestarid.eu.polestar.com/as/{path_token}/resume/as/authorization.ping"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Cookie": cookie
    }
    data = f"pf.username={email}&pf.pass={password}"
    response = requests.post(url, headers=headers, data=data, allow_redirects=False)
    if response.status_code != 302:
        print("  response.status_code = " + str(response.status_code))
        raise Exception("perform_login(): Login fehlgeschlagen")
    code    = response.headers['Location'].split("code=")[1].split("&")[0]
    max_age = response.headers['Strict-Transport-Security'].split("max-age=")[1].split(";")[0]
    print("  code       = " + str(code))
    print("  max_age    = " + str(max_age))
    return code

# Funktion zum Abrufen des API-Tokens
def get_api_token(code):
    url = "https://pc-api.polestar.com/eu-north-1/auth"
    headers = {
        "Content-Type": "application/json"
    }
    payload = {
        "query": "query getAuthToken($code: String!){"
                    "getAuthToken(code: $code){"
                        "id_token,"
                        "access_token,"
                        "refresh_token,"
                        "expires_in"
                    "}"
                 "}",
        "operationName": "getAuthToken",
        "variables": {"code": code}
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code != 200 or "errors" in response.json():
        print("  response.status_code = " + str(response.status_code))
        raise Exception("get_api_token(): API-Token-Anfrage fehlgeschlagen")
    api_creds     = response.json()['data']['getAuthToken']
    access_token  = api_creds['access_token']
    refresh_token = api_creds['refresh_token']
    expires_in    = api_creds['expires_in']
    expiry_time   = datetime.now() + timedelta(seconds=expires_in)
    print("  access_token  = " + str(access_token)[0:39] + "...")
    print("  refresh_token = " + str(refresh_token))
    print("  expires_in    = " + str(expires_in))
    print("  expiry_time   = " + get_local_time(TZ, expiry_time))
    return access_token, expiry_time, refresh_token

def get_token(email, password):
    print(" get_login_tokens()")
    path_token, cookie = get_login_tokens()
    print(" perform_login()")
    auth_code = perform_login(email, password, path_token, cookie)
    print(" get_api_token()")
    access_token, expiry_time, refresh_token = get_api_token(auth_code)

    return access_token, expiry_time, refresh_token

# unbekannter API-Endpoint
#        "query": "\n  query getCarSpecifications($locale: SiteLocale) {\n    loggedinCarSpecification(locale: $locale) {\n      title {\n        key\n        value\n      }\n      specificationGroups {\n        groupId\n        label {\n          key\n          value\n        }\n        rows {\n          specificationId\n          label {\n            key\n            value\n          }\n        }\n      }\n      chargeport {\n        value\n      }\n    }\n  }\n",

# Funktion zum Abrufen von Fahrzeugdaten
def get_car_data(vin, access_token):
    url = "https://pc-api.polestar.com/eu-north-1/my-star"
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
                        # "content {"
                        #     "code,"
                        #     "name"
                        # "}"
                        # "images {"
                        #     "studio {"
                        #         "url,"
                        #         "angles"
                        #     "}"
                        # "}"
                        "hasPerformancePackage,"
                        "registrationNo,"
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
        raise Exception("get_car_data() Datenabfrage fehlgeschlagen")
    car_data = response.json()['data']
    return car_data

# Funktion zum Abrufen von Batteriedaten
def get_battery_data(vin, access_token):
    url = "https://pc-api.polestar.com/eu-north-1/mystar-v2"
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
    url = "https://pc-api.polestar.com/eu-north-1/mystar-v2"
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

# Hauptprogramm
def main():
    print("Polestar_2_MQTT.py startet")
    print("==========================")

    expiry_time        = None
    last_car_data      = None
    last_battery_data  = None
    last_odometer_data = None

    while True:
        # TODO: MQTT-Versand der Daten

        if expiry_time == None or datetime.now() >= expiry_time - timedelta(seconds = 2* POLESTAR_CYCLE):
            # TODO WORKAROUND: neu einloggen, statt refresh_token nutzen
            print("get_token()")
            access_token, expiry_time, refresh_token = get_token(POLESTAR_EMAIL, POLESTAR_PASSWORD)

        print("get_car_data()")
        car_data = get_car_data(POLESTAR_VIN, access_token)
        if car_data != last_car_data:
            print(json.dumps(car_data, indent=4))
            last_car_data = car_data

        print("get_battery_data()")
        battery_data = get_battery_data(POLESTAR_VIN, access_token)
        if battery_data != last_battery_data:
            print(json.dumps(battery_data, indent=4))
            last_battery_data = battery_data
        
        print("get_odometer_data()")
        odometer_data = get_odometer_data(POLESTAR_VIN, access_token)
        if odometer_data != last_odometer_data:
            print(json.dumps(odometer_data, indent=4))
            last_odometer_data = odometer_data

        time.sleep(POLESTAR_CYCLE)  # wartet POLESTAR_CYCLE Sekunden

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