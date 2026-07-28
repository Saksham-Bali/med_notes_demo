"""
BiomedBERT + FAISS vector-based ontology grounding.

Provides semantic similarity search over RadLex concepts using dense
embeddings from a biomedical language model. This serves as Tier 2b
between TF-IDF fuzzy match (Tier 2a) and LLM-assisted selection (Tier 3),
catching cases where lexical similarity fails but semantic meaning is close.

The FAISS index is built once at startup and cached to disk for fast reload.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .radlex_loader import OntologyConcept, RadLexLoader

# Default model — PubMedBERT fine-tuned for sentence similarity
_DEFAULT_MODEL = "pritamdeka/S-PubMedBert-MS-MARCO"

# Cache directory for precomputed embeddings and FAISS index
_CACHE_DIR = Path("./outputs/cache/vector_index")

# Similarity threshold for accepting a vector match.
# Set higher than TF-IDF to avoid over-specific RadLex matches.
VECTOR_MATCH_THRESHOLD = 0.85


def _ensure_cache_dir() -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR


class VectorGrounder:
    """Semantic vector search over RadLex concepts using FAISS."""

    def __init__(
        self,
        radlex_loader: RadLexLoader | None = None,
        model_name: str = _DEFAULT_MODEL,
        cache_dir: Path | str | None = None,
        threshold: float = VECTOR_MATCH_THRESHOLD,
    ):
        self._radlex_loader = radlex_loader
        self._model_name = model_name
        self._cache_dir = Path(cache_dir) if cache_dir else _CACHE_DIR
        self._threshold = threshold

        # Lazy-loaded
        self._model = None
        self._index = None
        self._concept_map: list[tuple[str, str]] = []  # (concept_id, surface_text)
        self._concepts_by_id: dict[str, OntologyConcept] = {}
        self._loaded = False

    def _load_model(self):
        """Load the sentence transformer model."""
        if self._model is not None:
            return
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(self._model_name)

    def _encode(self, texts: list[str], batch_size: int = 256) -> np.ndarray:
        """Encode texts to normalized embeddings."""
        self._load_model()
        embeddings = self._model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=len(texts) > 1000,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return embeddings.astype(np.float32)

    def _index_path(self) -> Path:
        return self._cache_dir / "faiss_index.bin"

    def _map_path(self) -> Path:
        return self._cache_dir / "concept_map.json"

    def _meta_path(self) -> Path:
        return self._cache_dir / "index_meta.json"

    def _is_cache_valid(self, num_concepts: int) -> bool:
        """Check if cached index matches current concept count."""
        meta_path = self._meta_path()
        if not meta_path.exists():
            return False
        if not self._index_path().exists() or not self._map_path().exists():
            return False
        try:
            meta = json.loads(meta_path.read_text())
            return (
                meta.get("num_concepts") == num_concepts
                and meta.get("model") == self._model_name
            )
        except Exception:
            return False

    def _save_index(self, index, concept_map: list[tuple[str, str]], num_concepts: int):
        """Persist FAISS index and concept map to disk."""
        import faiss

        cache_dir = _ensure_cache_dir() if self._cache_dir == _CACHE_DIR else self._cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)

        faiss.write_index(index, str(self._index_path()))
        self._map_path().write_text(json.dumps(concept_map))
        self._meta_path().write_text(json.dumps({
            "num_concepts": num_concepts,
            "model": self._model_name,
            "num_vectors": len(concept_map),
        }))

    def _load_cached_index(self):
        """Load FAISS index and concept map from disk."""
        import faiss

        self._index = faiss.read_index(str(self._index_path()))
        self._concept_map = json.loads(self._map_path().read_text())

    def build_index(self, radlex_loader: RadLexLoader | None = None) -> None:
        """Build or load the FAISS index from RadLex concepts.

        Each concept contributes multiple vectors: one for the preferred label
        and one for each synonym. All vectors map back to the same concept_id.
        """
        if self._loaded:
            return

        loader = radlex_loader or self._radlex_loader
        if loader is None:
            from .radlex_loader import RadLexLoader as RL
            loader = RL(source_path=os.getenv("RADLEX_SOURCE_PATH"))

        loader.load()
        concepts = list(loader.concepts())
        self._concepts_by_id = {c.concept_id: c for c in concepts}

        # Check cache
        if self._is_cache_valid(len(concepts)):
            print(f"VectorGrounder: loading cached FAISS index ({len(concepts)} concepts)")
            self._load_cached_index()
            self._loaded = True
            return

        # Build fresh index
        print(f"VectorGrounder: building FAISS index for {len(concepts)} concepts...")
        t0 = time.time()

        texts: list[str] = []
        concept_map: list[tuple[str, str]] = []

        for concept in concepts:
            # Add preferred label
            label = concept.label.strip()
            if label:
                texts.append(label)
                concept_map.append((concept.concept_id, label))

            # Add synonyms (deduplicated)
            seen = {label.lower()}
            for syn in concept.synonyms:
                syn_clean = syn.strip()
                if syn_clean and syn_clean.lower() not in seen:
                    seen.add(syn_clean.lower())
                    texts.append(syn_clean)
                    concept_map.append((concept.concept_id, syn_clean))

        # Encode all texts
        embeddings = self._encode(texts)

        # Build FAISS index (inner product on normalized vectors = cosine similarity)
        import faiss

        dim = embeddings.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(embeddings)

        self._index = index
        self._concept_map = concept_map

        # Cache to disk
        self._save_index(index, concept_map, len(concepts))

        elapsed = time.time() - t0
        print(
            f"VectorGrounder: indexed {len(texts)} vectors "
            f"({len(concepts)} concepts) in {elapsed:.1f}s"
        )
        self._loaded = True

    def search(
        self,
        surface_form: str,
        top_k: int = 5,
        threshold: float | None = None,
    ) -> list[tuple[OntologyConcept, float]]:
        """Search for the closest RadLex concepts by semantic similarity.

        Args:
            surface_form: The clinical text to ground.
            top_k: Number of candidates to return.
            threshold: Minimum cosine similarity (default: self._threshold).

        Returns:
            List of (concept, score) tuples, sorted by descending similarity.
        """
        if not self._loaded:
            self.build_index()

        threshold = threshold if threshold is not None else self._threshold
        query = surface_form.strip()
        if not query:
            return []

        # Encode query
        query_vec = self._encode([query])

        # Search FAISS
        scores, indices = self._index.search(query_vec, top_k * 3)
        scores = scores[0]
        indices = indices[0]

        # Deduplicate by concept_id, keeping best score
        best_by_concept: dict[str, float] = {}
        for score, idx in zip(scores, indices):
            if idx < 0:
                continue
            concept_id, _text = self._concept_map[idx]
            if concept_id not in best_by_concept or score > best_by_concept[concept_id]:
                best_by_concept[concept_id] = float(score)

        # Filter and sort
        results: list[tuple[OntologyConcept, float]] = []
        for concept_id, score in sorted(
            best_by_concept.items(), key=lambda x: x[1], reverse=True
        ):
            if score < threshold:
                continue
            concept = self._concepts_by_id.get(concept_id)
            if concept:
                results.append((concept, score))
            if len(results) >= top_k:
                break

        return results

    def best_match(
        self,
        surface_form: str,
        threshold: float | None = None,
    ) -> tuple[OntologyConcept, float] | None:
        """Return the single best matching concept, or None if below threshold."""
        results = self.search(surface_form, top_k=1, threshold=threshold)
        return results[0] if results else None
