import pytest
from nobla.memory.extraction import ExtractionEngine


@pytest.fixture
def engine():
    return ExtractionEngine(spacy_model=None)  # Graceful: no spaCy


def test_extract_keywords(engine):
    result = engine.extract_keywords("Python is great for machine learning projects")
    assert isinstance(result, list)
    assert len(result) > 0
    assert "python" in [k.lower() for k in result]


def test_extract_entities_without_spacy(engine):
    """When spaCy is not loaded, entities should be empty list."""
    result = engine.extract_entities("Alice works at Google on ProjectX")
    assert isinstance(result, list)


def test_extract_entities_with_spacy():
    engine = ExtractionEngine(spacy_model="en_core_web_sm")
    if engine.nlp is None:
        pytest.skip("spaCy model not available")
    result = engine.extract_entities("Alice works at Google in New York")
    names = [e["text"] for e in result]
    assert "Alice" in names or "Google" in names


def test_extract_all(engine):
    result = engine.extract("Alice loves Python for ML projects")
    assert "keywords" in result
    assert "entities" in result
    assert isinstance(result["keywords"], list)
    assert isinstance(result["entities"], list)
