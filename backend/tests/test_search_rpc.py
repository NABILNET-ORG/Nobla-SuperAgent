import pytest

from nobla.tools.search.models import SearchMode


def test_search_mode_values():
    assert SearchMode("quick") == SearchMode.QUICK
    assert SearchMode("deep") == SearchMode.DEEP
    assert SearchMode("wide") == SearchMode.WIDE
    assert SearchMode("deep_wide") == SearchMode.DEEP_WIDE


def test_search_mode_invalid():
    with pytest.raises(ValueError):
        SearchMode("invalid")
