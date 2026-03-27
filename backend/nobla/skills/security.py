"""Skill security scanner — validates skills before installation.

Spec reference: Phase 5-Foundation §4.3 — Security Scanner.

Checks:
1. Pattern matching: network calls, file system access, env var reads
2. Dependency check: known malicious packages
3. Permission escalation: does it claim higher tier than justified?
4. Sandbox dry-run: execute with mock data, 10-second hard timeout
   (dry-run wired in Phase 5A when sandbox integration is ready)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from nobla.security.permissions import Tier
from nobla.skills.models import SkillManifest

logger = logging.getLogger(__name__)

# Suspicious patterns in skill source code
SUSPICIOUS_PATTERNS: list[tuple[str, str]] = [
    (r"\bos\.environ\b", "Accesses environment variables"),
    (r"\bos\.system\b", "Direct system command execution"),
    (r"\bsubprocess\b", "Subprocess execution"),
    (r"\b__import__\b", "Dynamic import"),
    (r"\beval\s*\(", "eval() usage"),
    (r"\bexec\s*\(", "exec() usage"),
    (r"\bopen\s*\(.*(w|a|x)", "File write access"),
    (r"\bsocket\b", "Raw socket access"),
    (r"\brequests\.(get|post|put|delete|patch)\b", "HTTP requests"),
    (r"\burllib\b", "URL library usage"),
    (r"\bctypes\b", "C-type foreign function interface"),
]

# Known malicious or vulnerable packages
BLOCKED_PACKAGES: set[str] = {
    "evil-package",
    "malicious-lib",
    "cryptominer",
    # Real entries would come from a maintained blocklist
}

# Maximum tier a skill can request without being flagged
MAX_UNRESTRICTED_TIER = Tier.STANDARD


@dataclass(slots=True)
class ScanResult:
    """Result of a security scan."""

    passed: bool
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    patterns_found: list[str] = field(default_factory=list)


class SkillSecurityScanner:
    """Validates skills for security concerns before installation."""

    def __init__(
        self,
        blocked_packages: set[str] | None = None,
        suspicious_patterns: list[tuple[str, str]] | None = None,
        max_unrestricted_tier: Tier = MAX_UNRESTRICTED_TIER,
    ) -> None:
        self._blocked = blocked_packages or BLOCKED_PACKAGES
        self._patterns = suspicious_patterns or SUSPICIOUS_PATTERNS
        self._max_tier = max_unrestricted_tier

    async def scan(
        self, manifest: SkillManifest, source_code: str | None = None
    ) -> ScanResult:
        """Run all security checks on a skill.

        Args:
            manifest: The skill's parsed manifest.
            source_code: Optional source code string for pattern analysis.
        """
        issues: list[str] = []
        warnings: list[str] = []
        patterns_found: list[str] = []

        # Check 1: Dependency blocklist
        self._check_dependencies(manifest, issues)

        # Check 2: Permission escalation
        self._check_tier_escalation(manifest, issues, warnings)

        # Check 3: Source code patterns (if source available)
        if source_code:
            self._check_patterns(source_code, manifest, patterns_found, warnings)

        # Check 4: Manifest sanity
        self._check_manifest_sanity(manifest, issues)

        passed = len(issues) == 0

        result = ScanResult(
            passed=passed,
            issues=issues,
            warnings=warnings,
            patterns_found=patterns_found,
        )

        if not passed:
            logger.warning(
                "Skill '%s' failed security scan: %s",
                manifest.name,
                "; ".join(issues),
            )
        elif warnings:
            logger.info(
                "Skill '%s' passed with warnings: %s",
                manifest.name,
                "; ".join(warnings),
            )

        return result

    def _check_dependencies(
        self, manifest: SkillManifest, issues: list[str]
    ) -> None:
        """Check for known malicious dependencies."""
        for dep in manifest.dependencies:
            # Normalize: strip version specifiers
            pkg_name = re.split(r"[><=!~]", dep)[0].strip().lower()
            if pkg_name in self._blocked:
                issues.append(f"Blocked dependency: {pkg_name}")

    def _check_tier_escalation(
        self,
        manifest: SkillManifest,
        issues: list[str],
        warnings: list[str],
    ) -> None:
        """Flag skills requesting higher tier than justified."""
        if manifest.tier > self._max_tier:
            warnings.append(
                f"Skill requests {manifest.tier.name} tier "
                f"(above {self._max_tier.name} threshold)"
            )
        if manifest.tier == Tier.ADMIN and not manifest.requires_approval:
            issues.append("ADMIN tier skill must require approval")

    def _check_patterns(
        self,
        source_code: str,
        manifest: SkillManifest,
        patterns_found: list[str],
        warnings: list[str],
    ) -> None:
        """Scan source code for suspicious patterns."""
        for pattern, description in self._patterns:
            if re.search(pattern, source_code):
                patterns_found.append(description)
                warnings.append(f"Suspicious pattern: {description}")

    def _check_manifest_sanity(
        self, manifest: SkillManifest, issues: list[str]
    ) -> None:
        """Basic manifest validation."""
        if not manifest.name:
            issues.append("Skill name is empty")
        if not manifest.description:
            issues.append("Skill description is empty")
        if not manifest.id:
            issues.append("Skill ID is empty")
        if manifest.enabled:
            issues.append("Skill must not be pre-enabled (enabled must be false)")
