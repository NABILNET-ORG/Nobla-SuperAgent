"""Tests for Phase 5B.2 SkillPackager — archive/manifest validation, hashing."""

from __future__ import annotations

import json
import io
import zipfile

import pytest

from nobla.marketplace.packager import SkillPackager


@pytest.fixture
def packager():
    return SkillPackager()


def _create_archive(manifest: dict, skill_code: str = "pass") -> bytes:
    """Create a .nobla zip archive in memory and return bytes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("nobla-skill.json", json.dumps(manifest))
        zf.writestr("skill.py", skill_code)
    return buf.getvalue()


def _valid_manifest():
    return {
        "name": "test-skill",
        "version": "1.0.0",
        "description": "A test skill",
        "category": "utilities",
    }


class TestValidateManifest:
    def test_valid_manifest(self, packager):
        result = packager.validate_manifest(_valid_manifest())
        assert result.valid is True
        assert result.issues == []

    def test_missing_name(self, packager):
        m = _valid_manifest()
        del m["name"]
        result = packager.validate_manifest(m)
        assert result.valid is False
        assert any("name" in i.lower() for i in result.issues)

    def test_missing_version(self, packager):
        m = _valid_manifest()
        del m["version"]
        result = packager.validate_manifest(m)
        assert result.valid is False

    def test_missing_description(self, packager):
        m = _valid_manifest()
        del m["description"]
        result = packager.validate_manifest(m)
        assert result.valid is False

    def test_invalid_semver(self, packager):
        m = _valid_manifest()
        m["version"] = "not-a-version"
        result = packager.validate_manifest(m)
        assert result.valid is False
        assert any("version" in i.lower() or "semver" in i.lower() for i in result.issues)

    def test_valid_semver_variants(self, packager):
        for v in ["0.1.0", "1.0.0", "10.20.30"]:
            m = _valid_manifest()
            m["version"] = v
            assert packager.validate_manifest(m).valid is True


class TestValidateArchive:
    def test_valid_archive(self, packager):
        data = _create_archive(_valid_manifest())
        result = packager.validate_archive(data)
        assert result.valid is True

    def test_invalid_zip(self, packager):
        result = packager.validate_archive(b"not a zip file")
        assert result.valid is False
        assert any("zip" in i.lower() or "archive" in i.lower() for i in result.issues)

    def test_missing_manifest_in_archive(self, packager):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("skill.py", "pass")
        result = packager.validate_archive(buf.getvalue())
        assert result.valid is False
        assert any("manifest" in i.lower() or "nobla-skill.json" in i.lower() for i in result.issues)

    def test_invalid_manifest_in_archive(self, packager):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("nobla-skill.json", "not json")
        result = packager.validate_archive(buf.getvalue())
        assert result.valid is False


class TestExtractManifest:
    def test_extracts_manifest(self, packager):
        manifest = _valid_manifest()
        data = _create_archive(manifest)
        result = packager.extract_manifest(data)
        assert result["name"] == "test-skill"
        assert result["version"] == "1.0.0"


class TestComputeHash:
    def test_hash_is_sha256_hex(self, packager):
        h = packager.compute_hash(b"hello world")
        assert len(h) == 64  # SHA-256 hex

    def test_same_input_same_hash(self, packager):
        h1 = packager.compute_hash(b"data")
        h2 = packager.compute_hash(b"data")
        assert h1 == h2

    def test_different_input_different_hash(self, packager):
        h1 = packager.compute_hash(b"data1")
        h2 = packager.compute_hash(b"data2")
        assert h1 != h2


class TestArchiveSize:
    def test_oversized_archive_rejected(self, packager):
        packager.max_archive_size_mb = 0.001  # ~1KB limit
        data = _create_archive(_valid_manifest(), skill_code="x" * 10000)
        result = packager.validate_archive(data)
        assert result.valid is False
        assert any("size" in i.lower() for i in result.issues)
