import pytest
from nobla.security.costs import CostTracker, BudgetExceeded


@pytest.fixture
def tracker():
    return CostTracker(daily_limit=5.0, monthly_limit=50.0, session_limit=1.0, warning_threshold=0.8)


def test_initial_spend(tracker):
    assert tracker.session_spend == 0.0


def test_record_spend(tracker):
    tracker.record(0.50)
    assert tracker.session_spend == 0.50


def test_session_limit_exceeded(tracker):
    tracker.record(0.90)
    with pytest.raises(BudgetExceeded, match="(?i)session"):
        tracker.check_budget(estimated_cost=0.20)


def test_session_limit_exact(tracker):
    tracker.record(0.80)
    tracker.check_budget(estimated_cost=0.20)  # exactly at limit, should pass


def test_warning_at_threshold(tracker):
    tracker.record(0.80)  # 80% of 1.0
    warnings = tracker.get_warnings()
    assert any("session" in w for w in warnings)


def test_no_warning_below_threshold(tracker):
    tracker.record(0.50)
    warnings = tracker.get_warnings()
    assert len(warnings) == 0


def test_get_dashboard(tracker):
    tracker.record(0.42)
    data = tracker.get_dashboard()
    assert data["session_usd"] == 0.42
    assert data["limits"]["session"] == 1.0


def test_set_daily_spend(tracker):
    tracker.set_daily_spend(4.50)
    with pytest.raises(BudgetExceeded, match="(?i)daily"):
        tracker.check_budget(estimated_cost=0.60)
