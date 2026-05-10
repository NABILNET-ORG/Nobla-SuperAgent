"""Slack Enterprise Grid settings + user-context tests (Phase 5-Channels).

New focused test module per the v2.1.6 Boy Scout Exception — extending
the Slack adapter for Grid mode lands ALL new tests in dedicated, ceiling-
respecting files instead of compounding the grandfathered
test_slack_adapter.py (~1,500 lines, frozen for surgical Edit only).

Covers:
  - SlackSettings: enterprise_grid + org_token + team_ids fields and
    the validate_tokens model_validator gating.
  - SlackUserContext: enterprise_id field for Grid org routing.
"""

from __future__ import annotations

import pytest

from nobla.config.settings import SlackSettings


class TestSlackEnterpriseGridSettings:
    def test_enterprise_grid_default_false(self):
        s = SlackSettings()
        assert s.enterprise_grid is False

    def test_org_token_default_empty(self):
        s = SlackSettings()
        assert s.org_token == ""

    def test_team_ids_default_empty(self):
        s = SlackSettings()
        assert s.team_ids == []

    def test_grid_disabled_allows_empty_org_fields(self):
        s = SlackSettings(enabled=False, enterprise_grid=False)
        assert s.enterprise_grid is False
        assert s.org_token == ""

    def test_grid_enabled_requires_org_token(self):
        with pytest.raises(Exception):
            SlackSettings(
                enabled=True, bot_token="xoxb-x", app_token="xapp-x",
                mode="socket", enterprise_grid=True, team_ids=["T1"],
            )

    def test_grid_enabled_requires_team_ids(self):
        with pytest.raises(Exception):
            SlackSettings(
                enabled=True, bot_token="xoxb-x", app_token="xapp-x",
                mode="socket", enterprise_grid=True, org_token="xoxa-org",
            )

    def test_grid_enabled_still_requires_bot_token(self):
        with pytest.raises(Exception):
            SlackSettings(
                enabled=True, mode="socket", enterprise_grid=True,
                org_token="xoxa-org", team_ids=["T1"],
            )

    def test_grid_valid_full_socket_config(self):
        s = SlackSettings(
            enabled=True, bot_token="xoxb-x", app_token="xapp-x",
            mode="socket", enterprise_grid=True,
            org_token="xoxa-org-token", team_ids=["T1", "T2"],
        )
        assert s.enterprise_grid is True
        assert s.org_token == "xoxa-org-token"
        assert s.team_ids == ["T1", "T2"]

    def test_grid_valid_full_events_config(self):
        s = SlackSettings(
            enabled=True, bot_token="xoxb-x", signing_secret="sec",
            mode="events", enterprise_grid=True,
            org_token="xoxa-org-token", team_ids=["T1"],
        )
        assert s.enterprise_grid is True
        assert s.team_ids == ["T1"]

    def test_team_ids_accepts_multiple_workspaces(self):
        s = SlackSettings(
            enabled=True, bot_token="xoxb-x", app_token="xapp-x",
            mode="socket", enterprise_grid=True,
            org_token="xoxa-org-token",
            team_ids=["T1", "T2", "T3", "T4"],
        )
        assert len(s.team_ids) == 4
