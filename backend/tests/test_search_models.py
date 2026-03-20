from nobla.tools.search.models import SearchResult, SearchMode, Citation


def test_search_result_creation():
    r = SearchResult(title="Test", url="https://example.com", snippet="A test result", score=0.9)
    assert r.title == "Test"
    assert r.score == 0.9


def test_search_mode_enum():
    assert SearchMode.QUICK.value == "quick"
    assert SearchMode.DEEP.value == "deep"
    assert SearchMode.WIDE.value == "wide"
    assert SearchMode.DEEP_WIDE.value == "deep_wide"


def test_citation():
    c = Citation(index=1, title="Source", url="https://example.com", snippet="relevant text")
    assert c.index == 1


def test_search_result_to_dict():
    r = SearchResult(title="T", url="https://x.com", snippet="S", score=0.5)
    d = r.to_dict()
    assert d["title"] == "T"
    assert d["url"] == "https://x.com"
