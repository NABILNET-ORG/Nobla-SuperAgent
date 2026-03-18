from __future__ import annotations
import structlog

logger = structlog.get_logger()


class BudgetExceeded(Exception):
    def __init__(self, period: str, limit: float, spent: float):
        self.period = period
        self.limit = limit
        self.spent = spent
        super().__init__(f"{period.capitalize()} budget exceeded: ${spent:.2f} / ${limit:.2f}")


class CostTracker:
    def __init__(self, daily_limit: float = 5.0, monthly_limit: float = 50.0,
                 session_limit: float = 1.0, warning_threshold: float = 0.8):
        self.daily_limit = daily_limit
        self.monthly_limit = monthly_limit
        self.session_limit = session_limit
        self.warning_threshold = warning_threshold
        self.session_spend: float = 0.0
        self._daily_spend: float = 0.0
        self._monthly_spend: float = 0.0

    def record(self, cost_usd: float) -> None:
        self.session_spend += cost_usd
        self._daily_spend += cost_usd
        self._monthly_spend += cost_usd

    def set_daily_spend(self, amount: float) -> None:
        self._daily_spend = amount

    def set_monthly_spend(self, amount: float) -> None:
        self._monthly_spend = amount

    def check_budget(self, estimated_cost: float = 0.0) -> None:
        checks = [
            ("session", self.session_spend + estimated_cost, self.session_limit),
            ("daily", self._daily_spend + estimated_cost, self.daily_limit),
            ("monthly", self._monthly_spend + estimated_cost, self.monthly_limit),
        ]
        for period, projected, limit in checks:
            if projected > limit:
                raise BudgetExceeded(period, limit, projected)

    def get_warnings(self) -> list[str]:
        warnings = []
        checks = [
            ("session", self.session_spend, self.session_limit),
            ("daily", self._daily_spend, self.daily_limit),
            ("monthly", self._monthly_spend, self.monthly_limit),
        ]
        for period, spent, limit in checks:
            if limit > 0 and spent >= self.warning_threshold * limit:
                warnings.append(f"{period}: ${spent:.2f} / ${limit:.2f} ({spent/limit*100:.0f}%)")
        return warnings

    def get_dashboard(self) -> dict:
        return {
            "session_usd": self.session_spend,
            "daily_usd": self._daily_spend,
            "monthly_usd": self._monthly_spend,
            "limits": {
                "session": self.session_limit,
                "daily": self.daily_limit,
                "monthly": self.monthly_limit,
            },
            "warnings": self.get_warnings(),
        }
