"""
SQLite-backed FactStore for scalable fact graph persistence.
Phase 8: replaces JSON file storage with a relational database.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .migrations import migrate_graph_payload


_DEFAULT_DB = Path("data") / "fact_graphs.db"


class SQLiteFactStore:
    """
    Persists fact graphs in SQLite.
    Tables: patients, entities, events (with full event payload as JSON).
    """

    def __init__(self, db_path: str | Path = _DEFAULT_DB):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS patients (
                    subject_id    TEXT PRIMARY KEY,
                    schema_version INTEGER DEFAULT 2,
                    metadata_json TEXT DEFAULT '{}',
                    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS entities (
                    entity_id       TEXT NOT NULL,
                    subject_id      TEXT NOT NULL REFERENCES patients(subject_id),
                    canonical_name  TEXT NOT NULL,
                    radlex_id       TEXT,
                    snomed_id       TEXT,
                    entity_type     TEXT DEFAULT 'finding',
                    anatomical_site TEXT,
                    body_region     TEXT,
                    first_documented TEXT,
                    last_documented  TEXT,
                    status          TEXT DEFAULT 'active',
                    certainty_json  TEXT DEFAULT '[]',
                    PRIMARY KEY (entity_id, subject_id)
                );

                CREATE TABLE IF NOT EXISTS events (
                    event_id         TEXT NOT NULL,
                    entity_id        TEXT NOT NULL,
                    subject_id       TEXT NOT NULL,
                    date             TEXT,
                    source_report_id TEXT,
                    hadm_id          TEXT,
                    modality         TEXT DEFAULT 'OTHER',
                    measurement_json TEXT DEFAULT '{}',
                    certainty        REAL DEFAULT 0.0,
                    certainty_label  TEXT DEFAULT 'unknown',
                    trend            TEXT DEFAULT 'unknown',
                    is_negated       INTEGER DEFAULT 0,
                    negation_language TEXT,
                    payload_json     TEXT DEFAULT '{}',
                    PRIMARY KEY (event_id, subject_id),
                    FOREIGN KEY (entity_id, subject_id) REFERENCES entities(entity_id, subject_id)
                );

                CREATE INDEX IF NOT EXISTS idx_entities_subject ON entities(subject_id);
                CREATE INDEX IF NOT EXISTS idx_events_subject ON events(subject_id);
                CREATE INDEX IF NOT EXISTS idx_events_entity ON events(entity_id, subject_id);
                CREATE INDEX IF NOT EXISTS idx_events_date ON events(date);
            """)

    def save_fact_graph(self, fact_graph: dict[str, Any]) -> None:
        """Persist a complete fact graph to SQLite (upsert semantics)."""
        migrated = migrate_graph_payload(dict(fact_graph or {}))
        subject_id = str(migrated.get("subject_id", ""))
        if not subject_id:
            raise ValueError("fact_graph must have a 'subject_id'")

        metadata = json.dumps(migrated.get("metadata", {}))
        schema_version = int(migrated.get("schema_version", 2))
        entities = migrated.get("entities", {})
        if not isinstance(entities, dict):
            entities = {}

        with self._conn() as conn:
            conn.execute(
                """INSERT INTO patients (subject_id, schema_version, metadata_json, updated_at)
                   VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(subject_id) DO UPDATE SET
                     schema_version=excluded.schema_version,
                     metadata_json=excluded.metadata_json,
                     updated_at=CURRENT_TIMESTAMP""",
                (subject_id, schema_version, metadata),
            )

            # Clear existing entities/events for this patient, then reinsert.
            conn.execute("DELETE FROM events WHERE subject_id = ?", (subject_id,))
            conn.execute("DELETE FROM entities WHERE subject_id = ?", (subject_id,))

            for entity_id, entity in entities.items():
                if not isinstance(entity, dict):
                    continue
                conn.execute(
                    """INSERT INTO entities
                       (entity_id, subject_id, canonical_name, radlex_id, snomed_id,
                        entity_type, anatomical_site, body_region,
                        first_documented, last_documented, status, certainty_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        entity_id,
                        subject_id,
                        str(entity.get("canonical_name", entity_id)),
                        entity.get("radlex_id"),
                        entity.get("snomed_id"),
                        str(entity.get("entity_type", "finding")),
                        entity.get("anatomical_site"),
                        entity.get("body_region"),
                        str(entity.get("first_documented", "")),
                        str(entity.get("last_documented", "")),
                        str(entity.get("status", "active")),
                        json.dumps(entity.get("certainty_trajectory", [])),
                    ),
                )

                events = entity.get("events", [])
                if not isinstance(events, list):
                    continue
                for event in events:
                    if not isinstance(event, dict):
                        continue
                    conn.execute(
                        """INSERT INTO events
                           (event_id, entity_id, subject_id, date, source_report_id,
                            hadm_id, modality, measurement_json, certainty,
                            certainty_label, trend, is_negated, negation_language,
                            payload_json)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            str(event.get("event_id", "")),
                            entity_id,
                            subject_id,
                            str(event.get("date", "")),
                            str(event.get("source_report_id", "")),
                            str(event.get("hadm_id", "")),
                            str(event.get("modality", "OTHER")),
                            json.dumps(event.get("measurement", {})),
                            float(event.get("certainty", 0.0)),
                            str(event.get("certainty_label", "unknown")),
                            str(event.get("trend", "unknown")),
                            int(bool(event.get("is_negated", False))),
                            event.get("negation_language"),
                            json.dumps(event),
                        ),
                    )

    def load_fact_graph(self, subject_id: str) -> dict[str, Any] | None:
        """Load a fact graph from SQLite. Returns None if not found."""
        with self._conn() as conn:
            patient = conn.execute(
                "SELECT * FROM patients WHERE subject_id = ?", (subject_id,)
            ).fetchone()
            if not patient:
                return None

            entities_rows = conn.execute(
                "SELECT * FROM entities WHERE subject_id = ?", (subject_id,)
            ).fetchall()

            entities: dict[str, Any] = {}
            for row in entities_rows:
                entity_id = row["entity_id"]
                event_rows = conn.execute(
                    "SELECT payload_json FROM events WHERE entity_id = ? AND subject_id = ? ORDER BY date, event_id",
                    (entity_id, subject_id),
                ).fetchall()

                events = [json.loads(er["payload_json"]) for er in event_rows]

                entities[entity_id] = {
                    "entity_id": entity_id,
                    "canonical_name": row["canonical_name"],
                    "radlex_id": row["radlex_id"],
                    "snomed_id": row["snomed_id"],
                    "entity_type": row["entity_type"],
                    "anatomical_site": row["anatomical_site"],
                    "body_region": row["body_region"],
                    "first_documented": row["first_documented"],
                    "last_documented": row["last_documented"],
                    "status": row["status"],
                    "events": events,
                    "certainty_trajectory": json.loads(row["certainty_json"] or "[]"),
                }

            return {
                "subject_id": subject_id,
                "schema_version": patient["schema_version"],
                "metadata": json.loads(patient["metadata_json"] or "{}"),
                "entities": entities,
            }

    def list_patients(self) -> list[str]:
        """Return all stored patient subject IDs."""
        with self._conn() as conn:
            rows = conn.execute("SELECT subject_id FROM patients ORDER BY subject_id").fetchall()
            return [row["subject_id"] for row in rows]
