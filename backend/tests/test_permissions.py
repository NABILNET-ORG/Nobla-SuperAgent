import pytest
from nobla.security.permissions import Tier, PermissionChecker, InsufficientPermissions


def test_tier_ordering():
    assert Tier.SAFE < Tier.STANDARD < Tier.ELEVATED < Tier.ADMIN


def test_tier_from_int():
    assert Tier(1) == Tier.SAFE
    assert Tier(4) == Tier.ADMIN


def test_permission_check_passes():
    checker = PermissionChecker()
    checker.check(current_tier=Tier.STANDARD, required_tier=Tier.STANDARD)  # no exception


def test_permission_check_fails():
    checker = PermissionChecker()
    with pytest.raises(InsufficientPermissions) as exc_info:
        checker.check(current_tier=Tier.SAFE, required_tier=Tier.STANDARD)
    assert exc_info.value.required_tier == Tier.STANDARD
    assert exc_info.value.current_tier == Tier.SAFE


def test_escalation_tier2_no_passphrase():
    checker = PermissionChecker(escalation_requires_passphrase=[3, 4])
    assert checker.requires_passphrase_for_escalation(2) is False


def test_escalation_tier3_requires_passphrase():
    checker = PermissionChecker(escalation_requires_passphrase=[3, 4])
    assert checker.requires_passphrase_for_escalation(3) is True
    assert checker.requires_passphrase_for_escalation(4) is True
