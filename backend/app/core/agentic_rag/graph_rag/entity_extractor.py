"""LLM-based entity and relationship extraction from document chunks.

Extracts (subject, predicate, object) triples from text using LLM,
with entity type classification. Designed for batch processing to
minimize LLM API calls.
"""
import json
import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)

MAX_TRIPLES_PER_CHUNK = 10
BATCH_CHUNKS = 3  # Process N chunks per LLM call


@dataclass
class EntityTripleData:
    """A single extracted triple."""
    subject: str
    predicate: str
    object: str
    subject_type: str = "ENTITY"    # PERSON | ORG | CONCEPT | LOCATION | EVENT | ENTITY
    object_type: str = "ENTITY"
    confidence: float = 0.8
    source_chunk_index: int = 0


_EXTRACTION_PROMPT = """从以下文本中提取实体和关系。识别关键的实体（人物、组织、概念、地点、事件等）及其之间的关系。

文本：
{text}

规则：
1. 每个三元组包含：subject(主体)、predicate(关系)、object(客体)
2. subject_type/object_type 取值：PERSON, ORG, CONCEPT, LOCATION, EVENT, PRODUCT, TECH
3. predicate 使用简洁的中文或英文动词短语（如"属于"、"开发了"、"位于"）
4. 只提取文本中明确提到的关系，不要推测
5. 最多提取 {max_triples} 个最重要的三元组
6. confidence 为 0.5-1.0 的置信度

严格按 JSON 格式输出（不要输出其他内容）：
{{
  "triples": [
    {{
      "subject": "实体A",
      "predicate": "关系",
      "object": "实体B",
      "subject_type": "ORG",
      "object_type": "PRODUCT",
      "confidence": 0.9
    }}
  ]
}}"""


async def extract_triples_from_chunks(
    chunks: List[str],
    chunk_indices: List[int],
    llm_config,
) -> List[EntityTripleData]:
    """Extract entity-relationship triples from document chunks.

    Processes chunks in batches to minimize LLM calls. Each batch
    produces multiple triples.

    Args:
        chunks: List of chunk text content.
        chunk_indices: Corresponding chunk indices in the document.
        llm_config: LLM model configuration for extraction.

    Returns:
        List of extracted EntityTripleData.
    """
    from app.core.llm_client import chat_completion

    all_triples: List[EntityTripleData] = []

    # Process in batches
    for i in range(0, len(chunks), BATCH_CHUNKS):
        batch_texts = chunks[i:i + BATCH_CHUNKS]
        batch_indices = chunk_indices[i:i + BATCH_CHUNKS]

        combined_text = "\n\n---\n\n".join(
            f"[片段 {idx}]\n{text[:1500]}" for idx, text in zip(batch_indices, batch_texts)
        )

        prompt = _EXTRACTION_PROMPT.replace("{text}", combined_text)
        prompt = prompt.replace("{max_triples}", str(MAX_TRIPLES_PER_CHUNK * len(batch_texts)))

        messages = [
            {"role": "system", "content": "你是知识图谱实体关系提取专家。只输出 JSON。"},
            {"role": "user", "content": prompt},
        ]

        try:
            result = await chat_completion(llm_config, messages, stream=False)
            result_text = result.strip()

            if "```" in result_text:
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
                result_text = result_text.strip()

            parsed = json.loads(result_text)
            raw_triples = parsed.get("triples", [])

            for t in raw_triples:
                subj = (t.get("subject") or "").strip()
                pred = (t.get("predicate") or "").strip()
                obj = (t.get("object") or "").strip()
                if not subj or not pred or not obj:
                    continue

                # Determine source chunk index (use first chunk in batch as default)
                src_idx = batch_indices[0]

                confidence = float(t.get("confidence", 0.8))
                confidence = max(0.0, min(1.0, confidence))

                all_triples.append(EntityTripleData(
                    subject=subj[:200],
                    predicate=pred[:100],
                    object=obj[:200],
                    subject_type=_validate_type(t.get("subject_type", "ENTITY")),
                    object_type=_validate_type(t.get("object_type", "ENTITY")),
                    confidence=confidence,
                    source_chunk_index=src_idx,
                ))

        except Exception as exc:
            logger.warning("Entity extraction failed for batch at index %d: %s", i, exc)
            continue

    logger.info("Extracted %d triples from %d chunks", len(all_triples), len(chunks))
    return all_triples


_VALID_TYPES = {"PERSON", "ORG", "CONCEPT", "LOCATION", "EVENT", "PRODUCT", "TECH", "ENTITY"}


def _validate_type(t: str) -> str:
    t = (t or "ENTITY").upper().strip()
    return t if t in _VALID_TYPES else "ENTITY"
