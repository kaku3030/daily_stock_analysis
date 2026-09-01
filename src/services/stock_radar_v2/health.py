"""Provider fallback debounce and deterministic Critical health rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

from .config import StockRadarConfig, load_stock_radar_config
from .notifications import RadarNotifier


class ProviderMode(str, Enum):
    PRIMARY = "primary"
    FALLBACK = "fallback"


class FailureKind(str, Enum):
    TIMEOUT = "timeout"
    EMPTY = "empty"
    PARSE = "parse"
    CONNECTION = "connection_error"
    AUTH = "authentication_error"
    SUBSCRIPTION = "subscription_error"
    CLOSED_BAR_MISSING = "closed_bar_missing"
    TIMESTAMP_MISMATCH = "timestamp_mismatch"
    SESSION_MISMATCH = "session_mismatch"
    OTHER = "other"


@dataclass(frozen=True)
class HealthDecision:
    mode: ProviderMode
    critical: bool
    reason: str
    transitioned: bool = False
    accepted: bool = True


class FallbackStateMachine:
    """Keep provider routing stable while exposing severe data failures."""

    def __init__(
        self,
        config: StockRadarConfig | None = None,
        *,
        notifier: RadarNotifier | None = None,
        primary_name: str = "primary",
        fallback_name: str = "fallback",
    ) -> None:
        self.config = config or load_stock_radar_config()
        self.notifier = notifier or RadarNotifier()
        self.primary_name = primary_name
        self.fallback_name = fallback_name
        self.mode = ProviderMode.PRIMARY
        self.fail_count = 0
        self.recovery_success_count = 0
        self.timeout_streak = 0
        self.empty_parse_streak = 0
        self.closed_bar_integrity_streak = 0
        self.critical = False
        self.fallback_reason: str | None = None
        self.cooldown_until: datetime | None = None
        self.next_health_check_at: datetime | None = None

    @staticmethod
    def _now(value: datetime | None) -> datetime:
        current = value or datetime.now(timezone.utc)
        return current.replace(tzinfo=timezone.utc) if current.tzinfo is None else current

    def record_success(self) -> HealthDecision:
        if self.mode is ProviderMode.FALLBACK:
            return HealthDecision(self.mode, self.critical, "fallback_active", accepted=False)
        self.fail_count = 0
        self.timeout_streak = 0
        self.empty_parse_streak = 0
        self.closed_bar_integrity_streak = 0
        self.critical = False
        return HealthDecision(self.mode, False, "primary_healthy")

    def record_failure(
        self,
        kind: FailureKind,
        *,
        observed_at: datetime | None = None,
        elapsed_seconds: float | None = None,
        error_code: str | None = None,
    ) -> HealthDecision:
        now = self._now(observed_at)
        self.fail_count += 1
        self._update_streaks(kind, elapsed_seconds)
        critical_reason = self._critical_reason(kind, elapsed_seconds, error_code)
        if critical_reason:
            self._set_critical(critical_reason)
        should_fallback = bool(critical_reason) or self.fail_count >= self.config.fallback.fail_count
        transitioned = should_fallback and self.mode is ProviderMode.PRIMARY
        if transitioned:
            self.mode = ProviderMode.FALLBACK
            self.cooldown_until = now + timedelta(seconds=self.config.fallback.cooldown_seconds)
            self.next_health_check_at = now + timedelta(
                seconds=self.config.fallback.health_check_interval_seconds
            )
            self.recovery_success_count = 0
            self.fallback_reason = critical_reason or f"consecutive_failures={self.fail_count}"
            self.notifier.notify(
                "provider_fallback_alert",
                {
                    "from": self.primary_name,
                    "to": self.fallback_name,
                    "reason": self.fallback_reason,
                    "critical": self.critical,
                },
            )
        reason = critical_reason or f"{kind.value}:consecutive_failures={self.fail_count}"
        return HealthDecision(self.mode, self.critical, reason, transitioned=transitioned)

    def health_check_due(self, observed_at: datetime | None = None) -> bool:
        now = self._now(observed_at)
        return bool(
            self.mode is ProviderMode.FALLBACK
            and self.cooldown_until is not None
            and self.next_health_check_at is not None
            and now >= self.cooldown_until
            and now >= self.next_health_check_at
        )

    def record_recovery_probe(
        self,
        success: bool,
        *,
        observed_at: datetime | None = None,
    ) -> HealthDecision:
        now = self._now(observed_at)
        if not self.health_check_due(now):
            return HealthDecision(self.mode, self.critical, "health_check_not_due", accepted=False)
        self.next_health_check_at = now + timedelta(
            seconds=self.config.fallback.health_check_interval_seconds
        )
        if not success:
            self.recovery_success_count = 0
            return HealthDecision(self.mode, self.critical, "primary_recovery_probe_failed")
        self.recovery_success_count += 1
        if self.recovery_success_count < self.config.fallback.recovery_success_count:
            return HealthDecision(
                self.mode,
                self.critical,
                f"recovery_success={self.recovery_success_count}",
            )
        self.mode = ProviderMode.PRIMARY
        self.fail_count = 0
        self.recovery_success_count = 0
        self.timeout_streak = 0
        self.empty_parse_streak = 0
        self.closed_bar_integrity_streak = 0
        self.critical = False
        self.cooldown_until = None
        self.next_health_check_at = None
        self.fallback_reason = None
        return HealthDecision(self.mode, False, "primary_recovered", transitioned=True)

    def _update_streaks(self, kind: FailureKind, elapsed_seconds: float | None) -> None:
        severe_timeout = kind is FailureKind.TIMEOUT and (
            elapsed_seconds is not None
            and elapsed_seconds > self.config.critical.timeout_seconds
        )
        self.timeout_streak = self.timeout_streak + 1 if severe_timeout else 0
        self.empty_parse_streak = (
            self.empty_parse_streak + 1
            if kind in {FailureKind.EMPTY, FailureKind.PARSE}
            else 0
        )
        self.closed_bar_integrity_streak = (
            self.closed_bar_integrity_streak + 1
            if kind
            in {
                FailureKind.CLOSED_BAR_MISSING,
                FailureKind.TIMESTAMP_MISMATCH,
                FailureKind.SESSION_MISMATCH,
            }
            else 0
        )

    def _critical_reason(
        self,
        kind: FailureKind,
        elapsed_seconds: float | None,
        error_code: str | None,
    ) -> str | None:
        if kind in {FailureKind.CONNECTION, FailureKind.AUTH, FailureKind.SUBSCRIPTION}:
            suffix = f":{error_code}" if error_code else ""
            return f"explicit_{kind.value}{suffix}"
        if self.timeout_streak >= self.config.critical.timeout_count:
            return (
                f"timeout>{self.config.critical.timeout_seconds:g}s"
                f"_count={self.timeout_streak}"
            )
        if self.empty_parse_streak >= self.config.critical.empty_or_parse_count:
            return f"empty_or_parse_count={self.empty_parse_streak}"
        if self.closed_bar_integrity_streak >= self.config.critical.closed_bar_integrity_count:
            return f"closed_bar_integrity_count={self.closed_bar_integrity_streak}"
        return None

    def _set_critical(self, reason: str) -> None:
        if not self.critical:
            self.notifier.notify(
                "data_health_alert",
                {"provider": self.primary_name, "severity": "critical", "reason": reason},
            )
        self.critical = True
