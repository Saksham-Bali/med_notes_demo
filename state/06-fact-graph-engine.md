# Agent 06: Fact Graph Engine

> **Status:** EXISTS — needs major upgrade (log → state machine)  
> **Deployment:** Standalone microservice + database  
> **Port:** `5006`  
> **Base URL:** `http://fact-graph:5006`

---

## 1. What This Agent Does

The Fact Graph Engine is the **single source of truth** for all patient data in the platform. Every other agent either writes to it or reads from it. It maintains a **longitudinal, entity-centric state** of each patient's clinical journey.

It is NOT a simple database. It is a **state machine** where each clinical entity has a trajectory that evolves over time as new data arrives.

---

## 2. Current State (What Already Exists)

You have a Fact Graph that:
- Stores extracted findings from radiology reports
- Maintains a timeline of events per patient
- Links entities to RadLex IDs
- Supports RECIST measurement tracking

**Critical problems:**
- Acts as an **append-only log**, not a state machine
- Entities don't merge across time (pleural effusion in Report 3 and Report 24 are separate entries)
- Deduplication uses string similarity, not ontology identity
- No confidence trajectories
- No entity type classification
- No multi-source support (only handles radiology, not SOAP/counselling/department notes)

---

## 3. What Needs to Change

### 3.1 Core Data Model Redesign

**Current (broken):**
```
FactGraph
  └── Events[]           # flat list of extracted mentions
       ├── text
       ├── radlex_id
       ├── report_id
       └── timestamp
```

**New (state machine):**
```
FactGraph
  └── Patient
       └── Entities[]                    # each entity is a persistent concept
            ├── canonical_name           # "pleural effusion"
            ├── radlex_id                # "RID34901"
            ├── entity_type              # PRIMARY | INCIDENTAL | NEGATED | ANATOMICAL
            ├── current_status           # PRESENT | ABSENT | IMPROVED | WORSENED | STABLE | NEW
            ├── current_certainty        # latest confidence score
            ├── first_seen               # timestamp
            ├── last_updated             # timestamp
            ├── trajectory[]             # status history over time
            │    ├── timestamp
            │    ├── status
            │    ├── certainty
            │    ├── source_type
            │    ├── source_department
            │    └── evidence
            ├── measurements[]           # for RECIST-tracked entities
            │    ├── timestamp
            │    ├── value
            │    ├── unit
            │    └── comparison_to_prior
            └── provenance[]             # which departments/sources contributed
                 ├── source_type
                 ├── department
                 └── timestamp
```

### 3.2 RadLex-Based Entity Merging (The #1 Fix)

**Replace this:**
```python
# OLD: string similarity merge
if name_similarity(new_entity, existing_entity) > 0.93:
    merge()
```

**With this:**
```python
# NEW: ontology-based merge
def should_merge(new_fact: ClinicalFact, existing_entity: Entity) -> bool:
    # Level 1: Exact RadLex ID match
    if new_fact.radlex_id and new_fact.radlex_id == existing_entity.radlex_id:
        return True
    
    # Level 2: Ontology parent match (e.g., "right pleural effusion" and "pleural effusion")
    if radlex_db.is_parent_of(existing_entity.radlex_id, new_fact.radlex_id):
        return True
    if radlex_db.is_parent_of(new_fact.radlex_id, existing_entity.radlex_id):
        return True
    
    # Level 3: Sibling concepts (same parent in ontology)
    if radlex_db.are_siblings(new_fact.radlex_id, existing_entity.radlex_id):
        # Only merge siblings if they're clinically equivalent
        return radlex_db.clinical_equivalence(new_fact.radlex_id, existing_entity.radlex_id) > 0.8
    
    # Level 4: Fall back to string similarity only for ungrounded entities
    if not new_fact.radlex_id and not existing_entity.radlex_id:
        return fuzzy_match(new_fact.entity, existing_entity.canonical_name) > 0.90
    
    return False
```

### 3.3 Temporal Propagation

When the same entity appears in different reports over time, update its trajectory:

```python
async def ingest_fact(self, patient_id: str, fact: ClinicalFact):
    # Find existing entity
    existing = self.find_matching_entity(patient_id, fact)
    
    if existing:
        # UPDATE trajectory
        existing.trajectory.append(TrajectoryPoint(
            timestamp=fact.timestamp,
            status=fact.status,
            certainty=fact.certainty,
            source_type=fact.source_type,
            source_department=fact.source_department,
            evidence=fact.evidence,
        ))
        existing.current_status = fact.status
        existing.current_certainty = fact.certainty
        existing.last_updated = fact.timestamp
        
        # Add provenance if new department
        if fact.source_department not in [p.department for p in existing.provenance]:
            existing.provenance.append(Provenance(
                source_type=fact.source_type,
                department=fact.source_department,
                timestamp=fact.timestamp,
            ))
    else:
        # CREATE new entity
        entity = Entity(
            canonical_name=fact.entity,
            radlex_id=fact.radlex_id,
            entity_type=fact.entity_type,
            current_status=fact.status,
            current_certainty=fact.certainty,
            first_seen=fact.timestamp,
            last_updated=fact.timestamp,
            trajectory=[TrajectoryPoint(...)],
            provenance=[Provenance(...)],
        )
        self.add_entity(patient_id, entity)
```

### 3.4 Multi-Source Ingestion

The Fact Graph must now accept facts from ALL sources, not just radiology:

```python
# All of these produce ClinicalFact objects with the same schema:
# - SOAP Extractor (handwritten notes)
# - Radiology Extractor (radiology reports)
# - Counselling Summarizer (voice transcripts — only approved facts)
# - Department Merger (multi-department consolidated notes)
# - EMR Adapter (direct EMR feeds)

# The ingest endpoint doesn't care about the source — it's all CFS
@app.post("/api/v1/ingest")
async def ingest_facts(request: IngestRequest):
    for fact in request.facts:
        await fact_graph.ingest_fact(request.patient_id, fact)
```

---

## 4. API Contract

### 4.1 Ingest Facts

```
POST /api/v1/ingest
```

```json
{
  "patient_id": "PAT-12345",
  "facts": [
    {
      "entity": "pleural effusion",
      "radlex_id": "RID34901",
      "entity_type": "PRIMARY",
      "certainty": 0.94,
      "evidence": "Small left pleural effusion noted",
      "source_type": "RADIOLOGY",
      "source_department": "radiology",
      "timestamp": "2026-03-25T00:00:00Z",
      "negated": false,
      "status": "PRESENT"
    }
  ]
}
```

### 4.2 Get Patient State

```
GET /api/v1/patient/{patient_id}/state
```

Returns the full current state of all entities for a patient:

```json
{
  "patient_id": "PAT-12345",
  "entities": [
    {
      "canonical_name": "pleural effusion",
      "radlex_id": "RID34901",
      "entity_type": "PRIMARY",
      "current_status": "IMPROVED",
      "current_certainty": 0.88,
      "first_seen": "2026-01-15T00:00:00Z",
      "last_updated": "2026-03-25T00:00:00Z",
      "trajectory": [
        {"timestamp": "2026-01-15", "status": "PRESENT", "certainty": 0.94, "source_type": "RADIOLOGY"},
        {"timestamp": "2026-02-20", "status": "PRESENT", "certainty": 0.90, "source_type": "RADIOLOGY"},
        {"timestamp": "2026-03-25", "status": "IMPROVED", "certainty": 0.88, "source_type": "RADIOLOGY"}
      ],
      "provenance": [
        {"source_type": "RADIOLOGY", "department": "radiology", "timestamp": "2026-01-15"}
      ]
    }
  ],
  "last_updated": "2026-03-25T00:00:00Z",
  "entity_count": 12
}
```

### 4.3 Get Patient Timeline

```
GET /api/v1/patient/{patient_id}/timeline
```

Returns all events in chronological order (for the live dashboard).

### 4.4 Get Entity History

```
GET /api/v1/patient/{patient_id}/entity/{radlex_id}/history
```

Returns the full trajectory of a single entity.

### 4.5 Conflict Check

```
POST /api/v1/patient/{patient_id}/check-conflicts
```

Called by the Department Merger to check if incoming facts conflict with existing state.

---

## 5. Database Schema (PostgreSQL)

```sql
CREATE TABLE patients (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE entities (
    id SERIAL PRIMARY KEY,
    patient_id TEXT REFERENCES patients(id),
    canonical_name TEXT NOT NULL,
    radlex_id TEXT,
    entity_type TEXT NOT NULL,  -- PRIMARY, INCIDENTAL, NEGATED, ANATOMICAL
    current_status TEXT NOT NULL, -- PRESENT, ABSENT, IMPROVED, WORSENED, STABLE, NEW
    current_certainty FLOAT NOT NULL,
    first_seen TIMESTAMP NOT NULL,
    last_updated TIMESTAMP NOT NULL,
    embedding VECTOR(1536)  -- pgvector for semantic search
);

CREATE TABLE trajectory_points (
    id SERIAL PRIMARY KEY,
    entity_id INTEGER REFERENCES entities(id),
    timestamp TIMESTAMP NOT NULL,
    status TEXT NOT NULL,
    certainty FLOAT NOT NULL,
    source_type TEXT NOT NULL,
    source_department TEXT,
    evidence TEXT
);

CREATE TABLE measurements (
    id SERIAL PRIMARY KEY,
    entity_id INTEGER REFERENCES entities(id),
    timestamp TIMESTAMP NOT NULL,
    value FLOAT NOT NULL,
    unit TEXT NOT NULL,
    comparison_to_prior TEXT
);

CREATE TABLE provenance (
    id SERIAL PRIMARY KEY,
    entity_id INTEGER REFERENCES entities(id),
    source_type TEXT NOT NULL,
    department TEXT,
    timestamp TIMESTAMP NOT NULL
);

CREATE INDEX idx_entities_patient ON entities(patient_id);
CREATE INDEX idx_entities_radlex ON entities(radlex_id);
CREATE INDEX idx_trajectory_entity ON trajectory_points(entity_id);
```

---

## 6. Deployment

### 6.1 Environment Variables

```env
DATABASE_URL=postgresql://user:pass@postgres:5432/factgraph
RADLEX_DB_PATH=/data/radlex.db
EMBEDDING_MODEL=text-embedding-3-small
OPENAI_API_KEY=your-key          # for embeddings only
MERGE_STRATEGY=ontology_first     # ontology_first | string_similarity | hybrid
CONFIDENCE_DECAY_RATE=0.01        # per month, for aging facts
LOG_LEVEL=INFO
```

---

## 7. Testing Checklist

- [ ] Same entity (same RadLex ID) from two reports → merged into one entity with 2 trajectory points
- [ ] Ontology parent match → correctly merged (e.g., "right pleural effusion" merges with "pleural effusion")
- [ ] String similarity fallback → only used when both entities are ungrounded
- [ ] Negated finding updates status → entity status changes from PRESENT to ABSENT
- [ ] Multi-source ingestion → RADIOLOGY, HANDWRITTEN, COUNSELLING all accepted
- [ ] Department provenance → correctly tracks which departments contributed
- [ ] Patient state endpoint → returns all current entities with latest status
- [ ] Timeline endpoint → returns chronological events
- [ ] Conflict check → identifies contradictions between departments
- [ ] RECIST measurements → stored and retrievable per entity

---

## 8. File Structure

```
fact-graph/
├── main.py
├── core/
│   ├── entity_manager.py        # Create, merge, update entities
│   ├── merge_logic.py           # RadLex-based merge decisions
│   ├── trajectory_tracker.py    # Temporal propagation
│   └── conflict_detector.py     # Cross-department conflict check
├── models/
│   ├── entity.py
│   ├── trajectory.py
│   ├── clinical_fact.py         # CFS input schema
│   └── response.py
├── db/
│   ├── connection.py
│   ├── migrations/
│   │   └── 001_initial.sql
│   └── queries.py
├── grounding/
│   ├── radlex_db.py
│   └── radlex_merge.py
├── config.py
├── Dockerfile
├── docker-compose.yml           # includes postgres + pgvector
├── requirements.txt
└── tests/
    ├── test_merge_logic.py
    ├── test_temporal_propagation.py
    ├── test_multi_source.py
    └── test_conflict_detection.py
```
