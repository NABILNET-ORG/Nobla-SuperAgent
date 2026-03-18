from __future__ import annotations
import enum


class Tier(enum.IntEnum):
    SAFE = 1
    STANDARD = 2
    ELEVATED = 3
    ADMIN = 4


class InsufficientPermissions(Exception):
    def __init__(self, required_tier: Tier, current_tier: Tier):
        self.required_tier = required_tier
        self.current_tier = current_tier
        super().__init__(f"Requires tier {required_tier.name}, current: {current_tier.name}")


class PermissionChecker:
    def __init__(self, escalation_requires_passphrase: list[int] | None = None):
        self.escalation_requires_passphrase = escalation_requires_passphrase or [3, 4]

    def check(self, current_tier: Tier, required_tier: Tier) -> None:
        if current_tier < required_tier:
            raise InsufficientPermissions(required_tier, current_tier)

    def requires_passphrase_for_escalation(self, target_tier: int) -> bool:
        return target_tier in self.escalation_requires_passphrase
