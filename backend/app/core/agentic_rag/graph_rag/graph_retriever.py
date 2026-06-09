"""Graph-enhanced retrieval — combines graph traversal with vector search.

Pipeline:
1. Extract entities from query (LLM or keyword matching)
2. Match entities to graph nodes
3. BFS traversal (1-2 hops) to find related entities and source chunks
4. Fetch those chunks from the database
5. Score by graph distance + edge weight
6. Merge with vector retrieval results via RRF fusion
"""
import json
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agentic_rag.graph_rag.graph_store import get_or_build_graph, KnowledgeGraph

logger = logging.getLogger(__name__)


async def graph_retrieve(
    db: AsyncSession,
    kb_id: int,
    query: str,
    top_k: int = 10,
    max_hops: int = 2,
    llm_config=None,
) -> List[Dict[str, Any]]:
    """Retrieve document chunks via knowledge graph traversal.

    Args:
        db: Database session.
        kb_id: Knowledge base ID.
        query: User's query.
        top_k: Maximum results to return.
        max_hops: Graph traversal depth.
        llm_config: LLM config for entity extraction (optional).

    Returns:
        List of dicts matching the raw_results format used by retrieval_service:
        [{content, score, metadata: {doc_id, chunk_index}, doc_name}]
    """
    graph = await get_or_build_graph(db, kb_id)
    if not graph or graph.node_count == 0:
        return []

    # Step 1: Extract entities from query
    query_entities = await _extract_query_entities(query, graph, llm_config)
    if not query_entities:
        return []

    logger.debug("Graph retrieval: query entities = %s", query_entities)

    # Step 2: Traverse graph from matched entities
    all_source_chunks: Dict[Tuple[int, int], float] = {}  # (doc_id, chunk_idx) -> score

    for entity in query_entities:
        neighbors = graph.get_neighbors(entity, max_hops=max_hops)
        # Add the entity's own source chunks (distance=0)
        entity_chunks = graph.get_source_chunks_for_entities([entity])
        for chunk_key in entity_chunks:
            all_source_chunks[chunk_key] = max(all_source_chunks.get(chunk_key, 0), 1.0)

        # Add neighbor chunks with distance-decayed scores
        for neighbor in neighbors:
            distance = neighbor.get("distance", 1)
            weight = neighbor.get("weight", 1.0)
            score = weight / (1 + distance)  # decay by distance
            for chunk_key in neighbor.get("source_chunks", []):
                chunk_key = tuple(chunk_key)
                all_source_chunks[chunk_key] = max(all_source_chunks.get(chunk_key, 0), score)

    if not all_source_chunks:
        return []

    # Step 3: Fetch chunk content from database
    from app.models.document import DocumentChunk, Document, DocumentStatus

    # Sort by score, take top_k * 2 to have room for filtering
    sorted_chunks = sorted(all_source_chunks.items(), key=lambda x: -x[1])[:top_k * 2]

    results = []
    for (doc_id, chunk_idx), graph_score in sorted_chunks:
        row = await db.execute(
            select(DocumentChunk.content, DocumentChunk.kb_id)
            .join(Document, Document.id == DocumentChunk.doc_id)
            .where(
                DocumentChunk.doc_id == doc_id,
                DocumentChunk.chunk_index == chunk_idx,
                Document.status == DocumentStatus.COMPLETED,
            )
        )
        chunk = row.first()
        if not chunk:
            continue

        results.append({
            "content": chunk.content,
            "score": min(graph_score, 1.0),
            "metadata": {"doc_id": doc_id, "chunk_index": chunk_idx},
            "source_type": "graph",
        })

        if len(results) >= top_k:
            break

    logger.info("Graph retrieval for kb_id=%d: %d entities → %d chunks → %d results",
                kb_id, len(query_entities), len(all_source_chunks), len(results))
    return results


async def _extract_query_entities(
    query: str,
    graph: KnowledgeGraph,
    llm_config=None,
) -> List[str]:
    """Extract entity mentions from the query.

    Two strategies:
    1. Fast: keyword matching against graph nodes (no LLM call)
    2. LLM: entity extraction when keyword matching finds nothing
    """
    # Strategy 1: keyword matching against existing graph nodes
    matched = []
    query_lower = query.lower().replace(" ", "")
    for node in graph.graph.nodes:
        node_data = graph._node_data.get(node)
        if not node_data:
            continue
        name_lower = node_data.name.lower().replace(" ", "")
        if name_lower in query_lower or query_lower in name_lower:
            matched.append(node_data.name)
        elif len(name_lower) >= 2 and name_lower in query_lower:
            matched.append(node_data.name)

    if matched:
        return matched[:5]

    # Strategy 2: LLM-based entity extraction (if available)
    if llm_config:
        try:
            return await _llm_extract_entities(query, llm_config)
        except Exception as exc:
            logger.debug("LLM entity extraction failed: %s", exc)

    # Strategy 3: Simple segmentation fallback (Chinese)
    try:
        import jieba
        words = [w for w in jieba.cut(query) if len(w) >= 2]
        matched = []
        for word in words:
            found = graph.find_entity(word)
            if found:
                node_data = graph._node_data.get(found)
                matched.append(node_data.name if node_data else found)
        return matched[:5]
    except ImportError:
        pass

    return []


_ENTITY_EXTRACT_PROMPT = """从以下问题中提取关键实体（人名、组织、概念、产品、技术等）。

问题：{query}

只输出 JSON：{{"entities": ["实体1", "实体2"]}}"""


async def _llm_extract_entities(query: str, llm_config) -> List[str]:
    """Use LLM to extract entities from query."""
    from app.core.llm_client import chat_completion

    prompt = _ENTITY_EXTRACT_PROMPT.replace("{query}", query)
    messages = [
        {"role": "system", "content": "你是实体识别专家。只输出 JSON。"},
        {"role": "user", "content": prompt},
    ]
    result = await chat_completion(llm_config, messages, stream=False)
    result_text = result.strip()
    if "```" in result_text:
        result_text = result_text.split("```")[1]
        if result_text.startswith("json"):
            result_text = result_text[4:]
        result_text = result_text.strip()
    parsed = json.loads(result_text)
    return [e.strip() for e in parsed.get("entities", []) if e.strip()][:5]
