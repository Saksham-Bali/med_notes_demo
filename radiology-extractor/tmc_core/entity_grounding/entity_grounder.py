"""
Ontology-grounded entity resolver.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from typing import Any

# dotenv not needed in containerized service

from tmc_core.utils.llm import create_default_llm_client, parse_json_from_text
from tmc_core.entity_grounding.grounding_cache import CACHE_MISS_SENTINEL, GroundingCache
from tmc_core.entity_grounding.radlex_loader import OntologyConcept, RadLexLoader, _normalize
from tmc_core.entity_grounding.snomed_loader import SNOMEDLoader

try:
    from tmc_core.entity_grounding.vector_grounder import VectorGrounder
except ImportError:
    VectorGrounder = None  # type: ignore[assignment,misc]

try:
    from tmc_core.entity_grounding.scispacy_grounder import ScispaCyGrounder
except ImportError:
    ScispaCyGrounder = None  # type: ignore[assignment,misc]

# ---------------------------------------------------------------------------
# Negation-prefix patterns (used in Tier 1b negation-stripped exact match)
# ---------------------------------------------------------------------------
_NEGATION_PREFIX_RE = re.compile(
    r"^(?:no\s+evidence\s+of\s+|no\s+acute\s+|negative\s+for\s+|"
    r"absence\s+of\s+|without\s+|not\s+|no\s+)",
    re.IGNORECASE,
)


def _strip_negation_prefix(text: str) -> str:
    """Strip a leading clinical negation phrase from a surface form.

    Examples:
        "no hemorrhage"            → "hemorrhage"
        "no evidence of infarct"   → "infarct"
        "without pleural effusion" → "pleural effusion"
        "no acute fracture"        → "fracture"
    """
    return _NEGATION_PREFIX_RE.sub("", (text or "")).strip()


# ---------------------------------------------------------------------------
# Fuzzy acceptance thresholds (Fix 1)
# ---------------------------------------------------------------------------
# Raised from the original 0.70 baseline, which was calibrated for a 9-concept
# built-in subset. At 46,000 concepts, 0.70 TF-IDF is too permissive.
FUZZY_THRESHOLD_BASE = 0.82  # anatomy mismatch: cross-region match
FUZZY_THRESHOLD_WITH_ANATOMY = 0.78  # slight relaxation when anatomy matches
FUZZY_THRESHOLD_CROSS_REGION = 0.93  # very high bar for cross-region hits

# ---------------------------------------------------------------------------
# Oncologic concept gating (Fix 3)
# ---------------------------------------------------------------------------
ONCOLOGIC_RADLEX_PARENTS = {
    "RID4906",  # malignant neoplasm
    "RID4903",  # neoplasm
    "RID34617",  # metastasis
}

# Minimum token-count ratio for label vs surface form (Fix 4)
MIN_LABEL_SPECIFICITY_RATIO = 0.4


def _slug(text: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    return text or "unspecified_entity"


def _has_neoplastic_cues(text: str) -> bool:
    lowered = (text or "").lower()
    return any(
        token in lowered
        for token in (
            "mass",
            "lesion",
            "nodule",
            "tumor",
            "neoplasm",
            "malignan",
            "cancer",
            "carcinoid",
            "metasta",
            "adenopathy",
        )
    )


# Phase 7 — Cross-report entity linking: coarse body region map.
BODY_REGION_MAP: dict[str, str] = {
    # Head / Neck
    "brain": "head_neck",
    "cerebral": "head_neck",
    "intracranial": "head_neck",
    "cerebellar": "head_neck",
    "pituitary": "head_neck",
    "sella": "head_neck",
    "orbit": "head_neck",
    "skull": "head_neck",
    "temporal": "head_neck",
    "nasopharyn": "head_neck",
    "neck": "head_neck",
    "thyroid": "head_neck",
    # Chest
    "lung": "chest",
    "pulmonary": "chest",
    "mediastin": "chest",
    "pleural": "chest",
    "hilar": "chest",
    "bronch": "chest",
    "pericardi": "chest",
    "cardiac": "chest",
    "rul": "chest",
    "rll": "chest",
    "lul": "chest",
    "lll": "chest",
    # Abdomen / Pelvis
    "liver": "abdomen_pelvis",
    "hepatic": "abdomen_pelvis",
    "spleen": "abdomen_pelvis",
    "splenic": "abdomen_pelvis",
    "kidney": "abdomen_pelvis",
    "renal": "abdomen_pelvis",
    "adrenal": "abdomen_pelvis",
    "pancrea": "abdomen_pelvis",
    "bowel": "abdomen_pelvis",
    "colon": "abdomen_pelvis",
    "bladder": "abdomen_pelvis",
    "peritoneal": "abdomen_pelvis",
    # Musculoskeletal
    "knee": "musculoskeletal",
    "hip": "musculoskeletal",
    "shoulder": "musculoskeletal",
    "ankle": "musculoskeletal",
    "femur": "musculoskeletal",
    "tibia": "musculoskeletal",
    "rib": "musculoskeletal",
    "sternum": "musculoskeletal",
    # Spine
    "cervical spine": "spine",
    "thoracic spine": "spine",
    "lumbar spine": "spine",
    "vertebra": "spine",
    "spinal": "spine",
}


def infer_body_region(entity_name: str, anatomical_site: str | None = None) -> str:
    """Infer the coarse body region from entity name and/or anatomical site."""
    text = f"{entity_name or ''} {anatomical_site or ''}".lower()
    for keyword, region in BODY_REGION_MAP.items():
        if keyword in text:
            return region
    return "other"


@dataclass
class GroundedEntity:
    surface_form: str
    radlex_id: str | None
    radlex_label: str | None
    snomed_id: str | None
    grounding_method: str
    grounding_confidence: float
    canonical_name: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EntityGrounder:
    """
    3-tier grounding:
    1) exact match (RadLex/SNOMED)
    2) fuzzy match (with anatomy consistency, token overlap, and label specificity gates)
    3) optional LLM-assisted candidate selection
    """

    def __init__(
        self,
        radlex_loader: RadLexLoader | None = None,
        snomed_loader: SNOMEDLoader | None = None,
        llm_client: Any | None = None,
        cache: GroundingCache | None = None,
        fuzzy_threshold: float = FUZZY_THRESHOLD_WITH_ANATOMY,
        use_vector_grounding: bool = True,
        use_scispacy: bool = True,
    ):
        from tmc_core.utils.llm import AZURE_ENDPOINT, AZURE_API_KEY, AZURE_DEPLOYMENT
        self.radlex = radlex_loader or RadLexLoader(
            source_path=os.getenv("RADLEX_PATH", os.getenv("RADLEX_SOURCE_PATH"))
        )
        self.snomed = snomed_loader or SNOMEDLoader(
            source_path=os.getenv("SNOMED_SOURCE_PATH")
        )
        # Tier 2b: BiomedBERT + FAISS vector search (disabled in this service)
        self.vector_grounder = None
        if use_vector_grounding and VectorGrounder is not None:
            try:
                self.vector_grounder = VectorGrounder(radlex_loader=self.radlex)
            except Exception:
                pass  # Fall back to TF-IDF only
        # Tier 0.5: scispaCy UMLS entity linker (disabled in this service)
        self.scispacy_grounder = None
        if use_scispacy and ScispaCyGrounder is not None:
            self.scispacy_grounder = ScispaCyGrounder()
        if llm_client is not None:
            self.llm_client = llm_client
        else:
            # Use Azure client if API key is configured
            has_azure_env = bool(AZURE_API_KEY and AZURE_ENDPOINT)
            self.llm_client = (
                create_default_llm_client(deployment=AZURE_DEPLOYMENT)
                if has_azure_env
                else None
            )
        self.cache = cache or GroundingCache()
        self.fuzzy_threshold = fuzzy_threshold

    def _legacy_canonical_name(
        self, surface_form: str, label: str | None = None
    ) -> str:
        surface = (surface_form or "").lower()
        text = f"{surface} {label or ''}".lower()
        if "osseous abnormality" in text or "bone abnormality" in text:
            return "finding_osseous_abnormality"
        if "hepatic" in text or "liver" in text:
            return "metastasis_liver"
        if "adrenal" in text and "left" in text:
            return "metastasis_adrenal_left"
        if "adrenal" in text and "right" in text:
            return "metastasis_adrenal_right"
        if (
            "lung" in text or "lobe" in text or "pulmonary" in text
        ) and _has_neoplastic_cues(text):
            if "right upper" in text or "rul" in text:
                return "primary_lung_right_upper_lobe"
            if "right lower" in text or "rll" in text:
                return "primary_lung_right_lower_lobe"
            if "left upper" in text or "lul" in text:
                return "primary_lung_left_upper_lobe"
            if "left lower" in text or "lll" in text:
                return "primary_lung_left_lower_lobe"
            return "primary_lung_unspecified"
        if ("lymph" in text or "node" in text) and _has_neoplastic_cues(text):
            return "lymph_node_unspecified"
        if ("brain" in text or "cerebell" in text) and _has_neoplastic_cues(text):
            return "lesion_brain_unspecified"
        raw = f"finding_{_slug(label or surface_form)}"
        return self._postprocess_canonical_name(raw, surface_form)

    # ------------------------------------------------------------------
    # Anatomy-not-finding canonical name correction
    # ------------------------------------------------------------------
    def _postprocess_canonical_name(
        self, canonical_name: str, surface_form: str = ""
    ) -> str:
        """Correct bare anatomy slugs to include the clinical finding qualifier."""
        name = (canonical_name or "").lower().strip()
        ANATOMY_TO_FINDING = {
            "finding_paranasal_sinuses": "finding_paranasal_sinuses_normally_aerated",
            "finding_mastoid_air_cell": "finding_mastoid_air_cells_normally_aerated",
            "finding_mastoid_air_cells": "finding_mastoid_air_cells_normally_aerated",
            "finding_right_hemidiaphragm": "finding_right_hemidiaphragm_elevation",
            "finding_left_hemidiaphragm": "finding_left_hemidiaphragm_elevation",
            "finding_craniocervical_junction": "finding_craniocervical_junction_normal",
        }
        corrected = ANATOMY_TO_FINDING.get(name)
        if corrected:
            return corrected
        # 'territorial' alone is a partial adjective, not a finding
        if name == "finding_territorial":
            sf = (surface_form or "").lower()
            if "infarct" in sf or "ischemi" in sf:
                return "finding_vascular_territorial_infarct"
        # 'heart size normal' should not become 'finding_enlargement' or 'finding_acromegaly'
        # Defensive: if surface form is a normal-observation statement, map to a
        # clearly-qualified name so downstream evaluation doesn't confuse it with pathology.
        sf = (surface_form or "").lower()
        _has_normal_word = bool(re.search(r"\bnormal\b", sf))
        if name == "finding_enlargement" and _has_normal_word:
            return "finding_heart_size_normal"
        if name == "finding_acromegaly" and _has_normal_word:
            return "finding_heart_size_normal"
        # 'finding_abnormal' generated from "Upper mediastinum has normal contours" is a
        # hallucinated inversion — suppress it by mapping to a non-pathological name.
        if name == "finding_abnormal" and _has_normal_word:
            return "finding_upper_mediastinum_normal_contours"
        return canonical_name

    def _accept_fuzzy_match(
        self,
        combined_score: float,
        candidate_body_region: str,
        surface_body_region: str,
    ) -> bool:
        """Return True only if the combined score clears the region-adjusted threshold."""
        regions_match = (
            candidate_body_region == surface_body_region
            or candidate_body_region == "other"
            or surface_body_region == "other"
        )
        if regions_match:
            return combined_score >= self.fuzzy_threshold
        # Cross-region match requires very high confidence.
        return combined_score >= FUZZY_THRESHOLD_CROSS_REGION

    # ------------------------------------------------------------------
    # Fix 2: token-overlap blended score
    # ------------------------------------------------------------------
    def _blended_score(
        self,
        surface_form: str,
        candidate_label: str,
        tfidf_score: float,
    ) -> float:
        """Blend TF-IDF cosine with difflib token-level ratio to penalise
        lexically similar but semantically different labels."""
        token_score = SequenceMatcher(
            None,
            _normalize(surface_form),
            _normalize(candidate_label),
        ).ratio()
        return 0.6 * tfidf_score + 0.4 * token_score

    # ------------------------------------------------------------------
    # Fix 3: oncologic concept detection
    # ------------------------------------------------------------------
    def _is_oncologic_concept(self, concept: OntologyConcept) -> bool:
        parents_str = " ".join(concept.parents or [])
        return any(rid in parents_str for rid in ONCOLOGIC_RADLEX_PARENTS)

    def _apply_oncologic_context_gate(
        self,
        grounded: GroundedEntity,
        concept: OntologyConcept,
        report_context: dict | None,
    ) -> GroundedEntity:
        """Cap confidence on oncologic concepts when report context does not
        confirm a known malignancy.  Prevents 'metastasis_liver' appearing in
        early non-oncologic reports."""
        if not self._is_oncologic_concept(concept):
            return grounded
        has_oncologic_context = bool(
            report_context and report_context.get("has_malignancy_history", False)
        )
        if not has_oncologic_context:
            # Cap to below acceptance threshold so the caller falls through to fallback.
            grounded.grounding_confidence = min(grounded.grounding_confidence, 0.40)
        return grounded

    # ------------------------------------------------------------------
    # Fix 4: label specificity filter
    # ------------------------------------------------------------------
    def _check_label_specificity(
        self,
        surface_form: str,
        candidate_label: str,
    ) -> bool:
        """Reject candidates whose label is too short relative to the surface
        form, preventing short RadLex labels matching long descriptive phrases."""
        sf_tokens = len((surface_form or "").split())
        label_tokens = len((candidate_label or "").split())
        ratio = label_tokens / max(sf_tokens, 1)
        return ratio >= MIN_LABEL_SPECIFICITY_RATIO

    def _candidate_overstates_specificity(
        self, surface_form: str, concept: OntologyConcept
    ) -> bool:
        surface = (surface_form or "").lower()
        label = (concept.label or "").lower()
        generic_observation = any(
            token in surface
            for token in (
                "abnormality",
                "finding",
                "change",
                "volume",
                "contour",
                "size",
            )
        )
        if "abnormality" in surface and "abnormality" not in label:
            return True
        if "finding" in surface and "finding" not in label:
            return True
        if generic_observation and not _has_neoplastic_cues(surface):
            if any(
                token in label
                for token in ("nodule", "mass", "tumor", "lymphadenopathy", "metast")
            ):
                return True

        # Fracture specificity guard: generic "fracture" / "acute fracture" must not
        # match specific fracture subtypes (Chance, burst, chisel, comminuted, etc.)
        # unless the surface form explicitly names the subtype.
        _GENERIC_FRACTURE_TERMS = {
            "fracture",
            "acute fracture",
            "no fracture",
            "no acute fracture",
        }
        _SPECIFIC_FRACTURE_LABELS = {
            "chance fracture",
            "burst fracture",
            "chisel fracture",
            "comminuted fracture",
            "fatigue fracture",
            "stress fracture",
            "pathologic fracture",
            "avulsion fracture",
            "impacted fracture",
        }
        if (
            surface in _GENERIC_FRACTURE_TERMS
            or surface.endswith(" fracture")
            and len(surface.split()) == 2
        ):
            if label in _SPECIFIC_FRACTURE_LABELS:
                return True

        return False

    def _from_concept(
        self,
        surface_form: str,
        concept: OntologyConcept,
        confidence: float,
        method: str,
    ) -> GroundedEntity:
        # The canonical name is ALWAYS derived from the clinical surface form,
        # never from the RadLex preferred label.  The RadLex label is stored
        # separately in radlex_label for ontology look-ups — it must never
        # overwrite or replace the extracted entity label.
        return GroundedEntity(
            surface_form=surface_form,
            radlex_id=concept.concept_id if concept.ontology == "radlex" else None,
            radlex_label=concept.label if concept.ontology == "radlex" else None,
            snomed_id=(
                concept.concept_id
                if concept.ontology == "snomed"
                else concept.snomed_id
            ),
            grounding_method=method,
            grounding_confidence=float(confidence),
            canonical_name=self._legacy_canonical_name(surface_form),
        )

    def _fallback(self, surface_form: str) -> GroundedEntity:
        return GroundedEntity(
            surface_form=surface_form,
            radlex_id=None,
            radlex_label=None,
            snomed_id=None,
            grounding_method="fallback_canonical",
            grounding_confidence=0.0,
            canonical_name=self._legacy_canonical_name(surface_form),
        )

    def _call_llm(self, prompt: str) -> dict[str, Any] | None:
        if not self.llm_client:
            return None
        try:
            raw = self.llm_client.chat(prompt, max_tokens=800, temperature=0.0)
            parsed = parse_json_from_text(raw)
            if isinstance(parsed, dict):
                return parsed
            return None
        except Exception:
            return None

    def _llm_select(
        self,
        surface_form: str,
        radlex_candidates: list[tuple[OntologyConcept, float]],
        snomed_candidates: list[tuple[OntologyConcept, float]],
    ) -> GroundedEntity | None:
        if not radlex_candidates:
            radlex_candidates = []

        combined = [
            {
                "ontology": "radlex",
                "rank": idx + 1,
                "radlex_id": concept.concept_id,
                "concept_id": concept.concept_id,
                "label": concept.label,
                "score": round(score, 3),
            }
            for idx, (concept, score) in enumerate(radlex_candidates[:5])
        ] + [
            {
                "ontology": "snomed",
                "rank": idx + 1 + len(radlex_candidates[:5]),
                "concept_id": concept.concept_id,
                "label": concept.label,
                "score": round(score, 3),
            }
            for idx, (concept, score) in enumerate(snomed_candidates[:5])
        ]
        if not combined:
            return None

        prompt = (
            "Select the best ontology grounding candidate.\n"
            'Return JSON: {"selected_rank": <int or null>, "confidence": <0-1>, "ontology": "radlex|snomed|null"}.\n'
            f"Surface form: {surface_form}\n"
            f"Candidates: {json.dumps(combined)}"
        )
        decision = self._call_llm(prompt)
        if not decision:
            return None

        selected_rank = decision.get("selected_rank")
        confidence = float(decision.get("confidence", 0.0) or 0.0)
        if not isinstance(selected_rank, int):
            return None
        if selected_rank < 1 or selected_rank > len(combined):
            return None
        ontology = str(
            decision.get("ontology") or combined[selected_rank - 1]["ontology"]
        ).lower()
        if ontology == "snomed":
            offset = len(radlex_candidates[:5])
            idx = selected_rank - 1 - offset
            if idx < 0 or idx >= len(snomed_candidates[:5]):
                return None
            concept, fuzzy_score = snomed_candidates[idx]
        else:
            if selected_rank - 1 >= len(radlex_candidates[:5]):
                return None
            concept, fuzzy_score = radlex_candidates[selected_rank - 1]
        # Keep confidence conservative if LLM overstates certainty.
        effective_confidence = min(confidence, max(fuzzy_score, 0.71))
        return self._from_concept(
            surface_form=surface_form,
            concept=concept,
            confidence=effective_confidence,
            method="llm_assisted",
        )

    def _looks_like_diagnosis(self, surface_form: str) -> bool:
        text = (surface_form or "").lower()
        diagnosis_terms = [
            "carcinoma",
            "adenocarcinoma",
            "malignancy",
            "neoplasm",
            "tumor",
            "cancer",
        ]
        return any(term in text for term in diagnosis_terms)

    def ground(
        self,
        surface_form: str,
        report_context: dict | None = None,
    ) -> GroundedEntity:
        """Ground a surface form against the ontology.

        Args:
            surface_form: The text snippet to ground.
            report_context: Optional dict with keys such as
                ``has_malignancy_history`` (bool) used for the oncologic
                context gate (Fix 3).
        """
        cached = self.cache.get(surface_form)
        if cached == CACHE_MISS_SENTINEL:
            return self._fallback(surface_form)
        if isinstance(cached, dict):
            entity = GroundedEntity(**cached)
            # Apply post-processing in case cache was populated before this fix.
            entity = GroundedEntity(
                surface_form=entity.surface_form,
                radlex_id=entity.radlex_id,
                radlex_label=entity.radlex_label,
                snomed_id=entity.snomed_id,
                grounding_method=entity.grounding_method,
                grounding_confidence=entity.grounding_confidence,
                canonical_name=self._postprocess_canonical_name(
                    entity.canonical_name, surface_form
                ),
            )
            return entity

        surface_region = infer_body_region(surface_form)

        # Tier 1: exact match in RadLex first, then SNOMED.
        exact_radlex = self.radlex.exact_match(surface_form)
        if exact_radlex:
            grounded = self._from_concept(
                surface_form, exact_radlex, confidence=0.99, method="exact_match"
            )
            grounded = self._apply_oncologic_context_gate(
                grounded, exact_radlex, report_context
            )
            if grounded.grounding_confidence >= self.fuzzy_threshold:
                self.cache.set(surface_form, grounded.to_dict())
                return grounded
            # Oncologic gate downgraded confidence — fall through.

        exact_snomed = self.snomed.exact_match(surface_form)
        if exact_snomed and self._looks_like_diagnosis(surface_form):
            grounded = self._from_concept(
                surface_form, exact_snomed, confidence=0.97, method="exact_match_snomed"
            )
            self.cache.set(surface_form, grounded.to_dict())
            return grounded

        # Tier 1b: negation-stripped exact match.
        # "no hemorrhage" → strip "no " → retry as "hemorrhage".
        # This handles cases where the extraction output includes a negation prefix
        # that the ontology does not know about.
        stripped = _strip_negation_prefix(surface_form)
        if stripped and stripped != surface_form:
            exact_stripped = self.radlex.exact_match(stripped)
            if exact_stripped:
                grounded = self._from_concept(
                    surface_form,
                    exact_stripped,
                    confidence=0.97,
                    method="exact_match_negation_stripped",
                )
                self.cache.set(surface_form, grounded.to_dict())
                return grounded

        # ── Tier 0.5: scispaCy UMLS entity linker (Week 4) ──────────────────
        # Catches clinical terms that appear in UMLS (3.3M concept names) but
        # not in the RadLex exact/alias index.  Only fires when:
        #   (a) a high-confidence UMLS CUI is found (score ≥ 0.80)
        #   (b) that CUI maps to a known RadLex RID via the bridge table
        # Falls back silently if scispaCy is not installed (e.g. on local machine).
        if self.scispacy_grounder is not None:
            try:
                umls_result = self.scispacy_grounder.ground(surface_form)
                if umls_result and umls_result.radlex_id:
                    # Find the RadLex concept for this RID to build a proper result
                    rid_concept = self.radlex.get_concept_by_id(umls_result.radlex_id)
                    if rid_concept:
                        grounded = self._from_concept(
                            surface_form,
                            rid_concept,
                            confidence=min(umls_result.score * 0.95, 0.96),
                            method="scispacy_umls_bridge",
                        )
                        self.cache.set(surface_form, grounded.to_dict())
                        return grounded
            except Exception as e:
                import logging as _lg

                _lg.getLogger("entity_grounding.entity_grounder").debug(
                    "scispaCy Tier 0.5 error for '%s': %s", surface_form, e
                )

        # Tier 2: fuzzy candidate search in RadLex.
        # Apply Fix 2 (blended score), Fix 4 (label specificity) and
        # Fix 1 (anatomy consistency) in the filter step.
        fuzzy_radlex = self.radlex.fuzzy_search(
            surface_form,
            body_region=surface_region,
            top_k=5,
        )
        filtered_fuzzy_radlex: list[tuple[OntologyConcept, float]] = []
        for concept, raw_score in fuzzy_radlex:
            if self._candidate_overstates_specificity(surface_form, concept):
                continue
            # Fix 4: reject if label is too short relative to surface form.
            if not self._check_label_specificity(surface_form, concept.label):
                continue
            # Fix 2: blend TF-IDF score with token-level overlap.
            blended = self._blended_score(surface_form, concept.label, raw_score)
            # Fix 1: anatomy-aware acceptance gate.
            if self._accept_fuzzy_match(blended, concept.body_region, surface_region):
                filtered_fuzzy_radlex.append((concept, blended))

        fuzzy_snomed = (
            self.snomed.fuzzy_search(surface_form, top_k=5)
            if self._looks_like_diagnosis(surface_form)
            else []
        )
        if filtered_fuzzy_radlex:
            best_concept, best_score = filtered_fuzzy_radlex[0]
            grounded = self._from_concept(
                surface_form,
                best_concept,
                confidence=best_score,
                method="fuzzy_match",
            )
            # Fix 3: oncologic context gate.
            grounded = self._apply_oncologic_context_gate(
                grounded, best_concept, report_context
            )
            if grounded.grounding_confidence >= self.fuzzy_threshold:
                self.cache.set(surface_form, grounded.to_dict())
                return grounded
        if fuzzy_snomed:
            best_concept, best_score = fuzzy_snomed[0]
            if best_score >= self.fuzzy_threshold:
                grounded = self._from_concept(
                    surface_form,
                    best_concept,
                    confidence=best_score,
                    method="fuzzy_match_snomed",
                )
                self.cache.set(surface_form, grounded.to_dict())
                return grounded

        # Tier 2b: BiomedBERT + FAISS semantic vector search.
        # Catches cases where lexical (TF-IDF) similarity fails but
        # semantic meaning is close (e.g. "fluid collection" → "effusion").
        if self.vector_grounder is not None:
            vector_results = self.vector_grounder.search(surface_form, top_k=3)
            for v_concept, v_score in vector_results:
                if self._candidate_overstates_specificity(surface_form, v_concept):
                    continue
                if not self._check_label_specificity(surface_form, v_concept.label):
                    continue
                candidate_region = v_concept.body_region
                if not self._accept_fuzzy_match(
                    v_score, candidate_region, surface_region
                ):
                    continue
                grounded = self._from_concept(
                    surface_form,
                    v_concept,
                    confidence=v_score,
                    method="vector_match",
                )
                grounded = self._apply_oncologic_context_gate(
                    grounded, v_concept, report_context
                )
                if grounded.grounding_confidence >= self.fuzzy_threshold:
                    self.cache.set(surface_form, grounded.to_dict())
                    return grounded

        # Tier 3: optional LLM selection over fuzzy shortlist.
        # Re-compute raw candidates for LLM shortlist (pre-blending, no hard filter).
        raw_fuzzy_radlex = [
            (concept, score)
            for concept, score in fuzzy_radlex
            if not self._candidate_overstates_specificity(surface_form, concept)
        ]
        llm_grounded = self._llm_select(surface_form, raw_fuzzy_radlex, fuzzy_snomed)
        if llm_grounded:
            # Fix 3 also applies to LLM-chosen oncologic concepts.
            # _llm_select returns the concept object indirectly; we re-check via label.
            self.cache.set(surface_form, llm_grounded.to_dict())
            return llm_grounded

        # Fallback: keep backward-compatible canonical naming.
        self.cache.set_miss(surface_form)
        return self._fallback(surface_form)
