"""
Agent 3: GC Updater

Maintains append-only longitudinal clinical summaries for cancer patients.
Uses the configured project LLM provider.

Renders GC from Fact Graph in full or incremental mode.
"""

import os
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
from extraction.prompts import (
    FACT_GRAPH_FULL_GC_RENDER_PROMPT,
    FACT_GRAPH_INCREMENTAL_GC_RENDER_PROMPT,
)
from utils.llm import create_default_llm_client




class GCUpdater:
    """
    Renders the Grouped Content (GC) clinical summary from the Fact Graph.
    Supports full re-render and incremental delta modes.
    Uses the configured LLM provider.
    """
    
    def __init__(self, template_path: str = None, llm_client: Any | None = None):
        """Initialize the GC updater with the configured LLM provider."""
        load_dotenv(dotenv_path="config/.env")
        self.llm_client = llm_client or create_default_llm_client()
        self.render_mode = os.getenv("GC_RENDER_MODE", "deterministic").strip().lower()
        
        # Load template
        if template_path:
            self.template_path = Path(template_path)
        else:
            self.template_path = Path(__file__).parent / "gc_template.md"
        
        with open(self.template_path, "r") as f:
            self.template = f.read()
    
    def initialize_gc(self, subject_id: str) -> str:
        """Create a new GC from template for a patient."""
        return self.template.format(
            subject_id=subject_id,
            date=datetime.now().strftime("%Y-%m-%d")
        )

    def _format_event_line(self, event: dict[str, Any]) -> str:
        measurement = event.get("measurement", {}) if isinstance(event, dict) else {}
        mm = measurement.get("normalized_mm") if isinstance(measurement, dict) else None
        raw_text = measurement.get("raw_text") if isinstance(measurement, dict) else None
        is_qual = bool(measurement.get("is_qualitative", False)) if isinstance(measurement, dict) else False
        measurement_str = "qualitative"
        if mm is not None:
            measurement_str = f"{mm} mm"
        elif raw_text:
            measurement_str = str(raw_text)
        modality = str(event.get("modality", "OTHER"))
        date = str(event.get("date", ""))
        trend = str(event.get("trend", "unknown"))
        certainty_label = str(event.get("certainty_label", "unknown"))
        certainty = event.get("certainty", 0.0)
        qual_tag = " (qualitative)" if is_qual else ""

        # Negation-aware rendering (Phase 2)
        is_negated = bool(event.get("is_negated", False))
        negation_lang = event.get("negation_language", "")
        if is_negated:
            entity_name = str(event.get("entity_id", ""))
            negation_tag = f" [ABSENT — {negation_lang}]" if negation_lang else " [ABSENT]"
            return f"~~{entity_name}~~{negation_tag} | {date} | {modality}"

        return (
            f"{date} | {modality} | {measurement_str}{qual_tag} | "
            f"trend={trend} | certainty={certainty_label} ({certainty})"
        )

    def _render_full_from_fact_graph(self, fact_graph: dict[str, Any]) -> str:
        subject_id = str(fact_graph.get("subject_id", "unknown"))
        entities = fact_graph.get("entities", {}) or {}
        lines = [
            "# Longitudinal Clinical Summary",
            "",
            f"**Subject ID:** {subject_id}",
            f"**Rendered At:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Entity Timeline",
        ]

        if not isinstance(entities, dict) or not entities:
            lines.extend(["- No grounded entities available yet.", ""])
            return "\n".join(lines).strip()

        for entity_id in sorted(entities.keys()):
            entity = entities[entity_id] or {}
            entity_type = str(entity.get("entity_type", "finding"))
            status = str(entity.get("status", "unknown"))
            first_doc = str(entity.get("first_documented", ""))
            last_doc = str(entity.get("last_documented", ""))
            radlex_id = str(entity.get("radlex_id", "") or "")
            snomed_id = str(entity.get("snomed_id", "") or "")
            site = str(entity.get("anatomical_site", "") or "")

            lines.append(f"### {entity_id}")
            lines.append(f"- Type: {entity_type}")
            lines.append(f"- Status: {status}")
            if site:
                lines.append(f"- Site: {site}")
            lines.append(f"- First documented: {first_doc}")
            lines.append(f"- Last documented: {last_doc}")
            if radlex_id or snomed_id:
                lines.append(
                    f"- Ontology IDs: RadLex={radlex_id or 'n/a'}, SNOMED={snomed_id or 'n/a'}"
                )

            events = entity.get("events", [])
            if isinstance(events, list) and events:
                lines.append("- Events:")
                for event in sorted(events, key=lambda item: (str(item.get("date", "")), str(item.get("event_id", "")))):
                    lines.append(f"  - {self._format_event_line(event)}")
            else:
                lines.append("- Events: none")
            lines.append("")

        lines.append("## Certainty Trajectories")
        for entity_id in sorted(entities.keys()):
            entity = entities[entity_id] or {}
            trajectory = entity.get("certainty_trajectory", [])
            if not isinstance(trajectory, list) or not trajectory:
                continue
            lines.append(f"- {entity_id}:")
            for point in sorted(trajectory, key=lambda p: str(p.get("date", ""))):
                lines.append(
                    f"  - {point.get('date', '')}: {point.get('certainty_label', 'unknown')} ({point.get('certainty', 0.0)})"
                )
        return self._postprocess_gc("\n".join(lines).strip())

    def _render_incremental_from_events(
        self,
        current_gc: str,
        fact_graph: dict[str, Any],
        new_events: list[dict[str, Any]],
    ) -> str:
        if not current_gc or len(current_gc.strip()) < 20:
            return self._render_full_from_fact_graph(fact_graph)
        if not new_events:
            return current_gc

        by_entity: dict[str, list[dict[str, Any]]] = {}
        for event in new_events:
            if not isinstance(event, dict):
                continue
            entity_id = str(event.get("entity_id", "")).strip() or "unknown_entity"
            by_entity.setdefault(entity_id, []).append(event)

        section_lines = [
            "",
            f"## Incremental Update ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})",
            "",
        ]
        for entity_id in sorted(by_entity.keys()):
            section_lines.append(f"- {entity_id}:")
            for event in sorted(by_entity[entity_id], key=lambda item: (str(item.get("date", "")), str(item.get("event_id", "")))):
                section_lines.append(f"  - {self._format_event_line(event)}")
        updated = (current_gc.rstrip() + "\n" + "\n".join(section_lines)).strip()
        return self._postprocess_gc(updated)

    def _render_incremental_from_events_llm(
        self,
        current_gc: str,
        fact_graph: dict[str, Any],
        new_events: list[dict[str, Any]],
    ) -> str:
        if not current_gc or len(current_gc.strip()) < 20:
            return self._render_full_from_fact_graph_llm(fact_graph)
        if not new_events:
            return current_gc
        prompt = FACT_GRAPH_INCREMENTAL_GC_RENDER_PROMPT.format(
            current_gc=current_gc,
            fact_graph_json=json.dumps(fact_graph, indent=2),
            new_events_json=json.dumps(new_events, indent=2),
        )
        rendered = self._strip_markdown_fences(self._call_llm(prompt))
        if not rendered or len(rendered.strip()) < 50:
            return self._render_incremental_from_events(current_gc, fact_graph, new_events)
        return self._postprocess_gc(rendered)

    def _render_full_from_fact_graph_llm(self, fact_graph: dict[str, Any]) -> str:
        prompt = FACT_GRAPH_FULL_GC_RENDER_PROMPT.format(
            fact_graph_json=json.dumps(fact_graph, indent=2)
        )
        rendered = self._strip_markdown_fences(self._call_llm(prompt))
        if not rendered or len(rendered.strip()) < 50:
            return self._render_full_from_fact_graph(fact_graph)
        return self._postprocess_gc(rendered)

    def render_from_fact_graph(
        self,
        fact_graph: dict[str, Any],
        mode: str = "full",
        current_gc: str | None = None,
        new_events: list[dict[str, Any]] | None = None,
        renderer: str | None = None,
    ) -> str:
        """
        Render GC from Fact Graph.
        - full: regenerate full narrative from graph
        - incremental: append a delta section from newly-added events
        """
        mode_norm = (mode or "full").strip().lower()
        renderer_mode = (renderer or self.render_mode or "deterministic").strip().lower()
        use_llm = renderer_mode == "llm"
        if mode_norm == "incremental":
            if use_llm:
                return self._render_incremental_from_events_llm(
                    current_gc=current_gc or "",
                    fact_graph=fact_graph,
                    new_events=new_events or [],
                )
            return self._render_incremental_from_events(
                current_gc=current_gc or "",
                fact_graph=fact_graph,
                new_events=new_events or [],
            )
        if use_llm:
            return self._render_full_from_fact_graph_llm(fact_graph)
        return self._render_full_from_fact_graph(fact_graph)
    


    def _strip_markdown_fences(self, text: str) -> str:
        if text.startswith("```markdown"):
            text = text[11:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()

    def _normalize_for_dedupe(self, line: str) -> str:
        text = line.strip().lower()
        text = re.sub(r"^[-*]\s*", "", text)
        text = re.sub(r"\s+", " ", text)
        return text

    def _postprocess_gc(self, gc_text: str) -> str:
        """
        Deterministic cleanup pass for LLM output:
        - remove duplicate long lines per section
        - collapse repeated NEW lines
        - normalize blank-line spacing
        """
        lines = gc_text.splitlines()
        cleaned = []
        current_section = "__root__"
        seen_per_section: dict[str, set[str]] = {}
        seen_global_new: set[str] = set()

        for raw_line in lines:
            line = raw_line.rstrip()
            stripped = line.strip()

            if stripped.startswith("#"):
                current_section = stripped.lower()
                seen_per_section.setdefault(current_section, set())
                cleaned.append(stripped)
                continue

            if not stripped:
                if cleaned and cleaned[-1] == "":
                    continue
                cleaned.append("")
                continue

            norm = self._normalize_for_dedupe(stripped)
            if stripped.lower().startswith("new ("):
                if norm in seen_global_new:
                    continue
                seen_global_new.add(norm)

            section_seen = seen_per_section.setdefault(current_section, set())
            # Skip duplicates for informative lines while keeping short structural bullets.
            if len(norm) > 40 and norm in section_seen:
                continue
            section_seen.add(norm)
            cleaned.append(line)

        # Trim trailing blanks.
        while cleaned and cleaned[-1] == "":
            cleaned.pop()
        return "\n".join(cleaned).strip()
    

    
    def _call_llm(self, prompt: str) -> str:
        """Call the configured LLM provider with the given prompt."""
        return self.llm_client.chat(prompt, max_tokens=8000)
    
    def save_gc(
        self,
        gc_content: str,
        subject_id: str,
        output_dir: str = "./outputs/patient_gcs",
        save_history: bool = True
    ) -> str:
        """Save GC to file with optional version history."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Save current GC
        gc_file = output_path / f"subject_{subject_id}.md"
        with open(gc_file, "w") as f:
            f.write(gc_content)
        
        # Save to version history
        if save_history:
            history_file = output_path / f"subject_{subject_id}_history.json"
            
            history = []
            if history_file.exists():
                with open(history_file, "r") as f:
                    history = json.load(f)
            
            history.append({
                "timestamp": datetime.now().isoformat(),
                "content": gc_content
            })
            
            with open(history_file, "w") as f:
                json.dump(history, f, indent=2)
        
        return str(gc_file)
