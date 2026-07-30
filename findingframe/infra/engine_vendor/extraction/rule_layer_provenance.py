"""Content-addressed provenance for FindingFrame's deterministic rule layer.

The pipeline's central design claim is that identity is *computed, not
predicted*: `fact_graph/frame_linker.py` links frames into tracks using a
deterministic composite key (finding_type | anatomy | laterality), and the
anatomy/laterality views that feed that key come from deterministic lookup
tables and normalization functions, not the LLM. `scripts/build_frame_report_manifest.py`
already hashes the report text that goes into a run. Nothing previously
recorded which version of the *rule layer* -- the anatomy alias map, the
oncology taxonomy, the slot-normalization tables -- produced a given set of
tracks. This module closes that gap (see
`docs/REMEDIATION_PLAN_2026-07-29.md` P2-2).

Scope
-----
Covers exactly the two files named in the remediation plan:

- `extraction/finding_type_taxonomy.py`: the oncology 20-class taxonomy
  (`INITIAL_FINDING_TYPES`), the finding-type alias map (`TAXONOMY_ALIASES`),
  and the anatomy alias map (`ANATOMY_ALIASES`), plus the canonicalization
  functions that fall back to token-level rules when a raw value is not in
  the alias map (`canonicalize_anatomy`, `canonicalize_finding_type`).
- `extraction/frame_slot_normalizer.py`: the anatomy/temporal-change term
  tables and the normalization functions that use them
  (`normalize_anatomy_for_scoring`, `normalize_anatomy_for_linking`,
  `normalize_temporal_change_for_scoring`, and their helpers).

It deliberately does NOT cover the echo/CXR taxonomies in
`finding_type_taxonomy.py` (a separate pipeline not exercised by the
FindingFrame oncology tracking paper), nor `fact_graph/frame_linker.py`'s own
anatomy-parent tables (`_ANATOMY_PARENTS`, `_DEFAULT_ANATOMY_BY_TYPE`, and
friends) -- a related, currently unhashed piece of the rule layer left for a
future pass.

Design: data tables vs. logic
------------------------------
Some of this behavior lives in plain lookup tables (dicts/sets); some lives in
per-finding-type if/elif branches that a table-only hash would miss entirely
(for example `canonicalize_anatomy`'s token-set fallback rules, or
`normalize_anatomy_for_scoring`'s per-finding-type dispatch). Both determine
what track a frame ends up on, so both are fingerprinted, via two different
mechanisms:

- Data tables (dicts, sets, the taxonomy tuple) are hashed over their
  *canonicalized* content: `json.dumps(..., sort_keys=True)` over a structure
  where every `set`/`frozenset` has been converted to a sorted list first.
  This is necessary, not just tidy -- Python's `set` iteration order is not
  guaranteed stable across interpreter runs, so hashing an uncanonicalized
  set's repr could change the fingerprint between two runs over byte-identical
  code. Canonicalizing also means line moves and comment edits elsewhere in
  the file never touch these hashes.
- Functions that hold branching logic are hashed over their source text
  (`inspect.getsource`), concatenated and hashed as one component. This is a
  deliberate, simpler choice over e.g. hashing the AST with comments/docstrings
  stripped: it is easy to reproduce and reason about, at the cost of being
  sensitive to comment-only or whitespace-only edits *inside those specific
  functions*. That conservative bias (an edit that didn't change behavior
  might still change the hash) is preferable here to the alternative (an edit
  that did change behavior silently keeping the same hash).

Each named entry in `rule_layer_fingerprint()["components"]` corresponds to
one table or function group, so a diff between two fingerprints' component
maps tells a reader which piece changed.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import is_dataclass
from typing import Any

from extraction import finding_type_taxonomy as _taxonomy
from extraction import frame_slot_normalizer as _slot_normalizer


RULE_LAYER_FINGERPRINT_VERSION = "rule_layer_fingerprint_v1"


def _canonicalize(value: Any) -> Any:
    """Recursively convert a runtime value into an order-stable, JSON-ready form.

    `set`/`frozenset` -> sorted list (see module docstring on why this is
    required, not optional). Dataclass instances -> their field dict. Dict key
    order is left alone here because `json.dumps(..., sort_keys=True)` sorts
    keys at serialization time regardless of insertion order.
    """
    if isinstance(value, (set, frozenset)):
        return sorted(_canonicalize(item) for item in value)
    if isinstance(value, dict):
        return {key: _canonicalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    if is_dataclass(value) and not isinstance(value, type):
        return _canonicalize(
            {field: getattr(value, field) for field in value.__dataclass_fields__}
        )
    return value


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _hash_value(value: Any) -> str:
    canonical = _canonicalize(value)
    text = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return _sha256_hex(text)


def _hash_source(functions: tuple[Any, ...]) -> str:
    parts = [inspect.getsource(fn) for fn in functions]
    return _sha256_hex("\n".join(parts))


def _component_hashes() -> dict[str, str]:
    return {
        "taxonomy_finding_types": _hash_value(
            _taxonomy.ONCOLOGY_RULE_TABLES["INITIAL_FINDING_TYPES"]
        ),
        "taxonomy_aliases": _hash_value(
            _taxonomy.ONCOLOGY_RULE_TABLES["TAXONOMY_ALIASES"]
        ),
        "anatomy_aliases": _hash_value(
            _taxonomy.ONCOLOGY_RULE_TABLES["ANATOMY_ALIASES"]
        ),
        "anatomy_canonicalization_logic": _hash_source(
            _taxonomy.ONCOLOGY_RULE_LOGIC_FUNCTIONS
        ),
        "slot_normalizer_term_tables": _hash_value(_slot_normalizer.RULE_TABLES),
        "slot_normalizer_logic": _hash_source(_slot_normalizer.RULE_LOGIC_FUNCTIONS),
    }


def rule_layer_fingerprint() -> dict[str, Any]:
    """Return a content-addressed fingerprint of the deterministic rule layer.

    Stable across repeated calls within and across processes for
    byte-identical code (see module docstring on canonicalization). Changes
    whenever any covered table or function's source changes. Intended to be
    recorded into run artifacts alongside model id and prompt version, so a
    reader can tell which rule-layer version produced a given set of tracks.
    """
    components = _component_hashes()
    combined = _hash_value(components)
    return {
        "schema_version": RULE_LAYER_FINGERPRINT_VERSION,
        "components": components,
        "fingerprint_sha256": combined,
        "fingerprint_sha256_16": combined[:16],
    }
