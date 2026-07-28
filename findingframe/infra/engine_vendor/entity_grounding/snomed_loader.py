"""
SNOMED CT loading and search helpers.
"""

from __future__ import annotations

from pathlib import Path

from .radlex_loader import OntologyConcept, RadLexLoader


class SNOMEDLoader(RadLexLoader):
    """
    Reuses CSV/JSON loading behavior from RadLexLoader with SNOMED defaults.
    """

    def __init__(self, source_path: str | None = None):
        super().__init__(source_path=source_path)

    def _default_concepts(self) -> list[OntologyConcept]:
        return [
            OntologyConcept(
                ontology="snomed",
                concept_id="254637007",
                label="non-small cell lung carcinoma",
                synonyms=["nsclc", "lung adenocarcinoma", "lung cancer"],
            ),
            OntologyConcept(
                ontology="snomed",
                concept_id="94391008",
                label="adenocarcinoma",
                synonyms=["adenocarcinoma"],
            ),
            OntologyConcept(
                ontology="snomed",
                concept_id="128462008",
                label="metastatic malignant neoplasm to liver",
                synonyms=["liver metastasis", "hepatic metastases"],
            ),
            OntologyConcept(
                ontology="snomed",
                concept_id="363406005",
                label="malignant neoplastic disease",
                synonyms=["malignancy", "cancer"],
            ),
        ]

    def _load_from_csv(self, path: Path) -> list[OntologyConcept]:
        concepts = super()._load_from_csv(path)
        return [
            OntologyConcept(
                ontology="snomed",
                concept_id=concept.concept_id,
                label=concept.label,
                synonyms=concept.synonyms,
            )
            for concept in concepts
        ]

    def _load_from_json(self, path: Path) -> list[OntologyConcept]:
        concepts = super()._load_from_json(path)
        return [
            OntologyConcept(
                ontology="snomed",
                concept_id=concept.concept_id,
                label=concept.label,
                synonyms=concept.synonyms,
            )
            for concept in concepts
        ]
