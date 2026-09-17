"""Unit tests for client-secret expiry monitoring."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from polestar_mqtt.credential_expiry import (
    WARNING_DAYS,
    CredentialExpiryMonitor,
    CredentialStatus,
    credential_expiry_warning,
    credential_status,
    remaining_full_days,
)


NOW = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("remaining", "expected_days"),
    [
        (timedelta(days=30), 30),
        (timedelta(days=30, seconds=-1), 29),
        (timedelta(hours=23, minutes=59), 0),
        (timedelta(0), 0),
        (timedelta(seconds=-1), 0),
    ],
)
def test_calculates_non_negative_full_days(
    remaining: timedelta,
    expected_days: int,
) -> None:
    assert remaining_full_days(NOW + remaining, now=NOW) == expected_days


@pytest.mark.parametrize(
    ("remaining", "expected_status"),
    [
        (timedelta(days=31), CredentialStatus.OK),
        (timedelta(days=30), CredentialStatus.WARNING),
        (timedelta(days=8), CredentialStatus.WARNING),
        (timedelta(days=7), CredentialStatus.CRITICAL),
        (timedelta(days=1), CredentialStatus.CRITICAL),
        (timedelta(seconds=1), CredentialStatus.CRITICAL),
        (timedelta(0), CredentialStatus.EXPIRED),
        (timedelta(seconds=-1), CredentialStatus.EXPIRED),
    ],
)
def test_classifies_every_status_boundary(
    remaining: timedelta,
    expected_status: CredentialStatus,
) -> None:
    assert credential_status(NOW + remaining, now=NOW) is expected_status


@pytest.mark.parametrize("days", sorted(WARNING_DAYS))
def test_creates_warning_at_every_day_threshold(days: int) -> None:
    expiry = NOW + (timedelta(hours=12) if days == 0 else timedelta(days=days))

    warning = credential_expiry_warning(expiry, now=NOW)

    assert warning is not None
    assert warning.days_remaining == days
    assert f"days_remaining={days}" in warning.message


@pytest.mark.parametrize("days", [31, 29, 15, 13, 8, 6, 2])
def test_does_not_warn_outside_day_thresholds(days: int) -> None:
    assert credential_expiry_warning(NOW + timedelta(days=days), now=NOW) is None


def test_distinguishes_critical_and_expired_zero_day_warnings() -> None:
    critical = credential_expiry_warning(NOW + timedelta(seconds=1), now=NOW)
    expired = credential_expiry_warning(NOW - timedelta(seconds=1), now=NOW)

    assert critical is not None and critical.status is CredentialStatus.CRITICAL
    assert expired is not None and expired.status is CredentialStatus.EXPIRED


def test_emits_each_threshold_once_per_expiry() -> None:
    expires_at = NOW + timedelta(days=30)
    monitor = CredentialExpiryMonitor()

    first = monitor.next_warning(expires_at, now=NOW)
    assert first is not None and first.days_remaining == 30
    assert monitor.next_warning(expires_at, now=NOW) is None
    assert monitor.next_warning(expires_at, now=NOW + timedelta(hours=1)) is None

    at_fourteen_days = expires_at - timedelta(days=14)
    second = monitor.next_warning(expires_at, now=at_fourteen_days)
    assert second is not None and second.days_remaining == 14
    assert monitor.next_warning(expires_at, now=at_fourteen_days) is None


def test_new_expiry_has_independent_warning_thresholds() -> None:
    monitor = CredentialExpiryMonitor()
    first_expiry = NOW + timedelta(days=30)
    rotated_expiry = first_expiry + timedelta(hours=1)

    assert monitor.next_warning(first_expiry, now=NOW) is not None
    assert monitor.next_warning(rotated_expiry, now=NOW) is not None


def test_checks_at_start_and_after_twenty_four_hours() -> None:
    expires_at = NOW + timedelta(days=30)
    monitor = CredentialExpiryMonitor()

    startup = monitor.check(expires_at, now=NOW)
    assert startup is not None
    assert startup.warning is not None
    assert monitor.check(expires_at, now=NOW + timedelta(hours=23, minutes=59)) is None

    daily = monitor.check(expires_at, now=NOW + timedelta(days=1))
    assert daily is not None
    assert daily.days_remaining == 29
    assert daily.warning is None


def test_checks_rotated_expiry_immediately() -> None:
    monitor = CredentialExpiryMonitor()
    first_expiry = NOW + timedelta(days=30)
    rotated_expiry = NOW + timedelta(days=120)

    assert monitor.check(first_expiry, now=NOW) is not None
    rotation = monitor.check(rotated_expiry, now=NOW + timedelta(hours=1))
    assert rotation is not None
    assert rotation.expires_at == rotated_expiry


@pytest.mark.parametrize("argument", ["expires_at", "now"])
def test_rejects_naive_timestamps(argument: str) -> None:
    expires_at = NOW + timedelta(days=30)
    now = NOW
    if argument == "expires_at":
        expires_at = expires_at.replace(tzinfo=None)
    else:
        now = now.replace(tzinfo=None)

    with pytest.raises(ValueError, match=argument):
        remaining_full_days(expires_at, now=now)

