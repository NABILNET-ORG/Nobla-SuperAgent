"""Warm path consolidation — post-conversation LLM extraction.

Triggered after a conversation pauses/ends. Uses a cheap LLM call to:
1. Summarize the conversation
2. Extract facts (preferences, knowledge, decisions)
3. Extract entities and relationships for the knowledge graph
4. Detect duplicate facts and merge them
"""

from __future__ import annotations

import logging
import uuid as uuid_lib
from typing import Optional

from nobla.memory.episodic import EpisodicMemory
from nobla.memory.semantic import SemanticMemory
from nobla.memory.graph_builder import KnowledgeGraphBuilder
from nobla.memory.extraction import ExtractionEngine

logger = logging.getLogger(__name__)

# Prompt template for LLM-based fact extraction
FACT_EXTRACTION_PROMPT = """Analyze this conversation and extract:
1. A brief summary (1-2 sentences)
2. Key facts about the user's preferences, knowledge, or decisions
3. Named entities mentioned (people, organizations, tools, locations)

Conversation:
{conversation}

Respond in this exact format:
SUMMARY: <summary>
FACTS:
- <fact 1>
- <fact 2>
ENTITIES:
- <name> | <type> | <relationship>
"""


class ConversationConsolidator:
    """Extracts structured knowledge from conversations via warm path."""

    def __init__(
        self,
        extraction_engine: Optional[ExtractionEngine] = None,
    ):
        self._extraction = extraction_engine or ExtractionEngine(spacy_model=None)

    async def consolidate(
        self,
        messages: list,
        user_id: uuid_lib.UUID,
        conversation_id: uuid_lib.UUID,
        episodic: EpisodicMemory,
        semantic: SemanticMemory,
        graph: KnowledgeGraphBuilder,
        llm_router=None,
    ) -> dict:
        """Run full consolidation pipeline on a conversation.

        Returns dict with summary, facts_extracted, entities_extracted counts.
        """
        if not messages:
            return {"summary": "", "facts_extracted": 0, "entities_extracted": 0}

        # Build conversation text
        conversation_text = "\n".join(
            f"{getattr(m, 'role', 'user')}: {getattr(m, 'content', str(m))}"
            for m in messages
        )

        # 1. Extract entities from all messages using NER (no LLM needed)
        all_entities = []
        for msg in messages:
            content = getattr(msg, "content", str(msg))
            extracted = self._extraction.extract(content)
            all_entities.extend(extracted.get("entities", []))

        # 2. Add entities to knowledge graph
        entity_count = 0
        seen_entities = set()
        for ent in all_entities:
            name = ent.get("text", "")
            if name and name.lower() not in seen_entities:
                seen_entities.add(name.lower())
                graph.add_entity(
                    name,
                    entity_type=ent.get("type", "UNKNOWN"),
                )
                entity_count += 1

        # 3. Generate summary (LLM if available, else truncate)
        summary = ""
        if llm_router:
            try:
                from nobla.brain.base_provider import LLMMessage
                prompt = FACT_EXTRACTION_PROMPT.format(
                    conversation=conversation_text[:4000]
                )
                response = await llm_router.route(
                    [LLMMessage(role="user", content=prompt)]
                )
                summary, facts = self._parse_llm_response(response.content)
            except Exception as e:
                logger.warning("LLM consolidation failed: %s", e)
                summary = conversation_text[:200]
                facts = []
        else:
            summary = conversation_text[:200]
            facts = self._extract_facts_heuristic(messages)

        # 4. Store facts in semantic memory
        fact_count = 0
        for fact in facts:
            if not semantic.is_near_duplicate(user_id, fact):
                await semantic.store_fact(
                    user_id=user_id,
                    content=fact,
                    note_type="fact",
                    source_conversation_id=conversation_id,
                )
                fact_count += 1

        # 5. Update conversation summary
        topics = list(seen_entities)[:10]
        await episodic.update_summary(conversation_id, summary, topics)

        logger.info(
            "consolidation_complete",
            conversation_id=str(conversation_id),
            facts=fact_count,
            entities=entity_count,
        )

        return {
            "summary": summary,
            "facts_extracted": fact_count,
            "entities_extracted": entity_count,
        }

    def _parse_llm_response(self, response: str) -> tuple[str, list[str]]:
        """Parse structured LLM response into summary and facts."""
        summary = ""
        facts = []

        for line in response.split("\n"):
            line = line.strip()
            if line.startswith("SUMMARY:"):
                summary = line[len("SUMMARY:"):].strip()
            elif line.startswith("- ") and not line.startswith("- <") and " | " not in line:
                facts.append(line[2:].strip())

        return summary, facts

    def _extract_facts_heuristic(self, messages: list) -> list[str]:
        """Extract facts without LLM using simple heuristics."""
        facts = []
        keywords_set = set()

        for msg in messages:
            content = getattr(msg, "content", str(msg))
            role = getattr(msg, "role", "user")
            if role != "user":
                continue

            extracted = self._extraction.extract(content)
            keywords = extracted.get("keywords", [])

            # Sentences with strong preference/knowledge indicators
            for keyword in keywords:
                if keyword.lower() not in keywords_set:
                    keywords_set.add(keyword.lower())

            # Long user messages likely contain important context
            if len(content) > 50:
                facts.append(content[:200])

        return facts[:10]  # Cap at 10 facts
