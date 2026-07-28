"""Audit packet — the demo centerpiece. A self-contained JSON bundle for a run:
pseudonymized patient, reproducibility manifest, frames with verbatim evidence, tracks,
human link decisions, target selection, RECIST, reviews, and hash-chained sign-offs.
Also a flat CSV of facts+evidence."""
from __future__ import annotations

import csv
import io
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AuditLog,
    Frame,
    LinkDecision,
    Patient,
    RecistAssessment,
    Review,
    Signoff,
    TargetLesionSelection,
    Track,
)
from app.services import metrics
from app.services import recist as recist_svc  # aliased: a local ``recist`` var shadows below
from app.services.runs import get_run


async def build_audit_packet(
    session: AsyncSession, *, org_id: uuid.UUID, run_id: uuid.UUID
) -> dict:
    run = await get_run(session, org_id=org_id, run_id=run_id)
    patient = (
        await session.execute(
            select(Patient).where(Patient.id == run.patient_id, Patient.org_id == org_id)
        )
    ).scalar_one()

    frames = (
        await session.execute(
            select(Frame).where(Frame.run_id == run_id).order_by(Frame.frame_index)
        )
    ).scalars().all()
    tracks = (
        await session.execute(select(Track).where(Track.run_id == run_id))
    ).scalars().all()
    link_decisions = (
        await session.execute(
            select(LinkDecision).where(LinkDecision.run_id == run_id)
        )
    ).scalars().all()
    target = (
        await session.execute(
            select(TargetLesionSelection)
            .where(TargetLesionSelection.run_id == run_id)
            .order_by(TargetLesionSelection.selected_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    recist = (
        await session.execute(
            select(RecistAssessment)
            .where(RecistAssessment.run_id == run_id)
            .order_by(RecistAssessment.assessment_date)
        )
    ).scalars().all()
    reviews = (
        await session.execute(select(Review).where(Review.run_id == run_id))
    ).scalars().all()
    signoffs = (
        await session.execute(
            select(Signoff)
            .where(Signoff.patient_id == run.patient_id, Signoff.org_id == org_id)
            .order_by(Signoff.signed_at)
        )
    ).scalars().all()

    # Tamper-evident ROI timing (attested by the hash-chained audit_log) and the
    # naive-vs-confirmed RECIST contrast (the money moment) — both surfaced in the packet.
    timing = await metrics.compute_timing(
        session, org_id=org_id, run_id=run_id, patient_id=run.patient_id
    )
    contrast = await recist_svc.compute_contrast(session, org_id=org_id, run_id=run_id)

    return {
        "patient": {
            "id": str(patient.id),
            "subject_code": patient.subject_code,  # pseudonym only, no PII
            "cancer_type": patient.cancer_type,
        },
        "timing": timing,
        "recist_contrast": contrast,
        "manifest": {
            "run_id": str(run.id),
            "manifest_hash": run.manifest_hash,
            "engine_git_sha": run.engine_git_sha,
            "model_provider": run.model_provider,
            "model_id": run.model_id,
            "prompt_version": run.prompt_version,
            "schema_version": run.schema_version,
            "temperature": float(run.temperature) if run.temperature is not None else None,
            "reasoning_effort": run.reasoning_effort,
            "report_manifest": run.report_manifest,
            "status": run.status,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        },
        "frames": [_frame_row(f) for f in frames],
        "tracks": [_track_row(t) for t in tracks],
        "link_decisions": [_link_row(d) for d in link_decisions],
        "target_selection": {
            "selections": target.selections,
            "signature_sha256": target.signature_sha256,
            "selected_at": target.selected_at.isoformat(),
        }
        if target
        else None,
        "recist": [_recist_row(a) for a in recist],
        "reviews": [_review_row(r) for r in reviews],
        "signoffs": [_signoff_row(s) for s in signoffs],
    }


def _frame_row(f: Frame) -> dict:
    return {
        "track_key": f.track_key,
        "source_report_id": f.source_report_id,
        "finding_type": f.finding_type,
        "finding_surface": f.finding_surface,
        "assertion": f.assertion,
        "anatomy": f.anatomy,
        "laterality": f.laterality,
        "temporal_change": f.temporal_change,
        "measurement": f.measurement,
        "evidence_text": f.evidence_text,
        "evidence_span_start": f.evidence_span_start,
        "evidence_span_end": f.evidence_span_end,
        "evidence_verified": f.evidence_verified,
        "review_only": f.review_only,
        "report_version_id": str(f.report_version_id) if f.report_version_id else None,
    }


def _track_row(t: Track) -> dict:
    return {
        "track_key": t.track_key,
        "finding_type": t.finding_type,
        "anatomy": t.anatomy,
        "laterality": t.laterality,
        "latest_status": t.latest_status,
        "progression": t.progression,
        "event_count": t.event_count,
        "unresolved_link": t.unresolved_link,
        "false_split_candidate": t.false_split_candidate,
        "clinical_section": t.clinical_section,
    }


def _link_row(d: LinkDecision) -> dict:
    return {
        "decision": d.decision,
        "primary_track_key": d.primary_track_key,
        "related_track_keys": d.related_track_keys,
        "resulting_track_key": d.resulting_track_key,
        "rationale": d.rationale,
        "decided_by": str(d.decided_by),
        "decided_at": d.decided_at.isoformat(),
        "signature_sha256": d.signature_sha256,
    }


def _recist_row(a: RecistAssessment) -> dict:
    return {
        "assessment_date": a.assessment_date.isoformat(),
        "sld_mm": float(a.sld_mm) if a.sld_mm is not None else None,
        "baseline_sld_mm": float(a.baseline_sld_mm) if a.baseline_sld_mm is not None else None,
        "nadir_sld_mm": float(a.nadir_sld_mm) if a.nadir_sld_mm is not None else None,
        "pct_from_baseline": float(a.pct_from_baseline)
        if a.pct_from_baseline is not None
        else None,
        "classification": a.classification,
        "new_lesion": a.new_lesion,
    }


def _review_row(r: Review) -> dict:
    return {
        "track_key": r.track_key,
        "reviewer_id": str(r.reviewer_id),
        "link_correct": r.link_correct,
        "type_correct": r.type_correct,
        "progression_correct": r.progression_correct,
        "latest_status_correct": r.latest_status_correct,
        "evidence_valid": r.evidence_valid,
        "clinically_significant": r.clinically_significant,
        "comment": r.comment,
        "model_output_visible": r.model_output_visible,
        "created_at": r.created_at.isoformat(),
    }


def _signoff_row(s: Signoff) -> dict:
    return {
        "id": str(s.id),
        "payload_sha256": s.payload_sha256,
        "prev_signoff_sha256": s.prev_signoff_sha256,
        "row_sha256": s.row_sha256,  # tamper-evident chain hash (DB-computed)
        "signed_by": str(s.signed_by),
        "signed_at": s.signed_at.isoformat(),
        "scope": s.scope,
    }


def packet_to_csv(packet: dict) -> str:
    """Flat facts + verbatim evidence (one row per frame)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "subject_code",
            "track_key",
            "source_report_id",
            "finding_type",
            "assertion",
            "anatomy",
            "laterality",
            "temporal_change",
            "evidence_verified",
            "evidence_text",
        ]
    )
    subject = packet["patient"]["subject_code"]
    for f in packet["frames"]:
        writer.writerow(
            [
                subject,
                f["track_key"],
                f["source_report_id"],
                f["finding_type"],
                f["assertion"],
                f["anatomy"],
                f["laterality"],
                f["temporal_change"],
                f["evidence_verified"],
                f["evidence_text"],
            ]
        )
    return buf.getvalue()


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def packet_to_pdf(packet: dict) -> bytes:
    """Render the audit packet as a self-contained PDF audit report (reportlab).

    Shows: title + SYNTHETIC disclaimer, the reproducibility manifest, the ROI timing block,
    the RECIST result + naive-vs-confirmed contrast, a per-fact table with verbatim evidence
    and gate status, the human link decisions, and the sign-off block with the tamper-evident
    chain hashes rendered visibly."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm as MM
    from reportlab.platypus import (
        HRFlowable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        title="FindingFrame Audit Packet",
        leftMargin=16 * MM,
        rightMargin=16 * MM,
        topMargin=16 * MM,
        bottomMargin=16 * MM,
    )
    styles = getSampleStyleSheet()
    h1 = styles["Heading1"]
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], spaceBefore=10, spaceAfter=4)
    body = styles["BodyText"]
    small = ParagraphStyle("small", parent=body, fontSize=7.5, leading=9)
    mono = ParagraphStyle("mono", parent=small, fontName="Courier")
    disclaimer = ParagraphStyle(
        "disclaimer", parent=body, textColor=colors.HexColor("#b00020"),
        fontSize=8.5, leading=11, alignment=TA_LEFT,
    )

    patient = packet.get("patient", {})
    manifest = packet.get("manifest", {})
    timing = packet.get("timing", {})
    contrast = packet.get("recist_contrast") or {}

    story: list = []

    def kv_table(rows: list[tuple[str, str]], key_w: float = 55 * MM) -> Table:
        data = [[Paragraph(f"<b>{k}</b>", small), Paragraph(v, small)] for k, v in rows]
        t = Table(data, colWidths=[key_w, doc.width - key_w])
        t.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#e0e0e0")),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        return t

    # --- title + disclaimer ---
    story.append(Paragraph("FindingFrame — Audit Packet", h1))
    story.append(
        Paragraph(
            f"Patient <b>{_fmt(patient.get('subject_code'))}</b> "
            f"(pseudonymized, no PII) · cancer type {_fmt(patient.get('cancer_type'))} "
            f"· run {_fmt(manifest.get('run_id'))}",
            body,
        )
    )
    story.append(Spacer(1, 3 * MM))
    story.append(
        Paragraph(
            "SYNTHETIC / DEMO DATA where applicable — demo patients and their reports are "
            "hand-authored fiction and are not derived from any real patient.",
            disclaimer,
        )
    )
    story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#888888")))

    # --- reproducibility manifest ---
    story.append(Paragraph("Reproducibility manifest", h2))
    story.append(
        kv_table(
            [
                ("Engine git SHA", _fmt(manifest.get("engine_git_sha"))),
                ("Model", f"{_fmt(manifest.get('model_provider'))} / {_fmt(manifest.get('model_id'))}"),
                ("Prompt version", _fmt(manifest.get("prompt_version"))),
                ("Schema version", _fmt(manifest.get("schema_version"))),
                ("Manifest hash", _fmt(manifest.get("manifest_hash"))),
                ("Status", _fmt(manifest.get("status"))),
            ]
        )
    )

    # --- ROI timing (attested) ---
    story.append(Paragraph("Review timing (cryptographically attested)", h2))
    elapsed = timing.get("elapsed_seconds")
    active = timing.get("active_review_seconds")
    story.append(
        kv_table(
            [
                ("First action at", _fmt(timing.get("first_action_at"))),
                ("Sign-off at", _fmt(timing.get("signoff_at"))),
                ("Elapsed", f"{elapsed:.0f} s" if isinstance(elapsed, (int, float)) else "—"),
                ("Active review time", f"{active} s" if active is not None else "—"),
                ("Source", _fmt(timing.get("source"))),
            ]
        )
    )

    # --- RECIST result + contrast ---
    story.append(Paragraph("RECIST assessment", h2))
    recist_rows = packet.get("recist") or []
    if recist_rows:
        head = ["Date", "SLD (mm)", "% baseline", "New lesion", "Class"]
        data = [[Paragraph(f"<b>{h}</b>", small) for h in head]]
        for a in recist_rows:
            pct = a.get("pct_from_baseline")
            data.append(
                [
                    Paragraph(_fmt(a.get("assessment_date"))[:10], small),
                    Paragraph(_fmt(a.get("sld_mm")), small),
                    Paragraph(f"{pct:+.1f}%" if isinstance(pct, (int, float)) else "—", small),
                    Paragraph(_fmt(a.get("new_lesion")), small),
                    Paragraph(f"<b>{_fmt(a.get('classification'))}</b>", small),
                ]
            )
        t = Table(data, colWidths=[28 * MM, 24 * MM, 26 * MM, 24 * MM, doc.width - 102 * MM])
        t.setStyle(_grid_style(colors))
        story.append(t)
    else:
        story.append(Paragraph("No persisted RECIST assessment for this run.", small))

    if contrast.get("naive") is not None:
        naive = contrast.get("naive") or {}
        confirmed = contrast.get("confirmed") or {}
        story.append(Spacer(1, 2 * MM))
        story.append(
            Paragraph(
                f"<b>Naive vs confirmed contrast:</b> naive = "
                f"<b>{_fmt(naive.get('classification'))}</b> vs confirmed = "
                f"<b>{_fmt(confirmed.get('classification')) if contrast.get('confirmed') else 'n/a'}</b>"
                f" — discrepancy: {_fmt(contrast.get('discrepancy'))}",
                small,
            )
        )
        story.append(Paragraph(_fmt(contrast.get("discrepancy_note")), small))

    # --- per-fact table (verbatim evidence + gate status) ---
    story.append(Paragraph("Facts — verbatim evidence and evidence gate", h2))
    frames = packet.get("frames") or []
    head = ["Finding", "Anatomy / laterality", "Assertion", "Verbatim evidence", "Gate"]
    data = [[Paragraph(f"<b>{h}</b>", small) for h in head]]
    for f in frames:
        anat = _fmt(f.get("anatomy"))
        if f.get("laterality"):
            anat = f"{anat} / {f.get('laterality')}"
        gate = "verified" if f.get("evidence_verified") else "GATE-FAILED"
        data.append(
            [
                Paragraph(_fmt(f.get("finding_type")), small),
                Paragraph(anat, small),
                Paragraph(_fmt(f.get("assertion")), small),
                Paragraph(_fmt(f.get("evidence_text")), small),
                Paragraph(gate, small),
            ]
        )
    t = Table(
        data,
        colWidths=[34 * MM, 30 * MM, 18 * MM, doc.width - 100 * MM, 18 * MM],
        repeatRows=1,
    )
    t.setStyle(_grid_style(colors))
    story.append(t)

    # --- human link decisions ---
    story.append(Paragraph("Human link decisions", h2))
    links = packet.get("link_decisions") or []
    if links:
        head = ["Decision", "Primary track", "Related tracks", "Resulting track", "Signature"]
        data = [[Paragraph(f"<b>{h}</b>", small) for h in head]]
        for d in links:
            related = ", ".join(d.get("related_track_keys") or []) or "—"
            data.append(
                [
                    Paragraph(_fmt(d.get("decision")), small),
                    Paragraph(_fmt(d.get("primary_track_key")), small),
                    Paragraph(related, small),
                    Paragraph(_fmt(d.get("resulting_track_key")), small),
                    Paragraph(_fmt(d.get("signature_sha256")), mono),
                ]
            )
        t = Table(data, colWidths=[20 * MM, 42 * MM, 42 * MM, 34 * MM, doc.width - 138 * MM])
        t.setStyle(_grid_style(colors))
        story.append(t)
    else:
        story.append(Paragraph("No human link decisions recorded for this run.", small))

    # --- sign-off block (tamper-evident chain) ---
    story.append(Paragraph("Sign-off (tamper-evident hash chain)", h2))
    signoffs = packet.get("signoffs") or []
    if signoffs:
        for s in signoffs:
            story.append(
                kv_table(
                    [
                        ("Signed by", _fmt(s.get("signed_by"))),
                        ("Signed at", _fmt(s.get("signed_at"))),
                        ("Scope", _fmt(s.get("scope"))),
                        ("payload_sha256", _fmt(s.get("payload_sha256"))),
                        ("prev_signoff_sha256", _fmt(s.get("prev_signoff_sha256"))),
                        ("row_sha256 (chain hash)", _fmt(s.get("row_sha256"))),
                    ]
                )
            )
            story.append(Spacer(1, 2 * MM))
    else:
        story.append(
            Paragraph("No sign-off yet — nothing has entered the signed record.", small)
        )

    doc.build(story)
    return buf.getvalue()


def _grid_style(colors):  # noqa: ANN001
    from reportlab.platypus import TableStyle

    return TableStyle(
        [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]
    )


async def list_audit(
    session: AsyncSession, *, org_id: uuid.UUID, limit: int = 500
) -> list[AuditLog]:
    rows = (
        await session.execute(
            select(AuditLog)
            .where(AuditLog.org_id == org_id)
            .order_by(AuditLog.id.desc())
            .limit(limit)
        )
    ).scalars().all()
    return list(rows)
