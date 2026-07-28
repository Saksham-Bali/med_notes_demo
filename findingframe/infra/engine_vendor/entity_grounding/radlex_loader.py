"""
RadLex loading and search helpers.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree

try:
    import pandas as pd
except Exception:  # pragma: no cover - optional when pandas unavailable
    pd = None

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
except Exception:  # pragma: no cover - optional fallback when sklearn unavailable
    TfidfVectorizer = None
    cosine_similarity = None


def _normalize(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _split_synonyms(*values: str) -> list[str]:
    synonyms: list[str] = []
    seen: set[str] = set()
    for value in values:
        raw = str(value or "").strip()
        if not raw or raw.lower() == "nan":
            continue
        for part in re.split(r"[|,;]", raw):
            synonym = part.strip()
            key = _normalize(synonym)
            if not key or key in seen:
                continue
            seen.add(key)
            synonyms.append(synonym)
    return synonyms


def _parse_rid(text: str) -> str | None:
    match = re.search(r"(RID\d+)", str(text or ""))
    return match.group(1) if match else None


def _parse_parent_ids(text: str) -> list[str]:
    return sorted(set(re.findall(r"(RID\d+)", str(text or ""))))


def _clean_nullable(value: object) -> str | None:
    text = str(value or "").strip()
    if not text or text.lower() == "nan":
        return None
    return text


# ---------------------------------------------------------------------------
# Clinical surface-form aliases → correct RadLex concept IDs.
#
# These are keyed by _normalize(surface_form) and bypass exact-index lookup.
# All RIDs are verified against the full Radlex.xls (46 633 concepts) rather
# than the small built-in subset.  When the full ontology is loaded these
# entries still take priority so that clinical paraphrases (e.g. "elevated
# hemidiaphragm") reach the right concept instead of a spurious synonym hit.
#
# Rules for adding entries here:
#   1. The surface form does not appear as a preferred label in RadLex, OR
#   2. The exact-index returns the wrong concept due to a synonym collision.
# ---------------------------------------------------------------------------
SURFACE_FORM_ALIASES: dict[str, str] = {
    # ---- Anatomy shortcuts -------------------------------------------------
    "lung mass": "RID50149",  # pulmonary nodule (closest pathological)
    "liver met": "RID5231",  # metastasis
    "liver metastasis": "RID5231",  # metastasis
    "hepatic metastasis": "RID5231",  # metastasis
    "bone met": "RID5231",  # metastasis
    "bone metastasis": "RID5231",  # metastasis
    "brain met": "RID5231",  # metastasis
    "brain metastasis": "RID5231",  # metastasis
    "adrenal met": "RID5231",  # metastasis
    "adrenal metastasis": "RID5231",  # metastasis
    # ---- Fracture variants -----------------------------------------------
    "surgical fracture": "RID4650",  # fracture  (RID4650 = preferred label)
    "rib fracture": "RID4650",  # fracture
    "bone fracture": "RID4650",  # fracture
    "acute fracture": "RID4650",  # fracture — "acute fracture" must not match specific subtypes
    "no acute fracture": "RID4650",  # fracture negated
    # ---- Diaphragm elevation ---------------------------------------------
    # Full ontology has no "hemidiaphragm elevation" preferred label; closest
    # anatomy concept is right hemidiaphragm (RID1526).
    "elevated hemidiaphragm": "RID1526",  # right hemidiaphragm
    "elevated right hemidiaphragm": "RID1526",  # right hemidiaphragm
    "right hemidiaphragm elevation": "RID1526",
    "hemidiaphragm elevation": "RID28909",  # hemidiaphragm (generic)
    "diaphragmatic eventration": "RID28909",  # hemidiaphragm
    # ---- Pleural / chest -------------------------------------------------
    "no pleural effusion": "RID34539",  # pleural effusion
    "no effusion": "RID34539",  # pleural effusion
    "pleural thickening": "RID43269",  # pleural plaque (closest RadLex concept)
    "pleural fibrosis": "RID43269",  # pleural plaque
    "pleural scarring": "RID43269",  # pleural plaque
    # ---- Skull / brain findings ------------------------------------------
    "no hemorrhage": "RID4700",  # hemorrhage
    "no hydrocephalus": "RID4885",  # hydrocephalus
    "no midline shift": "RID5826",  # midline
    "midline shift": "RID5826",  # midline
    "midline deviation": "RID5826",  # midline
    # ---- MSK / joint -----------------------------------------------------
    "osseous abnormality": "RID6336",  # osseous (closest anatomy concept)
    "no osseous abnormality": "RID6336",  # osseous (negated)
    "bone abnormality": "RID6336",  # osseous
    "joint effusion": "RID4872",  # effusion (joint)
    "knee effusion": "RID4872",  # effusion
    # ---- Spine / MSK -----------------------------------------------------
    "degenerative changes": "RID3555",  # osteoarthritis
    "degenerative spur": "RID5076",  # osteophyte
    "osteophytes": "RID5076",  # osteophyte
    # ---- Abdomen ---------------------------------------------------------
    "hepatomegaly": "RID34593",  # enlarged liver (RID34593 has 'hepatomegaly' as synonym)
    "enlarged liver": "RID34593",  # enlarged liver
    "renal cyst": "RID35811",  # renal cyst
    # ---- Lymph nodes / adenopathy ----------------------------------------
    "hilar lymph node": "RID3798",  # lymphadenopathy
    "hilar nodes": "RID3798",  # lymphadenopathy
    "hilar calcifications": "RID3798",  # lymphadenopathy
    "hilar lymphadenopathy": "RID3798",  # lymphadenopathy
    "hilar adenopathy": "RID3798",  # lymphadenopathy
    "mediastinal lymph node": "RID13296",  # lymph node (preferred label)
}


BODY_REGION_SEED_LABELS: dict[str, tuple[str, ...]] = {
    "head_neck": ("head", "brain", "neck", "skull", "nasopharynx"),
    "chest": ("thorax", "lung", "heart", "mediastinum", "pleura"),
    "abdomen_pelvis": ("abdomen", "liver", "pelvis", "kidney", "adrenal gland"),
    "musculoskeletal": (
        "musculoskeletal system",
        "knee",
        "hip",
        "rib",
        "femur",
        "tibia",
    ),
    "spine": (
        "vertebral column",
        "spine",
        "cervical spine",
        "thoracic spine",
        "lumbar spine",
    ),
}

BODY_REGION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "head_neck": (
        "brain",
        "cerebr",
        "intracran",
        "skull",
        "nasopharyn",
        "head",
        "neck",
    ),
    "chest": (
        "lung",
        "pulmonary",
        "pleura",
        "pleural",
        "thorax",
        "mediastin",
        "bronch",
        "cardiac",
        "heart",
    ),
    "abdomen_pelvis": (
        "abdomen",
        "pelvis",
        "liver",
        "hepatic",
        "renal",
        "kidney",
        "adrenal",
        "bowel",
        "colon",
        "splenic",
        "pancrea",
    ),
    "musculoskeletal": (
        "knee",
        "hip",
        "femur",
        "tibia",
        "fibula",
        "joint",
        "osseous",
        "bone",
        "musculoskelet",
        "rib",
    ),
    "spine": (
        "spine",
        "vertebra",
        "vertebral",
        "cervical",
        "thoracic",
        "lumbar",
        "sacral",
        "sacro",
    ),
}


@dataclass
class OntologyConcept:
    ontology: str
    concept_id: str
    label: str
    synonyms: list[str]
    parents: list[str] = field(default_factory=list)
    snomed_id: str | None = None
    body_region: str = "other"


class RadLexLoader:
    """
    Loads RadLex concepts and provides exact/fuzzy search.

    Supported formats:
    - Excel (.xls/.xlsx) with RadLex export columns
    - CSV with columns: radlex_id|id, label|name, synonyms
    - JSON list of objects with the same fields
    - OWL/RDF/XML exports
    """

    def __init__(self, source_path: str | None = None):
        self.source_path = (
            Path(source_path) if source_path else self._discover_default_source_path()
        )
        self._concepts: list[OntologyConcept] = []
        self._exact_index: dict[str, list[OntologyConcept]] = {}
        self._concepts_by_id: dict[str, OntologyConcept] = {}
        self._region_buckets: dict[str, list[OntologyConcept]] = {}
        self._tfidf_indexes: dict[
            str, tuple[object, object, list[OntologyConcept]]
        ] = {}
        self._loaded = False

    def _discover_default_source_path(self) -> Path | None:
        for candidate in (
            "Radlex.xls",
            "Radlex.xlsx",
            "Radlex.csv",
            "Radlex.json",
            "Radlex.owl",
            "data/Radlex.xls",
            "data/Radlex.xlsx",
            "data/Radlex.csv",
        ):
            path = Path(candidate)
            if path.exists():
                return path
            root_path = Path(__file__).parent.parent / candidate
            if root_path.exists():
                return root_path
        return None

    def _default_concepts(self) -> list[OntologyConcept]:
        # Small built-in subset so grounding works before a full ontology import.
        # RIDs verified against Radlex.xls (46 633 concepts, March 2026).
        return [
            OntologyConcept(
                ontology="radlex",
                concept_id="RID1327",
                label="upper lobe of right lung",
                synonyms=["right upper lobe", "rul", "right upper lobe lung"],
            ),
            OntologyConcept(
                ontology="radlex",
                concept_id="RID1310",
                label="upper lobe of left lung",
                synonyms=["left upper lobe", "lul", "left upper lobe lung"],
            ),
            OntologyConcept(
                ontology="radlex",
                concept_id="RID1309",
                label="lower lobe of right lung",
                synonyms=["right lower lobe", "rll", "right lower lobe lung"],
            ),
            OntologyConcept(
                ontology="radlex",
                concept_id="RID1308",
                label="lower lobe of left lung",
                synonyms=["left lower lobe", "lll", "left lower lobe lung"],
            ),
            OntologyConcept(
                ontology="radlex",
                concept_id="RID58",
                label="liver",
                synonyms=["hepatic", "hepatic parenchyma"],
            ),
            OntologyConcept(
                ontology="radlex",
                concept_id="RID88",
                label="adrenal gland",
                synonyms=["adrenal", "adrenal gland lesion"],
            ),
            OntologyConcept(
                ontology="radlex",
                concept_id="RID13296",
                label="lymph node",
                synonyms=["lymphadenopathy", "node"],
            ),
            OntologyConcept(
                ontology="radlex",
                concept_id="RID6434",
                label="brain",
                synonyms=["cerebral", "intracranial", "cerebellar"],
            ),
            OntologyConcept(
                ontology="radlex",
                concept_id="RID4700",
                label="hemorrhage",
                synonyms=["bleeding", "intracranial hemorrhage", "haemorrhage"],
            ),
            OntologyConcept(
                ontology="radlex",
                concept_id="RID4885",
                label="hydrocephalus",
                synonyms=["ventriculomegaly", "ventricular enlargement"],
            ),
            OntologyConcept(
                ontology="radlex",
                concept_id="RID5826",
                label="midline",
                synonyms=[
                    "midline shift",
                    "midline deviation",
                    "shift of midline structures",
                ],
            ),
            OntologyConcept(
                ontology="radlex",
                concept_id="RID3891",
                label="arachnoid cyst",
                synonyms=["arachnoid space cyst", "leptomeningeal cyst"],
            ),
            OntologyConcept(
                ontology="radlex",
                concept_id="RID5172",
                label="infarction",
                synonyms=[
                    "infarct",
                    "cerebral infarction",
                    "ischemic stroke",
                    "ischemic infarction",
                ],
            ),
            OntologyConcept(
                ontology="radlex",
                concept_id="RID34539",
                label="pleural effusion",
                synonyms=["pleural fluid", "effusion"],
            ),
            OntologyConcept(
                ontology="radlex",
                concept_id="RID1526",
                label="right hemidiaphragm",
                synonyms=[
                    "elevated hemidiaphragm",
                    "hemidiaphragm elevation",
                    "right hemi-diaphragm",
                ],
            ),
            OntologyConcept(
                ontology="radlex",
                concept_id="RID50149",
                label="pulmonary nodule",
                synonyms=["lung nodule", "nodule", "lung mass"],
            ),
            OntologyConcept(
                ontology="radlex",
                concept_id="RID3798",
                label="lymphadenopathy",
                synonyms=[
                    "hilar adenopathy",
                    "hilar nodes",
                    "hilar calcifications",
                    "hilar lymphadenopathy",
                ],
            ),
            OntologyConcept(
                ontology="radlex",
                concept_id="RID43255",
                label="consolidation",
                synonyms=["pulmonary consolidation", "airspace consolidation"],
            ),
            OntologyConcept(
                ontology="radlex",
                concept_id="RID5352",
                label="pneumothorax",
                synonyms=["ptx", "air in pleural space"],
            ),
            OntologyConcept(
                ontology="radlex",
                concept_id="RID3555",
                label="osteoarthritis",
                synonyms=[
                    "degenerative joint disease",
                    "oa",
                    "djd",
                    "degenerative changes",
                ],
            ),
            OntologyConcept(
                ontology="radlex",
                concept_id="RID4872",
                label="effusion",
                synonyms=[
                    "joint effusion",
                    "joint fluid",
                    "articular effusion",
                    "joint space narrowing",
                ],
            ),
            OntologyConcept(
                ontology="radlex",
                concept_id="RID5076",
                label="osteophyte",
                synonyms=["bone spur", "spur", "osteophytes", "degenerative spur"],
            ),
            OntologyConcept(
                ontology="radlex",
                concept_id="RID4650",
                label="fracture",
                synonyms=[
                    "bone fracture",
                    "rib fracture",
                    "surgical fracture",
                    "break",
                    "fx",
                ],
            ),
            OntologyConcept(
                ontology="radlex",
                concept_id="RID28771",
                label="nasopharyngeal prominence",
                synonyms=["nasopharyngeal soft tissue", "adenoidal hypertrophy"],
            ),
            OntologyConcept(
                ontology="radlex",
                concept_id="RID5231",
                label="metastasis",
                synonyms=["metastatic lesion", "met", "mets"],
            ),
            OntologyConcept(
                ontology="radlex",
                concept_id="RID28493",
                label="atelectasis",
                synonyms=["collapse", "subsegmental atelectasis"],
            ),
        ]

    def _add_to_exact_index(self, concept: OntologyConcept) -> None:
        for term in [concept.label] + list(concept.synonyms):
            key = _normalize(term)
            if not key:
                continue
            self._exact_index.setdefault(key, []).append(concept)

    def _load_from_excel(self, path: Path) -> list[OntologyConcept]:
        if pd is None:
            raise ImportError("pandas is required to load RadLex Excel exports")
        engine = "xlrd" if path.suffix.lower() == ".xls" else "openpyxl"
        df = pd.read_excel(path, engine=engine)

        if "Obsolete" in df.columns:
            obsolete = df["Obsolete"].astype(str).str.strip().str.upper()
            df = df[~obsolete.isin({"TRUE", "1", "YES"})]

        concepts: list[OntologyConcept] = []
        for _, row in df.iterrows():
            concept_id = _parse_rid(row.get("Class ID", ""))
            label = _clean_nullable(row.get("Preferred Label", ""))
            if not concept_id or not label:
                continue
            synonyms = _split_synonyms(row.get("Synonyms", ""), row.get("Synonym", ""))
            concepts.append(
                OntologyConcept(
                    ontology="radlex",
                    concept_id=concept_id,
                    label=label,
                    synonyms=synonyms,
                    parents=_parse_parent_ids(row.get("Parents", "")),
                    snomed_id=_clean_nullable(row.get("SNOMED_ID", "")),
                )
            )
        return concepts

    def _load_from_csv(self, path: Path) -> list[OntologyConcept]:
        concepts: list[OntologyConcept] = []
        with path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                concept_id = _clean_nullable(row.get("radlex_id") or row.get("id"))
                label = _clean_nullable(
                    row.get("label") or row.get("name") or row.get("Preferred Label")
                )
                if not concept_id or not label:
                    continue
                concepts.append(
                    OntologyConcept(
                        ontology="radlex",
                        concept_id=concept_id,
                        label=label,
                        synonyms=_split_synonyms(
                            row.get("synonyms", ""),
                            row.get("Synonym", ""),
                            row.get("Synonyms", ""),
                        ),
                        parents=_parse_parent_ids(row.get("Parents", "")),
                        snomed_id=_clean_nullable(row.get("SNOMED_ID", "")),
                    )
                )
        return concepts

    def _load_from_json(self, path: Path) -> list[OntologyConcept]:
        raw = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        concepts: list[OntologyConcept] = []
        if not isinstance(raw, list):
            return concepts
        for row in raw:
            if not isinstance(row, dict):
                continue
            concept_id = _clean_nullable(row.get("radlex_id") or row.get("id"))
            label = _clean_nullable(row.get("label") or row.get("name"))
            if not concept_id or not label:
                continue
            synonyms = row.get("synonyms", [])
            if not isinstance(synonyms, list):
                synonyms = _split_synonyms(synonyms)
            concepts.append(
                OntologyConcept(
                    ontology="radlex",
                    concept_id=concept_id,
                    label=label,
                    synonyms=[str(s).strip() for s in synonyms if str(s).strip()],
                    parents=_parse_parent_ids(row.get("parents", "")),
                    snomed_id=_clean_nullable(row.get("snomed_id", "")),
                )
            )
        return concepts

    def _load_from_owl(self, path: Path) -> list[OntologyConcept]:
        concepts: list[OntologyConcept] = []
        try:
            tree = ElementTree.parse(path)
            root = tree.getroot()
        except Exception:
            return concepts

        ns = {
            "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
            "owl": "http://www.w3.org/2002/07/owl#",
            "oboInOwl": "http://www.geneontology.org/formats/oboInOwl#",
        }
        classes = root.findall(".//owl:Class", ns)
        for class_node in classes:
            about = class_node.attrib.get(f"{{{ns['rdf']}}}about", "")
            concept_id = _parse_rid(about)
            if not concept_id:
                continue
            labels = class_node.findall("rdfs:label", ns)
            if not labels:
                continue
            label = _clean_nullable(labels[0].text)
            if not label:
                continue
            synonyms: list[str] = []
            for syn_tag in ["hasExactSynonym", "hasRelatedSynonym"]:
                for syn in class_node.findall(f"oboInOwl:{syn_tag}", ns):
                    text = _clean_nullable(syn.text)
                    if text:
                        synonyms.append(text)
            parent_ids = [
                _parse_rid(parent.attrib.get(f"{{{ns['rdf']}}}resource", ""))
                for parent in class_node.findall("rdfs:subClassOf", ns)
            ]
            concepts.append(
                OntologyConcept(
                    ontology="radlex",
                    concept_id=concept_id,
                    label=label,
                    synonyms=_split_synonyms(*synonyms),
                    parents=[p for p in parent_ids if p],
                )
            )
        return concepts

    def _resolve_region_seed_ids(
        self, concepts: list[OntologyConcept]
    ) -> dict[str, set[str]]:
        by_label: dict[str, set[str]] = {}
        for concept in concepts:
            by_label.setdefault(_normalize(concept.label), set()).add(
                concept.concept_id
            )
        seed_ids: dict[str, set[str]] = {}
        for region, labels in BODY_REGION_SEED_LABELS.items():
            region_ids: set[str] = set()
            for label in labels:
                region_ids.update(by_label.get(_normalize(label), set()))
            seed_ids[region] = region_ids
        return seed_ids

    def _ancestor_ids(
        self,
        concept_id: str,
        parent_map: dict[str, list[str]],
        cache: dict[str, set[str]],
    ) -> set[str]:
        if concept_id in cache:
            return cache[concept_id]
        ancestors: set[str] = set()
        for parent_id in parent_map.get(concept_id, []):
            ancestors.add(parent_id)
            ancestors.update(self._ancestor_ids(parent_id, parent_map, cache))
        cache[concept_id] = ancestors
        return ancestors

    def _assign_body_region(
        self,
        concept: OntologyConcept,
        parent_map: dict[str, list[str]],
        seed_ids: dict[str, set[str]],
        ancestor_cache: dict[str, set[str]],
    ) -> str:
        ancestor_ids = self._ancestor_ids(
            concept.concept_id, parent_map, ancestor_cache
        )
        for region, region_seed_ids in seed_ids.items():
            if not region_seed_ids:
                continue
            if concept.concept_id in region_seed_ids:
                return region
            if ancestor_ids.intersection(region_seed_ids):
                return region
        text = " ".join([concept.label] + list(concept.synonyms)).lower()
        for region, keywords in BODY_REGION_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                return region
        return "other"

    def _build_region_buckets(
        self, concepts: list[OntologyConcept]
    ) -> dict[str, list[OntologyConcept]]:
        buckets: dict[str, list[OntologyConcept]] = {
            region: [] for region in BODY_REGION_SEED_LABELS
        }
        buckets["other"] = []
        parent_map = {concept.concept_id: list(concept.parents) for concept in concepts}
        seed_ids = self._resolve_region_seed_ids(concepts)
        ancestor_cache: dict[str, set[str]] = {}
        for concept in concepts:
            concept.body_region = self._assign_body_region(
                concept, parent_map, seed_ids, ancestor_cache
            )
            buckets.setdefault(concept.body_region, []).append(concept)
        return buckets

    def _build_tfidf_indexes(
        self,
        buckets: dict[str, list[OntologyConcept]],
    ) -> dict[str, tuple[object, object, list[OntologyConcept]]]:
        indexes: dict[str, tuple[object, object, list[OntologyConcept]]] = {}
        if TfidfVectorizer is None:
            return indexes
        all_concepts = [
            concept for concepts in buckets.values() for concept in concepts
        ]
        for region, concepts in buckets.items():
            if not concepts:
                continue
            corpus = [
                " ".join([concept.label] + list(concept.synonyms)).lower()
                for concept in concepts
            ]
            vectorizer = TfidfVectorizer(
                analyzer="char_wb",
                ngram_range=(3, 5),
                min_df=1,
            )
            matrix = vectorizer.fit_transform(corpus)
            indexes[region] = (vectorizer, matrix, concepts)
        if all_concepts:
            corpus = [
                " ".join([concept.label] + list(concept.synonyms)).lower()
                for concept in all_concepts
            ]
            vectorizer = TfidfVectorizer(
                analyzer="char_wb",
                ngram_range=(3, 5),
                min_df=1,
            )
            matrix = vectorizer.fit_transform(corpus)
            indexes["__all__"] = (vectorizer, matrix, all_concepts)
        return indexes

    def load(self) -> None:
        if self._loaded:
            return

        concepts: list[OntologyConcept] = []
        if self.source_path and self.source_path.exists():
            suffix = self.source_path.suffix.lower()
            if suffix in {".xls", ".xlsx"}:
                concepts = self._load_from_excel(self.source_path)
            elif suffix == ".csv":
                concepts = self._load_from_csv(self.source_path)
            elif suffix == ".json":
                concepts = self._load_from_json(self.source_path)
            elif suffix in {".owl", ".rdf", ".xml"}:
                concepts = self._load_from_owl(self.source_path)
        if not concepts:
            concepts = self._default_concepts()

        self._concepts = concepts
        self._concepts_by_id = {concept.concept_id: concept for concept in concepts}
        self._exact_index = {}
        for concept in concepts:
            self._add_to_exact_index(concept)

        # Load expanded aliases (generated by scripts/expand_radlex_aliases.py)
        expanded_count = self._load_expanded_aliases()

        self._region_buckets = self._build_region_buckets(concepts)
        self._tfidf_indexes = self._build_tfidf_indexes(self._region_buckets)
        self._loaded = True

        print(
            f"RadLex loaded: {len(self._concepts)} concepts, "
            f"{len(self._exact_index)} index entries "
            f"(+{expanded_count} expanded aliases), "
            f"{len(self._tfidf_indexes)} region buckets"
        )

    def _load_expanded_aliases(self) -> int:
        """Load expanded aliases from JSON file and add to the exact index.

        Returns the number of new aliases added.
        """
        alias_path = Path(__file__).parent / "expanded_aliases.json"
        if not alias_path.exists():
            return 0
        try:
            data = json.loads(alias_path.read_text())
        except Exception:
            return 0

        count = 0
        for concept_id, aliases in data.items():
            concept = self._concepts_by_id.get(concept_id)
            if not concept:
                continue
            for alias in aliases:
                key = _normalize(alias)
                if not key:
                    continue
                # Don't overwrite existing entries
                if key not in self._exact_index:
                    self._exact_index[key] = [concept]
                    count += 1
        return count

    def concepts(self) -> Iterable[OntologyConcept]:
        self.load()
        return self._concepts

    def get_concept_by_id(self, concept_id: str) -> OntologyConcept | None:
        """Return the OntologyConcept for a given RID, or None if not found."""
        self.load()
        return self._concepts_by_id.get(concept_id)

    def exact_match(self, surface_form: str) -> OntologyConcept | None:
        self.load()
        key = _normalize(surface_form)
        if not key:
            return None

        # 1. Curated aliases take priority — they override any synonym collision
        #    from the full ontology (e.g. "no hemorrhage" must not hit a wrong concept).
        alias_id = SURFACE_FORM_ALIASES.get(key)
        if alias_id:
            concept = self._concepts_by_id.get(alias_id)
            if concept:
                return concept

        # 2. Preferred-label-only lookup — prefer concepts whose label matches
        #    over ones that merely carry the surface form as a synonym.
        candidates = self._exact_index.get(key, [])
        if candidates:
            # Prefer preferred-label match over synonym match.
            pref_matches = [c for c in candidates if _normalize(c.label) == key]
            return (pref_matches or candidates)[0]

        return None

    def _concepts_for_region(self, body_region: str) -> list[OntologyConcept]:
        if body_region in self._region_buckets and self._region_buckets[body_region]:
            return self._region_buckets[body_region]
        if self._region_buckets.get("other"):
            return self._region_buckets["other"]
        return self._concepts

    def _collect_tfidf_scores(
        self,
        query: str,
        bundle: tuple[object, object, list[OntologyConcept]] | None,
        limit: int,
    ) -> dict[str, tuple[OntologyConcept, float]]:
        if not bundle or cosine_similarity is None:
            return {}
        vectorizer, matrix, concepts = bundle
        try:
            query_vec = vectorizer.transform([query])
            sims = cosine_similarity(query_vec, matrix).ravel()
        except Exception:
            return {}

        ranked_indices = sorted(
            range(len(sims)), key=lambda idx: sims[idx], reverse=True
        )[: max(limit, 1)]
        results: dict[str, tuple[OntologyConcept, float]] = {}
        for idx in ranked_indices:
            concept = concepts[idx]
            results[concept.concept_id] = (concept, float(sims[idx]))
        return results

    def fuzzy_search(
        self,
        surface_form: str,
        body_region: str = "other",
        top_k: int = 5,
        threshold: float = 0.0,
    ) -> list[tuple[OntologyConcept, float]]:
        self.load()
        query = _normalize(surface_form)
        if not query:
            return []

        concepts = self._concepts_for_region(body_region)
        scored: dict[str, tuple[OntologyConcept, float]] = {}

        for partial_scores in (
            self._collect_tfidf_scores(
                query, self._tfidf_indexes.get(body_region), top_k * 8
            ),
            self._collect_tfidf_scores(
                query, self._tfidf_indexes.get("__all__"), top_k * 8
            ),
        ):
            for concept_id, item in partial_scores.items():
                existing = scored.get(concept_id)
                if existing is None or item[1] > existing[1]:
                    scored[concept_id] = item

        candidate_concepts = list(
            {concept.concept_id: concept for concept in concepts}.values()
        )
        candidate_ids = {concept.concept_id for concept in candidate_concepts}
        for concept, _score in scored.values():
            if concept.concept_id not in candidate_ids:
                candidate_concepts.append(concept)
                candidate_ids.add(concept.concept_id)

        for concept in candidate_concepts:
            candidate_terms = [concept.label] + list(concept.synonyms)
            best = scored.get(concept.concept_id, (concept, 0.0))[1]
            for term in candidate_terms:
                score = SequenceMatcher(None, query, _normalize(term)).ratio()
                if score > best:
                    best = score
            query_tokens = set(query.split())
            label_tokens = set(_normalize(concept.label).split())
            if query_tokens and query_tokens.issubset(label_tokens):
                best = min(1.0, best + 0.08)
            scored[concept.concept_id] = (concept, float(best))

        ranked = sorted(scored.values(), key=lambda item: item[1], reverse=True)
        if threshold > 0.0:
            ranked = [item for item in ranked if item[1] >= threshold]
        return ranked[: max(1, top_k)]
