"""Phase 5B.2 SkillPackager — archive/manifest validation, SHA-256 hashing."""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile

from nobla.marketplace.models import PackageValidation

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
_REQUIRED_MANIFEST_FIELDS = ("name", "version", "description")
_MANIFEST_FILENAME = "nobla-skill.json"


class SkillPackager:
    def __init__(self, max_archive_size_mb: float = 10.0) -> None:
        self.max_archive_size_mb = max_archive_size_mb

    def validate_manifest(self, manifest: dict) -> PackageValidation:
        issues: list[str] = []
        for field in _REQUIRED_MANIFEST_FIELDS:
            if field not in manifest:
                issues.append(f"Missing required field: {field}")
        if "version" in manifest and not _SEMVER_RE.match(manifest["version"]):
            issues.append(f"Invalid version format (expected semver): {manifest['version']}")
        return PackageValidation(valid=len(issues) == 0, issues=issues)

    def validate_archive(self, data: bytes) -> PackageValidation:
        max_bytes = int(self.max_archive_size_mb * 1024 * 1024)
        if len(data) > max_bytes:
            return PackageValidation(
                valid=False,
                issues=[f"Archive size {len(data)} exceeds limit {max_bytes} bytes"],
            )
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
        except (zipfile.BadZipFile, Exception):
            return PackageValidation(valid=False, issues=["Invalid zip archive"])

        with zf:
            if _MANIFEST_FILENAME not in zf.namelist():
                return PackageValidation(
                    valid=False,
                    issues=[f"Archive missing {_MANIFEST_FILENAME}"],
                )
            try:
                manifest = json.loads(zf.read(_MANIFEST_FILENAME))
            except (json.JSONDecodeError, Exception):
                return PackageValidation(
                    valid=False,
                    issues=[f"Invalid JSON in {_MANIFEST_FILENAME}"],
                )
            return self.validate_manifest(manifest)

    def extract_manifest(self, data: bytes) -> dict:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            return json.loads(zf.read(_MANIFEST_FILENAME))

    def compute_hash(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()
