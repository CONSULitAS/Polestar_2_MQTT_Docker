#!/usr/bin/python3

import base64
import hashlib
import json
import os
import urllib.parse
from datetime import datetime, timedelta

import requests


class AuthError(Exception):
    """Raised when the full login flow fails."""


class TokenError(Exception):
    """Raised when token exchange or refresh fails."""


class PolestarAuthClient:
    def __init__(self, id_uri, redirect_uri, client_id, tz):
        self.id_uri = id_uri
        self.redirect_uri = redirect_uri
        self.client_id = client_id
        self.tz = tz

    @staticmethod
    def _generate_code_verifier_and_challenge():
        code_verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode("utf-8")
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode("utf-8")).digest()
        ).rstrip(b"=").decode("utf-8")
        return code_verifier, code_challenge

    def get_path_token(self):
        code_verifier, code_challenge = self._generate_code_verifier_and_challenge()

        params = urllib.parse.urlencode(
            {
                "response_type": "code",
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "scope": "openid profile email customer:attributes",
                "state": "ea5aa2860f894a9287a4819dd5ada85c",
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        )
        url = f"{self.id_uri}/authorization.oauth2?{params}"
        response = requests.get(url, allow_redirects=False)

        if response.status_code not in (302, 303, 200):
            raise AuthError(
                f"get_path_token(): status={response.status_code}, expected one of 200/302/303"
            )

        cookies = response.headers.get("Set-Cookie")
        if not cookies:
            raise AuthError("get_path_token(): missing Set-Cookie in response")
        cookie = cookies.split(";")[0]

        body = response.text
        try:
            path_token = body.split("action:")[1].split("/")[2]
        except Exception as exc:
            raise AuthError("get_path_token(): could not extract path token from response body") from exc

        print(f"  code_verifier  = {code_verifier}")
        print(f"  code_challenge = {code_challenge}")
        print(f"  cookies        = {cookies}")
        print(f"  cookie         = {cookie}")
        print(f"  path_token     = {path_token}")

        return path_token, cookie, code_verifier

    def perform_login(self, email, password, path_token, cookie):
        url = f"{self.id_uri}/{path_token}/resume/as/authorization.ping?client_id={self.client_id}"
        headers = {"Content-Type": "application/x-www-form-urlencoded", "Cookie": cookie}
        data = (
            f"pf.username={urllib.parse.quote(email, safe='')}"
            f"&pf.pass={urllib.parse.quote(password, safe='')}"
        )

        response = requests.post(url, headers=headers, data=data, allow_redirects=False)
        if response.status_code not in (302, 303):
            raise AuthError(
                f"perform_login(): status={response.status_code}, expected redirect after login"
            )

        max_age = response.headers.get("Strict-Transport-Security", "")
        if "max-age=" in max_age:
            max_age = max_age.split("max-age=")[1].split(";")[0]
        print(f"  max_age    = {max_age}")

        location = response.headers.get("Location", "")
        uid = location.split("uid=")[1].split("&")[0] if "uid=" in location else None
        code = location.split("code=")[1].split("&")[0] if "code=" in location else None
        print(f"  uid        = {uid if uid else 'NONE'}")
        print(f"  code       = {code if code else 'NONE'}")

        if code is None and uid:
            print("   handle missing code")
            data = {"pf.submit": True, "subject": uid}
            response = requests.post(url, headers=headers, data=data, allow_redirects=False)
            location = response.headers.get("Location", "")
            code = location.split("code=")[1].split("&")[0] if "code=" in location else None
            print(f"   code = {code}")

        if code is None:
            raise AuthError(
                "perform_login(): no authorization code received; verify credentials and T&C state"
            )

        return code

    def get_api_token(self, token_request_code, code_verifier):
        url = f"{self.id_uri}/token.oauth2"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        payload = {
            "grant_type": "authorization_code",
            "code": token_request_code,
            "code_verifier": code_verifier,
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
        }
        response = requests.post(url, headers=headers, data=payload)

        try:
            response_json = response.json()
        except ValueError:
            response_json = {"raw_response": response.text}

        if response.status_code != 200 or "errors" in response_json:
            raise TokenError(
                "get_api_token(): token exchange failed\n"
                f"status={response.status_code}\n"
                f"{json.dumps(response_json, indent=2)}"
            )

        access_token = response_json["access_token"]
        refresh_token = response_json["refresh_token"]
        expires_in = response_json["expires_in"]
        expiry_time = datetime.now() + timedelta(seconds=expires_in)

        print("  access_token  = " + str(access_token)[0:39] + "...")
        print(f"  refresh_token = {refresh_token}")
        print(f"  expires_in    = {expires_in} (seconds)")
        print("  expiry_time   = " + expiry_time.isoformat())

        return access_token, expiry_time, refresh_token

    def get_token(self, email, password):
        print(" get_path_token()")
        path_token, cookie, code_verifier = self.get_path_token()
        print(" perform_login()")
        auth_code = self.perform_login(email, password, path_token, cookie)
        print(" get_api_token()")
        return self.get_api_token(auth_code, code_verifier)

    def refresh_access_token(self, refresh_token):
        url = f"{self.id_uri}/token.oauth2"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
        }
        response = requests.post(url, headers=headers, data=payload)

        try:
            response_json = response.json()
        except ValueError:
            response_json = {"raw_response": response.text}

        if response.status_code != 200 or "errors" in response_json:
            raise TokenError(
                "refresh_access_token(): refresh failed\n"
                f"status={response.status_code}\n"
                f"{json.dumps(response_json, indent=2)}"
            )

        access_token = response_json["access_token"]
        new_refresh_token = response_json["refresh_token"]
        expires_in = response_json["expires_in"]
        expiry_time = datetime.now() + timedelta(seconds=expires_in)

        print("  access_token  = " + str(access_token)[:39] + "...")
        print(f"  refresh_token = {new_refresh_token}")
        print(f"  expires_in    = {expires_in} seconds")
        print("  expiry_time   = " + expiry_time.isoformat())

        return access_token, expiry_time, new_refresh_token

    def ensure_valid_token(self, access_token, expiry_time, refresh_token, email, password):
        if expiry_time is None or datetime.now() >= expiry_time - timedelta(seconds=15):
            if refresh_token:
                print(" refresh_access_token()")
                try:
                    return self.refresh_access_token(refresh_token)
                except TokenError:
                    print(" get_token(), refresh_access_token() failed")
                    return self.get_token(email, password)
            print(" get_token(), no refresh token available")
            return self.get_token(email, password)

        return access_token, expiry_time, refresh_token
