"""
الرسم المعرفي (Knowledge Graph) — مستوحى من Cognee.

يبني علاقات بين الذكريات عبر الكيانات المشتركة، ويسمح
بالاسترجاع عبر المسارات (graph traversal) بالإضافة للبحث الدلالي.

يستخدم SQLite بدل KuzuDB (لخفة Termux) لكن بنفس المفهوم:
  عقد (nodes) = ذكريات + كيانات
  حواف (edges) = علاقات بينها
"""

from __future__ import annotations
from dataclasses import dataclass
import sqlite3
import json
import time


@dataclass
class Edge:
    """حافة بين عقدتين — مستوحاة من Cognee Edge."""
    source: str        # id العقدة المصدر
    target: str        # id العقدة الهدف
    relation: str      # نوع العلاقة (mentions, relates_to, causes...)
    weight: float = 1.0
    metadata: dict = None


class GraphStore:
    """
    مخزن الرسم المعرفي على SQLite.
    خفيف بما يكفي لـ Termux، وقوي بما يكفي للخادم.
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS graph_nodes (
            id TEXT PRIMARY KEY,
            node_type TEXT NOT NULL,     -- memory | entity
            label TEXT,
            data TEXT,
            created_at REAL
        );
        CREATE TABLE IF NOT EXISTS graph_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            target TEXT NOT NULL,
            relation TEXT NOT NULL,
            weight REAL DEFAULT 1.0,
            metadata TEXT,
            created_at REAL,
            UNIQUE(source, target, relation)
        );
        CREATE INDEX IF NOT EXISTS idx_edges_source ON graph_edges(source);
        CREATE INDEX IF NOT EXISTS idx_edges_target ON graph_edges(target);
        CREATE INDEX IF NOT EXISTS idx_nodes_type ON graph_nodes(node_type);
        """)
        self.conn.commit()

    def add_node(self, node_id: str, node_type: str, label: str = "", data: dict = None):
        """يضيف عقدة (ذكرى أو كيان)."""
        self.conn.execute(
            "INSERT OR REPLACE INTO graph_nodes (id, node_type, label, data, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (node_id, node_type, label, json.dumps(data or {}), time.time())
        )
        self.conn.commit()

    def add_edge(self, edge: Edge):
        """يضيف علاقة بين عقدتين."""
        self.conn.execute(
            "INSERT OR IGNORE INTO graph_edges "
            "(source, target, relation, weight, metadata, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (edge.source, edge.target, edge.relation, edge.weight,
             json.dumps(edge.metadata or {}), time.time())
        )
        self.conn.commit()

    def link_by_entities(self, memory_id: str, entities: list[str]):
        """
        يربط ذكرى بكياناتها — جوهر بناء الـ graph.
        كل كيان يصبح عقدة، والذكرى ترتبط به.
        """
        self.add_node(memory_id, "memory")
        for entity in entities:
            ent_id = f"entity:{entity.lower().strip()}"
            self.add_node(ent_id, "entity", label=entity)
            self.add_edge(Edge(memory_id, ent_id, "mentions"))

    def neighbors(self, node_id: str, max_hops: int = 1) -> list[str]:
        """
        يجد العقد المجاورة عبر المسارات (graph traversal).
        max_hops=2 يعني: الذكريات التي تشترك في كيانات مع ذكرياتي.
        """
        visited = set()
        frontier = {node_id}

        for _ in range(max_hops):
            next_frontier = set()
            for nid in frontier:
                # الحواف الصادرة والواردة
                rows = self.conn.execute(
                    "SELECT target FROM graph_edges WHERE source = ? "
                    "UNION SELECT source FROM graph_edges WHERE target = ?",
                    (nid, nid)
                ).fetchall()
                for (neighbor,) in rows:
                    if neighbor not in visited:
                        next_frontier.add(neighbor)
                        visited.add(neighbor)
            frontier = next_frontier

        return list(visited)

    def related_memories(self, memory_id: str, max_hops: int = 2) -> list[str]:
        """
        يجد الذكريات المرتبطة عبر كيانات مشتركة.
        هذا ما يميز الـ graph عن البحث الدلالي البحت.
        """
        neighbors = self.neighbors(memory_id, max_hops)
        # فلترة العقد من نوع memory فقط
        mem_ids = []
        for nid in neighbors:
            if nid.startswith("entity:"):
                continue
            row = self.conn.execute(
                "SELECT node_type FROM graph_nodes WHERE id = ?", (nid,)
            ).fetchone()
            if row and row[0] == "memory" and nid != memory_id:
                mem_ids.append(nid)
        return mem_ids
