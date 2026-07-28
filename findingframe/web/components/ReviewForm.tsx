"use client";

import { useState } from "react";
import type { Review, ReviewInput, Track } from "@/lib/types";
import { Button, Field, Input, Textarea } from "./ui";
import { cx } from "@/lib/format";
import { Check, CheckCheck } from "lucide-react";

interface CorrectnessBool {
  key: keyof Pick<
    ReviewInput,
    "link_correct" | "type_correct" | "progression_correct" | "latest_status_correct"
  >;
  label: string;
}

const CORRECTNESS: CorrectnessBool[] = [
  { key: "link_correct", label: "Link correct" },
  { key: "type_correct", label: "Type correct" },
  { key: "progression_correct", label: "Progression correct" },
  { key: "latest_status_correct", label: "Latest status correct" },
];

interface DangerBool {
  key: keyof Pick<ReviewInput, "false_merge" | "false_split">;
  label: string;
}
const DANGER: DangerBool[] = [
  { key: "false_merge", label: "False merge (distinct findings linked)" },
  { key: "false_split", label: "False split (same finding split apart)" },
];

function defaults(): ReviewInput {
  return {
    track_key: "",
    reviewed_value: null,
    link_correct: false,
    type_correct: false,
    progression_correct: false,
    latest_status_correct: false,
    false_merge: false,
    false_split: false,
    evidence_valid: false,
    clinically_significant: false,
    comment: "",
  };
}

function CheckRow({
  checked,
  onChange,
  label,
  tone = "accent",
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  tone?: "accent" | "danger" | "good";
}) {
  const ring =
    tone === "danger"
      ? "peer-checked:bg-danger peer-checked:border-danger"
      : tone === "good"
      ? "peer-checked:bg-good peer-checked:border-good"
      : "peer-checked:bg-accent peer-checked:border-accent";
  return (
    <label className="flex items-center gap-2 cursor-pointer select-none py-1">
      <span className="relative inline-flex">
        <input
          type="checkbox"
          className="peer sr-only"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span
          className={cx(
            "w-4 h-4 rounded border border-line-strong bg-paper flex items-center justify-center transition-colors",
            ring
          )}
        >
          <Check className="w-3 h-3 text-white opacity-0 peer-checked:opacity-100" />
        </span>
      </span>
      <span className="text-sm text-ink-soft">{label}</span>
    </label>
  );
}

export function ReviewForm({
  track,
  existing,
  onSubmit,
  submitting,
}: {
  track: Track;
  existing?: Review;
  onSubmit: (input: ReviewInput) => void;
  submitting?: boolean;
}) {
  const [form, setForm] = useState<ReviewInput>(() => {
    const base: ReviewInput = existing
      ? { ...defaults(), ...existing, comment: existing.comment ?? "", reviewed_value: null }
      : defaults();
    base.track_key = track.track_key;
    return base;
  });
  const [showCorrections, setShowCorrections] = useState(false);

  const set = <K extends keyof ReviewInput>(k: K, v: ReviewInput[K]) =>
    setForm((f) => ({ ...f, [k]: v }));

  const markAllCorrect = () =>
    setForm((f) => ({
      ...f,
      link_correct: true,
      type_correct: true,
      progression_correct: true,
      latest_status_correct: true,
      false_merge: false,
      false_split: false,
      evidence_valid: true,
      clinically_significant: f.clinically_significant,
    }));

  const submit = () => {
    onSubmit({
      ...form,
      track_key: track.track_key,
      reviewed_value: {
        finding_type: track.finding_type,
        anatomy: track.anatomy,
        laterality: track.laterality,
        progression: track.progression,
        latest_status: track.latest_status,
      },
    });
  };

  return (
    <div className="rounded-lg border border-line bg-paper-soft p-3 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-2xs uppercase tracking-wide font-semibold text-ink-faint">
          Slot-level review
          {existing && <span className="ml-2 text-good normal-case tracking-normal">· saved</span>}
        </span>
        <Button size="sm" variant="subtle" onClick={markAllCorrect} type="button">
          <CheckCheck className="w-3.5 h-3.5" /> Mark all correct
        </Button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6">
        <div>
          {CORRECTNESS.map((c) => (
            <CheckRow
              key={c.key}
              checked={Boolean(form[c.key])}
              onChange={(v) => set(c.key, v)}
              label={c.label}
              tone="accent"
            />
          ))}
        </div>
        <div>
          <CheckRow
            checked={form.evidence_valid}
            onChange={(v) => set("evidence_valid", v)}
            label="Evidence valid (entails the fact)"
            tone="good"
          />
          <CheckRow
            checked={form.clinically_significant}
            onChange={(v) => set("clinically_significant", v)}
            label="Clinically significant"
            tone="good"
          />
        </div>
      </div>

      <div className="border-t border-line pt-2">
        <span className="text-2xs uppercase tracking-wide font-semibold text-danger-ink">
          Identity danger flags
        </span>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 mt-1">
          {DANGER.map((d) => (
            <CheckRow
              key={d.key}
              checked={Boolean(form[d.key])}
              onChange={(v) => set(d.key, v)}
              label={d.label}
              tone="danger"
            />
          ))}
        </div>
      </div>

      <button
        type="button"
        onClick={() => setShowCorrections((v) => !v)}
        className="text-xs text-accent hover:text-accent-ink font-medium"
      >
        {showCorrections ? "Hide" : "Add"} corrections
      </button>

      {showCorrections && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
          <Field label="Corrected finding type">
            <Input
              value={form.correction_finding_type ?? ""}
              placeholder={track.finding_type}
              onChange={(e) => set("correction_finding_type", e.target.value)}
            />
          </Field>
          <Field label="Corrected anatomy">
            <Input
              value={form.correction_anatomy ?? ""}
              placeholder={track.anatomy ?? ""}
              onChange={(e) => set("correction_anatomy", e.target.value)}
            />
          </Field>
          <Field label="Corrected laterality">
            <Input
              value={form.correction_laterality ?? ""}
              placeholder={track.laterality ?? ""}
              onChange={(e) => set("correction_laterality", e.target.value)}
            />
          </Field>
          <Field label="Corrected latest status">
            <Input
              value={form.correction_latest_status ?? ""}
              placeholder={track.latest_status ?? ""}
              onChange={(e) => set("correction_latest_status", e.target.value)}
            />
          </Field>
        </div>
      )}

      <Field label="Comment">
        <Textarea
          rows={2}
          value={form.comment ?? ""}
          placeholder="Optional note for the audit record…"
          onChange={(e) => set("comment", e.target.value)}
          className="font-sans text-sm"
        />
      </Field>

      <div className="flex justify-end">
        <Button size="sm" onClick={submit} loading={submitting} type="button">
          {existing ? "Update review" : "Save review"} <kbd className="ml-1">c</kbd>
        </Button>
      </div>
    </div>
  );
}
