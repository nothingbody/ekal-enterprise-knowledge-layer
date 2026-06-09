"""In-memory knowledge graph store backed by NetworkX.

Provides per-KB directed graphs with entity nodes and relationship edges.
Graphs are lazily loaded from the database and cached with TTL-based
invalidation. Designed for KBs up to ~100K nodes/edges.
"""
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

_GRAPH_CACHE_TTL = 600  # 10 minutes
_GRAPH_CACHE_MAX = 16


@dataclass
class GraphNode:
    """An entity node in the knowledge graph."""
    name: str
    entity_type: str
    mention_count: int = 1
    source_chunks: Set[Tuple[int, int]] = field(default_factory=set)  # (doc_id, chunk_index)


@dataclass
class GraphEdge:
    """A relationship edge in the knowledge graph."""
    predicate: str
    weight: float = 1.0
    source_chunks: Set[Tuple[int, int]] = field(default_factory=set)


class KnowledgeGraph:
    """Per-KB knowledge graph using NetworkX DiGraph."""

    def __init__(self, kb_id: int):
        import networkx as nx
        self.kb_id = kb_id
        self.graph = nx.DiGraph()
        self._node_data: Dict[str, GraphNode] = {}

    def add_triple(
        self,
        subject: str,
        predicate: str,
        obj: str,
        subject_type: str = "ENTITY",
        object_type: str = "ENTITY",
        doc_id: int = 0,
        chunk_index: int = 0,
        confidence: float = 0.8,
    ) -> None:
        """Add a triple to the graph."""
        subj_key = _normalize_entity(subject)
        obj_key = _normalize_entity(obj)
        source = (doc_id, chunk_index)

        # Add/update subject node
        if subj_key not in self._node_data:
            self._node_data[subj_key] = GraphNode(name=subject, entity_type=subject_type)
            self.graph.add_node(subj_key, type=subject_type, label=subject)
        self._node_data[subj_key].mention_count += 1
        self._node_data[subj_key].source_chunks.add(source)

        # Add/update object node
        if obj_key not in self._node_data:
            self._node_data[obj_key] = GraphNode(name=obj, entity_type=object_type)
            self.graph.add_node(obj_key, type=object_type, label=obj)
        self._node_data[obj_key].mention_count += 1
        self._node_data[obj_key].source_chunks.add(source)

        # Add/update edge
        if self.graph.has_edge(subj_key, obj_key):
            edge = self.graph[subj_key][obj_key]
            edge["weight"] = edge.get("weight", 1.0) + confidence
            edge.setdefault("predicates", []).append(predicate)
            edge.setdefault("sources", set()).add(source)
        else:
            self.graph.add_edge(
                subj_key, obj_key,
                predicate=predicate,
                predicates=[predicate],
                weight=confidence,
                sources={source},
            )

    def find_entity(self, query: str) -> Optional[str]:
        """Find the best matching entity node for a query string."""
        query_key = _normalize_entity(query)
        if query_key in self.graph:
            return query_key
        # Fuzzy match: find nodes containing the query
        for node in self.graph.nodes:
            if query_key in node or node in query_key:
                return node
        return None

    def get_neighbors(self, entity: str, max_hops: int = 2) -> List[Dict[str, Any]]:
        """Get all entities within max_hops of the given entity.

        Returns list of dicts with: entity, type, distance, predicate, source_chunks
        """
        import networkx as nx

        entity_key = self.find_entity(entity)
        if not entity_key:
            return []

        results = []
        visited = {entity_key}

        # BFS traversal
        queue = [(entity_key, 0)]
        while queue:
            current, depth = queue.pop(0)
            if depth >= max_hops:
                continue

            # Outgoing edges
            for neighbor in self.graph.successors(current):
                if neighbor not in visited:
                    visited.add(neighbor)
                    edge = self.graph[current][neighbor]
                    node_data = self._node_data.get(neighbor)
                    results.append({
                        "entity": node_data.name if node_data else neighbor,
                        "type": node_data.entity_type if node_data else "ENTITY",
                        "distance": depth + 1,
                        "predicate": edge.get("predicate", "related"),
                        "source_chunks": list(node_data.source_chunks)[:10] if node_data else [],
                        "weight": edge.get("weight", 1.0),
                    })
                    queue.append((neighbor, depth + 1))

            # Incoming edges
            for neighbor in self.graph.predecessors(current):
                if neighbor not in visited:
                    visited.add(neighbor)
                    edge = self.graph[neighbor][current]
                    node_data = self._node_data.get(neighbor)
                    results.append({
                        "entity": node_data.name if node_data else neighbor,
                        "type": node_data.entity_type if node_data else "ENTITY",
                        "distance": depth + 1,
                        "predicate": edge.get("predicate", "related") + "(反向)",
                        "source_chunks": list(node_data.source_chunks)[:10] if node_data else [],
                        "weight": edge.get("weight", 1.0),
                    })
                    queue.append((neighbor, depth + 1))

        # Sort by weight (most connected first)
        results.sort(key=lambda x: (-x["weight"], x["distance"]))
        return results

    def get_source_chunks_for_entities(self, entities: List[str]) -> Set[Tuple[int, int]]:
        """Get all source chunk (doc_id, chunk_index) pairs for given entities."""
        chunks = set()
        for entity in entities:
            key = self.find_entity(entity)
            if key and key in self._node_data:
                chunks.update(self._node_data[key].source_chunks)
        return chunks

    @property
    def node_count(self) -> int:
        return self.graph.number_of_nodes()

    @property
    def edge_count(self) -> int:
        return self.graph.number_of_edges()


def _normalize_entity(name: str) -> str:
    """Normalize entity name for matching."""
    return name.strip().lower().replace(" ", "").replace("　", "")


# ---------------------------------------------------------------------------
# Graph cache — one graph per KB, lazily loaded
# ---------------------------------------------------------------------------

_graph_cache: OrderedDict[int, Tuple[KnowledgeGraph, float]] = OrderedDict()


async def get_or_build_graph(db, kb_id: int) -> Optional[KnowledgeGraph]:
    """Get cached graph or build from database."""
    # Check cache
    cached = _graph_cache.get(kb_id)
    if cached:
        graph, ts = cached
        if time.monotonic() - ts < _GRAPH_CACHE_TTL:
            _graph_cache.move_to_end(kb_id)
            return graph
        _graph_cache.pop(kb_id, None)

    # Build from database
    try:
        from sqlalchemy import select
        from app.models.entity_triple import EntityTriple

        result = await db.execute(
            select(EntityTriple).where(EntityTriple.kb_id == kb_id)
        )
        triples = list(result.scalars().all())

        if not triples:
            return None

        graph = KnowledgeGraph(kb_id)
        for t in triples:
            graph.add_triple(
                subject=t.subject,
                predicate=t.predicate,
                obj=t.object,
                subject_type=t.subject_type,
                object_type=t.object_type,
                doc_id=t.doc_id,
                chunk_index=t.chunk_index,
                confidence=t.confidence or 0.8,
            )

        # Cache
        _graph_cache[kb_id] = (graph, time.monotonic())
        if len(_graph_cache) > _GRAPH_CACHE_MAX:
            _graph_cache.popitem(last=False)

        logger.info("Built knowledge graph for kb_id=%d: %d nodes, %d edges",
                     kb_id, graph.node_count, graph.edge_count)
        return graph

    except Exception as exc:
        logger.warning("Failed to build knowledge graph for kb_id=%d: %s", kb_id, exc)
        return None


def invalidate_graph_cache(kb_id: Optional[int] = None):
    """Invalidate cached graph for a KB (or all KBs)."""
    if kb_id is None:
        _graph_cache.clear()
    else:
        _graph_cache.pop(kb_id, None)
