#!/usr/bin/python3

import os
import requests
import json

# Umgebungsvariablen lesen
POLESTAR_EMAIL = os.getenv('POLESTAR_EMAIL')
POLESTAR_PASSWORD = os.getenv('POLESTAR_PASSWORD')
VIN = os.getenv('VIN')

# Funktion zum Abrufen des Login-Tokens und der Cookies
def get_login_tokens():
    url = "https://polestarid.eu.polestar.com/as/authorization.oauth2?response_type=code&client_id=polmystar&redirect_uri=https://www.polestar.com%2Fsign-in-callback&scope=openid+profile+email+customer%3Aattributes"
    response = requests.get(url, allow_redirects=False)
    cookies = response.headers.get('Set-Cookie')
    path_token = response.headers.get('Location').split("resumePath=")[1].split("&")[0]
    return path_token, cookies.split(';')[0]

# Funktion zum Einloggen und Abrufen des autorisierten Codes
def perform_login(path_token, cookie):
    url = f"https://polestarid.eu.polestar.com/as/{path_token}/resume/as/authorization.ping"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Cookie": cookie
    }
    data = f"pf.username={POLESTAR_EMAIL}&pf.pass={POLESTAR_PASSWORD}"
    response = requests.post(url, headers=headers, data=data, allow_redirects=False)
    code = response.headers['Location'].split("code=")[1].split("&")[0]
    return code

# Funktion zum Abrufen des API-Tokens
def get_api_token(code):
    url = "https://pc-api.polestar.com/eu-north-1/auth"
    headers = {
        "Content-Type": "application/json"
    }
    payload = {
        "query": "query getAuthToken($code: String!){getAuthToken(code: $code){id_token,access_token,refresh_token,expires_in}}",
        "operationName": "getAuthToken",
        "variables": {"code": code}
    }
    response = requests.post(url, headers=headers, json=payload)
    return response.json()['data']['getAuthToken']['access_token']

# Funktion zum Abrufen von Batteriedaten
def get_battery_data(access_token):
    url = "https://pc-api.polestar.com/eu-north-1/mystar-v2"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
    payload = {
        "query": "query GetBatteryData($vin:String!){getBatteryData(vin:$vin){averageEnergyConsumptionKwhPer100Km,batteryChargeLevelPercentage,chargerConnectionStatus,chargingCurrentAmps,chargingPowerWatts,chargingStatus,estimatedChargingTimeMinutesToTargetDistance,estimatedChargingTimeToFullMinutes,estimatedDistanceToEmptyKm,estimatedDistanceToEmptyMiles,eventUpdatedTimestamp{iso,unix}}}",
        "variables": {"vin": VIN}
    }
    response = requests.post(url, headers=headers, json=payload)
    return response.json()

# Hauptausführungsteil
path_token, cookie = get_login_tokens()
auth_code = perform_login(path_token, cookie)
access_token = get_api_token(auth_code)
battery_data = get_battery_data(access_token)

print(json.dumps(battery_data, indent=4))

