"""Client-secret expiry calculations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum


SECONDS_PER_DAY = 24 * 60 * 60
CRITICAL_THRESHOLD_DAYS = 7
WARNING_THRESHOLD_DAYS = 30
WARNING_DAYS = frozenset({30, 14, 7, 3, 1, 0})
CREDENTIAL_CHECK_INTERVAL = timedelta(days=1)


class CredentialStatus(StrEnum):
    """Operational status of the configured client secret."""

    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"
    EXPIRED = "expired"


@dataclass(frozen=True)
class CredentialExpiryWarning:
    """A structured, non-sensitive client-secret expiry warning."""

    days_remaining: int
    status: CredentialStatus
    expires_at: datetime

    @property
    def message(self) -> str:
        return (
            "Polestar client secret expiry warning: "
            f"status={self.status.value}, "
            f"days_remaining={self.days_remaining}, "
            f"expires_at={self.expires_at.astimezone(UTC).isoformat()}"
        )


@dataclass(frozen=True)
class CredentialExpiryCheck:
    """Result of a scheduled client-secret expiry check."""

    checked_at: datetime
    expires_at: datetime
    days_remaining: int
    status: CredentialStatus
    warning: CredentialExpiryWarning | None


class CredentialExpiryMonitor:
    """Suppress repeated warnings during one process lifetime."""

    def __init__(self) -> None:
        self._emitted_thresholds: set[tuple[datetime, int]] = set()
        self._last_checked_at: datetime | None = None
        self._last_checked_expiry: datetime | None = None

    def check(
        self,
        expires_at: datetime,
        *,
        now: datetime | None = None,
    ) -> CredentialExpiryCheck | None:
        """Check immediately at startup and at most once per 24 hours afterward."""

        current_time = datetime.now(UTC) if now is None else now
        if expires_at.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")
        if current_time.tzinfo is None:
            raise ValueError("now must be timezone-aware")

        current_utc = current_time.astimezone(UTC)
        expiry_utc = expires_at.astimezone(UTC)
        expiry_changed = expiry_utc != self._last_checked_expiry
        if self._last_checked_at is not None and not expiry_changed:
            elapsed = current_utc - self._last_checked_at
            if timedelta(0) <= elapsed < CREDENTIAL_CHECK_INTERVAL:
                return None

        self._last_checked_at = current_utc
        self._last_checked_expiry = expiry_utc
        return CredentialExpiryCheck(
            checked_at=current_utc,
            expires_at=expiry_utc,
            days_remaining=remaining_full_days(expiry_utc, now=current_utc),
            status=credential_status(expiry_utc, now=current_utc),
            warning=self.next_warning(expiry_utc, now=current_utc),
        )

    def next_warning(
        self,
        expires_at: datetime,
        *,
        now: datetime | None = None,
    ) -> CredentialExpiryWarning | None:
        """Return a threshold warning once per expiry timestamp and day value."""

        warning = credential_expiry_warning(expires_at, now=now)
        if warning is None:
            return None

        key = (expires_at.astimezone(UTC), warning.days_remaining)
        if key in self._emitted_thresholds:
            return None
        self._emitted_thresholds.add(key)
        return warning


def remaining_full_days(
    expires_at: datetime,
    *,
    now: datetime | None = None,
) -> int:
    """Return non-negative complete 24-hour periods until expiration."""

    current_time = datetime.now(UTC) if now is None else now
    if expires_at.tzinfo is None:
        raise ValueError("expires_at must be timezone-aware")
    if current_time.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    remaining_seconds = (
        expires_at.astimezone(UTC) - current_time.astimezone(UTC)
    ).total_seconds()
    return max(0, int(remaining_seconds // SECONDS_PER_DAY))


def credential_status(
    expires_at: datetime,
    *,
    now: datetime | None = None,
) -> CredentialStatus:
    """Classify expiry using the operational warning boundaries."""

    current_time = datetime.now(UTC) if now is None else now
    if expires_at.tzinfo is None:
        raise ValueError("expires_at must be timezone-aware")
    if current_time.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if current_time.astimezone(UTC) >= expires_at.astimezone(UTC):
        return CredentialStatus.EXPIRED

    days_remaining = remaining_full_days(expires_at, now=current_time)
    if days_remaining <= CRITICAL_THRESHOLD_DAYS:
        return CredentialStatus.CRITICAL
    if days_remaining <= WARNING_THRESHOLD_DAYS:
        return CredentialStatus.WARNING
    return CredentialStatus.OK


def credential_expiry_warning(
    expires_at: datetime,
    *,
    now: datetime | None = None,
) -> CredentialExpiryWarning | None:
    """Build a warning when the expiry reaches a configured day threshold."""

    current_time = datetime.now(UTC) if now is None else now
    days_remaining = remaining_full_days(expires_at, now=current_time)
    if days_remaining not in WARNING_DAYS:
        return None
    return CredentialExpiryWarning(
        days_remaining=days_remaining,
        status=credential_status(expires_at, now=current_time),
        expires_at=expires_at,
    )
