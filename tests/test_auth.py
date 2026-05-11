import base64
import hashlib
from datetime import datetime, timedelta

import pytest

import auth
from auth import AuthError, PolestarAuthClient, TokenError


@pytest.fixture
def auth_client():
    return PolestarAuthClient(
        "https://polestarid.example.com/as",
        "https://www.polestar.com/sign-in-callback",
        "client-id",
        "Europe/Berlin",
    )


def test_generate_code_verifier_and_challenge_returns_matching_pair():
    code_verifier, code_challenge = PolestarAuthClient._generate_code_verifier_and_challenge()

    expected_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode("utf-8")).digest()
    ).rstrip(b"=").decode("utf-8")

    assert code_verifier
    assert "=" not in code_verifier
    assert code_challenge == expected_challenge


def test_get_path_token_extracts_values(auth_client, monkeypatch, make_response):
    captured = {}

    def fake_get(url, allow_redirects=False):
        captured["url"] = url
        captured["allow_redirects"] = allow_redirects
        return make_response(
            status_code=200,
            headers={"Set-Cookie": "sessionid=abc123; Path=/; HttpOnly"},
            text="prefix action:/resume/path-token-42/continue suffix",
        )

    monkeypatch.setattr(
        auth_client,
        "_generate_code_verifier_and_challenge",
        lambda: ("fixed-verifier", "fixed-challenge"),
    )
    monkeypatch.setattr(auth.requests, "get", fake_get)

    path_token, cookie, code_verifier = auth_client.get_path_token()

    assert path_token == "path-token-42"
    assert cookie == "sessionid=abc123"
    assert code_verifier == "fixed-verifier"
    assert captured["allow_redirects"] is False
    assert "code_challenge=fixed-challenge" in captured["url"]


def test_get_path_token_raises_when_cookie_missing(auth_client, monkeypatch, make_response):
    monkeypatch.setattr(
        auth.requests,
        "get",
        lambda url, allow_redirects=False: make_response(status_code=200, headers={}, text="ok"),
    )

    with pytest.raises(AuthError, match="missing Set-Cookie"):
        auth_client.get_path_token()


def test_perform_login_returns_code_from_redirect(auth_client, monkeypatch, make_response):
    def fake_post(url, headers=None, data=None, allow_redirects=False):
        return make_response(
            status_code=302,
            headers={
                "Location": "https://www.polestar.com/sign-in-callback?code=auth-code-123",
                "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            },
        )

    monkeypatch.setattr(auth.requests, "post", fake_post)

    code = auth_client.perform_login("user@example.com", "secret", "path-token", "cookie=value")

    assert code == "auth-code-123"


def test_perform_login_retries_when_uid_is_returned_first(auth_client, monkeypatch, make_response):
    responses = iter(
        [
            make_response(
                status_code=302,
                headers={"Location": "https://redirect.example/callback?uid=user-123"},
            ),
            make_response(
                status_code=302,
                headers={"Location": "https://redirect.example/callback?code=follow-up-code"},
            ),
        ]
    )

    monkeypatch.setattr(
        auth.requests,
        "post",
        lambda url, headers=None, data=None, allow_redirects=False: next(responses),
    )

    code = auth_client.perform_login("user@example.com", "secret", "path-token", "cookie=value")

    assert code == "follow-up-code"


def test_get_api_token_returns_tokens_and_expiry(auth_client, monkeypatch, make_response):
    before_call = datetime.now()

    monkeypatch.setattr(
        auth.requests,
        "post",
        lambda url, headers=None, data=None: make_response(
            status_code=200,
            json_data={
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "expires_in": 300,
            },
        ),
    )

    access_token, expiry_time, refresh_token = auth_client.get_api_token("code-123", "verifier-123")

    assert access_token == "access-token"
    assert refresh_token == "refresh-token"
    assert before_call + timedelta(seconds=295) <= expiry_time <= before_call + timedelta(seconds=305)


def test_get_api_token_raises_for_error_payload(auth_client, monkeypatch, make_response):
    monkeypatch.setattr(
        auth.requests,
        "post",
        lambda url, headers=None, data=None: make_response(
            status_code=400,
            json_data={"errors": [{"message": "invalid_grant"}]},
        ),
    )

    with pytest.raises(TokenError, match="token exchange failed"):
        auth_client.get_api_token("bad-code", "verifier")


def test_ensure_valid_token_returns_existing_token_when_not_expiring(auth_client):
    expiry_time = datetime.now() + timedelta(minutes=10)

    result = auth_client.ensure_valid_token(
        "current-token", expiry_time, "refresh-token", "user@example.com", "secret"
    )

    assert result == ("current-token", expiry_time, "refresh-token")


def test_ensure_valid_token_uses_refresh_token_first(auth_client, monkeypatch):
    refreshed = ("new-token", datetime.now() + timedelta(minutes=30), "new-refresh")
    monkeypatch.setattr(auth_client, "refresh_access_token", lambda refresh_token: refreshed)

    result = auth_client.ensure_valid_token(
        "expired-token",
        datetime.now() + timedelta(seconds=10),
        "refresh-token",
        "user@example.com",
        "secret",
    )

    assert result == refreshed


def test_ensure_valid_token_falls_back_to_full_login_when_refresh_fails(auth_client, monkeypatch):
    fresh_login = ("fresh-token", datetime.now() + timedelta(minutes=30), "fresh-refresh")

    def fail_refresh(refresh_token):
        raise TokenError("refresh failed")

    monkeypatch.setattr(auth_client, "refresh_access_token", fail_refresh)
    monkeypatch.setattr(auth_client, "get_token", lambda email, password: fresh_login)

    result = auth_client.ensure_valid_token(
        "expired-token",
        datetime.now() + timedelta(seconds=10),
        "refresh-token",
        "user@example.com",
        "secret",
    )

    assert result == fresh_login
