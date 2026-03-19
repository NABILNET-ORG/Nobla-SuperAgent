"""Lightweight NER + keyword extraction for the hot path.

No LLM calls. Uses spaCy for NER (optional) and TF-IDF for keywords.
Graceful degradation: if spaCy is not available, skip NER.
"""

from __future__ import annotations

import logging
from typing import Optional

from sklearn.feature_extraction.text import TfidfVectorizer

logger = logging.getLogger(__name__)


class ExtractionEngine:
    """Extracts entities and keywords from text without LLM calls."""

    ENTITY_TYPE_MAP = {
        "PERSON": "PERSON",
        "ORG": "ORGANIZATION",
        "GPE": "LOCATION",
        "LOC": "LOCATION",
        "DATE": "DATE",
        "PRODUCT": "TOOL",
    }

    def __init__(self, spacy_model: Optional[str] = "en_core_web_sm"):
        self.nlp = None
        if spacy_model:
            try:
                import spacy
                self.nlp = spacy.load(spacy_model)
                logger.info("spaCy model '%s' loaded", spacy_model)
            except Exception as e:
                logger.warning("spaCy not available, NER disabled: %s", e)

        self._tfidf = TfidfVectorizer(
            max_features=20,
            stop_words="english",
            ngram_range=(1, 2),
        )

    def extract_keywords(self, text: str, top_k: int = 10) -> list[str]:
        """Extract top-K keywords using TF-IDF."""
        if not text or len(text.strip()) < 5:
            return []
        try:
            tfidf_matrix = self._tfidf.fit_transform([text])
            feature_names = self._tfidf.get_feature_names_out()
            scores = tfidf_matrix.toarray()[0]
            ranked = sorted(
                zip(feature_names, scores), key=lambda x: x[1], reverse=True
            )
            return [word for word, score in ranked[:top_k] if score > 0]
        except Exception as e:
            logger.warning("Keyword extraction failed: %s", e)
            return []

    def extract_entities(self, text: str) -> list[dict]:
        """Extract named entities using spaCy. Returns [] if spaCy unavailable."""
        if self.nlp is None or not text:
            return []
        try:
            doc = self.nlp(text)
            entities = []
            seen = set()
            for ent in doc.ents:
                key = (ent.text.lower(), ent.label_)
                if key not in seen:
                    seen.add(key)
                    entities.append({
                        "text": ent.text,
                        "type": self.ENTITY_TYPE_MAP.get(ent.label_, ent.label_),
                        "start": ent.start_char,
                        "end": ent.end_char,
                    })
            return entities
        except Exception as e:
            logger.warning("NER extraction failed: %s", e)
            return []

    def extract(self, text: str) -> dict:
        """Run full extraction pipeline. Returns keywords + entities."""
        return {
            "keywords": self.extract_keywords(text),
            "entities": self.extract_entities(text),
        }
