"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { ProgressionTarget, RecistProgression } from "@/lib/types";
import { Badge, Button, Card } from "./ui";
import type { Tone } from "./ui";
import { fmtDate } from "@/lib/format";
import { AlertTriangle, ArrowRight } from "lucide-react";

// Categorical hues for the target lesions — identity, not magnitude. Validated with the
// palette checker on a white surface, all pairs: worst CVD separation 12.6 (deutan),
// worst normal-vision separation 22.9, all three clear 3:1 contrast. Deliberately NOT the
// status tokens (danger/good/warn), which stay reserved for the RECIST call.
const LESION_HUES = ["#2b6fd4", "#c2620a", "#a02a8a"];
const SLD_INK = "#12181f";
const PD_INK = "#c0362c";
const PR_INK = "#2f855a";

const TONE: Record<string, Tone> = { PD: "danger", PR: "good", CR: "good", SD: "info" };
const CALL_NAME: Record<string, string> = {
  PD: "Progressive disease",
  PR: "Partial response",
  CR: "Complete response",
  SD: "Stable disease",
  NE: "Not evaluable",
};

function tone(call: string | null | undefined): Tone {
  return (call && TONE[call]) || "quiet";
}

function signed(n: number, digits = 1): string {
  return `${n > 0 ? "+" : ""}${n.toFixed(digits)}`;
}

/** "Feb '24" — 11 ticks have to sit side by side without colliding. */
function tickLabel(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  const month = d.toLocaleDateString(undefined, { month: "short" });
  return `${month} '${String(d.getFullYear()).slice(2)}`;
}

/** The finding half of "Primary tumor — left thorax": short enough to ride the line end. */
function shortName(t: ProgressionTarget): string {
  return t.display_name.split(" — ")[0] || t.confirmed_track_key;
}

// ---------------------------------------------------------------------------

export function ProgressionStory({
  progression,
  subjectCode,
  reviewHref,
}: {
  progression: RecistProgression;
  subjectCode?: string | null;
  reviewHref?: string;
}) {
  const tl = progression.timeline;
  const [hover, setHover] = useState<number | null>(null);
  const pending = progression.unconfirmed_targets ?? [];

  const n = tl.length;
  if (n === 0) {
    return <NoTrajectory pending={pending} reviewHref={reviewHref} />;
  }

  const last = tl[n - 1];
  const prev = n > 1 ? tl[n - 2] : null;
  const nadirIndex = tl.reduce((best, p, i) => (p.sld_mm < tl[best].sld_mm ? i : best), 0);
  const changed = Boolean(prev && prev.classification !== last.classification);
  // If an earlier scan carried the same burden but a different call, say so — it is the
  // shortest possible proof that this answer cannot be read off the newest report alone.
  const twin = tl.findIndex(
    (p, i) => i < n - 1 && p.sld_mm === last.sld_mm && p.classification !== last.classification
  );

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-xl font-semibold text-ink">Disease trajectory</h1>
        <p className="mt-1 text-sm text-ink-muted max-w-3xl">
          {subjectCode ? <span className="font-mono">{subjectCode}</span> : "This patient"} ·{" "}
          {n} scans from {fmtDate(tl[0].date)} to {fmtDate(last.date)}. Every diameter below
          is a human-confirmed target lesion; the response call is RECIST 1.1 applied to
          their sum.
        </p>
      </header>

      {pending.length > 0 && (
        <PendingBanner pending={pending} reviewHref={reviewHref} partial />
      )}

      <Verdict
        prev={prev}
        last={last}
        changed={changed}
        scanNumber={n}
        twin={twin >= 0 ? { index: twin, point: tl[twin] } : null}
      />

      <Card className="p-5">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-sm font-semibold text-ink">Tumour burden across every scan</h2>
          <p className="text-2xs text-ink-muted">
            Sum of the three target diameters (SLD), in millimetres
          </p>
        </div>
        <BurdenChart
          progression={progression}
          hover={hover}
          setHover={setHover}
          nadirIndex={nadirIndex}
        />
      </Card>

      <Card className="p-5">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-sm font-semibold text-ink">Each target lesion, scan by scan</h2>
          <p className="text-2xs text-ink-muted">Longest diameter, in millimetres</p>
        </div>
        <Legend targets={progression.targets} />
        <LesionChart progression={progression} hover={hover} setHover={setHover} />
      </Card>

      <TrajectoryTable progression={progression} nadirIndex={nadirIndex} />
    </div>
  );
}

// ---------------------------------------------------------------------------

type Pending = { confirmed_track_key: string; display_name: string }[];

/** The trajectory is gated, not missing. Say which lesions are holding it and where to go. */
function PendingBanner({
  pending,
  reviewHref,
  partial = false,
}: {
  pending: Pending;
  reviewHref?: string;
  partial?: boolean;
}) {
  return (
    <div className="rounded-xl border-2 border-warn/40 bg-warn-soft/50 p-4">
      <div className="flex items-start gap-2">
        <AlertTriangle className="mt-0.5 w-4 h-4 shrink-0 text-warn-ink" aria-hidden />
        <div className="min-w-0">
          <p className="text-sm font-semibold text-warn-ink">
            {pending.length} target {pending.length === 1 ? "lesion is" : "lesions are"}{" "}
            waiting for re-confirmation
          </p>
          <p className="mt-1 text-xs text-ink-soft max-w-2xl">
            The new report moved the RECIST call, so this run asks a human to re-attest that
            these are the same lesions before the response is recomputed. Until they are
            confirmed the trajectory {partial ? "is incomplete" : "cannot be drawn"} — it is
            withheld, not missing.
          </p>
          <ul className="mt-2 space-y-0.5">
            {pending.map((p) => (
              <li key={p.confirmed_track_key} className="text-xs text-ink-soft">
                {p.display_name}
              </li>
            ))}
          </ul>
          {reviewHref && (
            <Link href={reviewHref} className="mt-2 inline-block">
              <Button size="sm">Confirm in the review workbench →</Button>
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}

function NoTrajectory({ pending, reviewHref }: { pending: Pending; reviewHref?: string }) {
  if (pending.length > 0) {
    return (
      <div className="space-y-4">
        <h1 className="text-xl font-semibold text-ink">Disease trajectory</h1>
        <PendingBanner pending={pending} reviewHref={reviewHref} />
      </div>
    );
  }
  return (
    <Card className="p-6">
      <p className="text-sm font-semibold text-ink">No measurable timepoints</p>
      <p className="mt-1 text-xs text-ink-muted max-w-xl">
        Target lesions are selected but no scan carries a measurement, so there is no
        trajectory to draw. RECIST is never estimated from unmeasured findings.
      </p>
    </Card>
  );
}

function Verdict({
  prev,
  last,
  changed,
  scanNumber,
  twin,
}: {
  prev: RecistProgression["timeline"][number] | null;
  last: RecistProgression["timeline"][number];
  changed: boolean;
  scanNumber: number;
  twin: { index: number; point: RecistProgression["timeline"][number] } | null;
}) {
  return (
    <Card className={changed ? "border-2 border-danger/40 p-5" : "p-5"}>
      <div className="grid gap-4 sm:grid-cols-[1fr_auto_1fr] sm:items-center">
        {prev ? (
          <Timepoint
            heading={`After scan ${scanNumber - 1}`}
            point={prev}
            muted
          />
        ) : (
          <div />
        )}
        <ArrowRight className="hidden w-6 h-6 text-ink-faint sm:block" aria-hidden />
        <Timepoint heading={`After scan ${scanNumber}`} point={last} />
      </div>

      {changed && prev && (
        <p className="mt-4 border-t border-line pt-3 text-sm text-ink-soft max-w-3xl">
          The tumour burden is still{" "}
          <strong className="text-ink">{Math.abs(last.pct_from_baseline).toFixed(0)}% below</strong>{" "}
          where it started, which on its own reads like a continuing response. But RECIST 1.1
          measures progression against the <strong className="text-ink">nadir</strong> — the
          smallest the disease ever got — and calls it only when the rise clears{" "}
          <strong className="text-ink">both</strong> 20% and 5&nbsp;mm. At scan{" "}
          {scanNumber - 1} the rise was {signed(prev.pct_from_nadir)}% and{" "}
          {signed(prev.abs_from_nadir_mm, 0)}&nbsp;mm — under the line. At scan {scanNumber}{" "}
          it is {signed(last.pct_from_nadir)}% and {signed(last.abs_from_nadir_mm, 0)}&nbsp;mm
          — over it on both tests.
        </p>
      )}

      {twin && (
        <p className="mt-2 text-sm text-ink-soft max-w-3xl">
          Scan {twin.index + 1} carried the same {twin.point.sld_mm}&nbsp;mm burden and was
          called {twin.point.classification}. Nothing in scan {scanNumber} on its own
          separates the two — the {scanNumber - twin.index - 2} scans of history between
          them do.
        </p>
      )}
    </Card>
  );
}

function Timepoint({
  heading,
  point,
  muted = false,
}: {
  heading: string;
  point: RecistProgression["timeline"][number];
  muted?: boolean;
}) {
  return (
    <div className={muted ? "opacity-70" : undefined}>
      <p className="text-2xs uppercase tracking-wide text-ink-muted">
        {heading} · {fmtDate(point.date)}
      </p>
      <div className="mt-1.5 flex items-center gap-2">
        <Badge tone={tone(point.classification)} className="text-xs">
          {point.classification}
        </Badge>
        <span className={muted ? "text-sm text-ink-soft" : "text-sm font-semibold text-ink"}>
          {CALL_NAME[point.classification] ?? point.classification}
        </span>
      </div>
      <dl className="mt-2 space-y-0.5 text-xs text-ink-muted">
        <div className="flex gap-2">
          <dt className="w-28">Burden</dt>
          <dd className="font-mono tabular-nums text-ink-soft">{point.sld_mm} mm</dd>
        </div>
        <div className="flex gap-2">
          <dt className="w-28">vs baseline</dt>
          <dd className="font-mono tabular-nums text-ink-soft">
            {signed(point.pct_from_baseline)}%
          </dd>
        </div>
        <div className="flex gap-2">
          <dt className="w-28">vs nadir</dt>
          <dd className="font-mono tabular-nums text-ink-soft">
            {signed(point.pct_from_nadir)}% ({signed(point.abs_from_nadir_mm, 0)} mm)
          </dd>
        </div>
      </dl>
    </div>
  );
}

// ---------------------------------------------------------------------------

const W = 960;
const PAD_L = 46;
const PAD_T = 30;
const PAD_B = 44;

/** Ticks on round numbers (1/2/5 × 10ⁿ), at most six of them. */
function niceTicks(top: number): number[] {
  const candidates = [1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000];
  const step = candidates.find((s) => top / s <= 6) ?? 1000;
  const out: number[] = [];
  for (let v = 0; v <= top + 1e-9; v += step) out.push(v);
  return out;
}

function useScale(n: number, maxValue: number, height: number, padR: number) {
  const innerW = W - PAD_L - padR;
  const innerH = height - PAD_T - PAD_B;
  const top = maxValue * 1.15 || 1;
  return {
    innerW,
    innerH,
    top,
    padR,
    x: (i: number) => PAD_L + (n <= 1 ? innerW / 2 : (i / (n - 1)) * innerW),
    y: (v: number) => PAD_T + innerH - (v / top) * innerH,
  };
}

/** Keep an end-of-series label inside the plot instead of hanging off the edge. */
function anchorFor(i: number, n: number): { anchor: "start" | "middle" | "end"; dx: number } {
  if (i === 0) return { anchor: "start", dx: -2 };
  if (i === n - 1) return { anchor: "end", dx: 2 };
  return { anchor: "middle", dx: 0 };
}

/** Transparent per-timepoint bands so the hit target is the column, not the 8px dot. */
function HoverBands({
  n,
  height,
  padR,
  x,
  onHover,
}: {
  n: number;
  height: number;
  padR: number;
  x: (i: number) => number;
  onHover: (i: number | null) => void;
}) {
  const half = n > 1 ? (x(1) - x(0)) / 2 : (W - PAD_L - padR) / 2;
  return (
    <g onMouseLeave={() => onHover(null)}>
      {Array.from({ length: n }, (_, i) => (
        <rect
          key={i}
          x={x(i) - half}
          y={PAD_T}
          width={half * 2}
          height={height - PAD_T - PAD_B}
          fill="transparent"
          onMouseEnter={() => onHover(i)}
        />
      ))}
    </g>
  );
}

function GridAndAxis({
  dates,
  height,
  padR,
  top,
  x,
  y,
  hover,
}: {
  dates: string[];
  height: number;
  padR: number;
  top: number;
  x: (i: number) => number;
  y: (v: number) => number;
  hover: number | null;
}) {
  return (
    <>
      {niceTicks(top).map((v) => (
        <g key={v}>
          <line x1={PAD_L} x2={W - padR} y1={y(v)} y2={y(v)} stroke="#eef2f6" strokeWidth={1} />
          <text
            x={PAD_L - 8}
            y={y(v) + 3}
            textAnchor="end"
            fill="#9aa5b1"
            style={{ fontSize: 9, fontVariantNumeric: "tabular-nums" }}
          >
            {v}
          </text>
        </g>
      ))}

      {hover !== null && (
        <line
          x1={x(hover)}
          x2={x(hover)}
          y1={PAD_T}
          y2={height - PAD_B}
          stroke="#cbd5e1"
          strokeWidth={1}
        />
      )}

      {dates.map((d, i) => (
        <text
          key={d}
          x={x(i)}
          y={height - PAD_B + 16}
          textAnchor="middle"
          fill={hover === i ? "#12181f" : "#697684"}
          style={{ fontSize: 9, fontWeight: hover === i ? 600 : 400 }}
        >
          {tickLabel(d)}
        </text>
      ))}
      {dates.map((_, i) => (
        <text
          key={`n${i}`}
          x={x(i)}
          y={height - PAD_B + 29}
          textAnchor="middle"
          fill="#9aa5b1"
          style={{ fontSize: 8 }}
        >
          {i + 1}
        </text>
      ))}
    </>
  );
}

function BurdenChart({
  progression,
  hover,
  setHover,
  nadirIndex,
}: {
  progression: RecistProgression;
  hover: number | null;
  setHover: (i: number | null) => void;
  nadirIndex: number;
}) {
  const tl = progression.timeline;
  const n = tl.length;
  const H = 340;
  // Both charts share a right pad so their x-axes line up scan for scan — a reader
  // moving between them is comparing the same columns.
  const PAD_R = 84;
  const baseline = progression.baseline_sld_mm;
  const nadir = progression.nadir_sld_mm ?? tl[nadirIndex].sld_mm;
  const maxValue = Math.max(baseline, ...tl.map((p) => p.sld_mm));
  const { top, x, y } = useScale(n, maxValue, H, PAD_R);

  const prThreshold = baseline * 0.7; // -30% of baseline => partial response
  const pdThreshold = nadir * 1.2; //   +20% over nadir  => progression (with >=5mm)

  const path = tl.map((p, i) => `${i === 0 ? "M" : "L"} ${x(i)} ${y(p.sld_mm)}`).join(" ");
  const lastLeg =
    n > 1 ? `M ${x(n - 2)} ${y(tl[n - 2].sld_mm)} L ${x(n - 1)} ${y(tl[n - 1].sld_mm)}` : "";

  // Points worth a number beside them: the start, the nadir, and the last two scans —
  // the four the story is about. The rest are carried by the axis, tooltip and table.
  const labelled = new Set([0, nadirIndex, n - 2, n - 1].filter((i) => i >= 0));

  return (
    <>
      <ChartFrame
        height={H}
        hover={hover}
        n={n}
        padR={PAD_R}
        setHover={setHover}
        tooltip={hover === null ? null : <BurdenTooltip point={tl[hover]} index={hover} />}
        x={x}
        label="Tumour burden over time"
      >
        {/* The scan that changed the call. */}
        {n > 1 && (
          <>
            <rect
              x={x(n - 2)}
              y={PAD_T}
              width={x(n - 1) - x(n - 2)}
              height={H - PAD_T - PAD_B}
              fill="#c0362c"
              opacity={0.06}
            />
            <text
              x={(x(n - 2) + x(n - 1)) / 2}
              y={PAD_T - 12}
              textAnchor="middle"
              fill="#8f2018"
              style={{ fontSize: 9, fontWeight: 700 }}
            >
              scan {n} arrives
            </text>
          </>
        )}

        <GridAndAxis
          dates={tl.map((p) => p.date)}
          height={H}
          padR={PAD_R}
          top={top}
          x={x}
          y={y}
          hover={hover}
        />

        {/* Thresholds are dashed on purpose — the grid is solid, so dashing reads as a rule
            to cross rather than as a gridline. Labels sit at the left, where the curve is
            nowhere near them, so nothing is clipped by the plot edge. */}
        <Threshold
          y={y(prThreshold)}
          padR={PAD_R}
          color={PR_INK}
          label={`response line · ${prThreshold.toFixed(0)} mm`}
        />
        <Threshold
          y={y(pdThreshold)}
          padR={PAD_R}
          color={PD_INK}
          label={`progression line · ${pdThreshold.toFixed(0)} mm`}
        />

        <path d={path} fill="none" stroke={SLD_INK} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        <path d={lastLeg} fill="none" stroke={PD_INK} strokeWidth={3} strokeLinecap="round" />

        {tl.map((p, i) => {
          const isLast = i === n - 1;
          const isNadir = i === nadirIndex;
          const { anchor, dx } = anchorFor(i, n);
          return (
            <g key={p.date}>
              <circle
                cx={x(i)}
                cy={y(p.sld_mm)}
                r={hover === i ? 6 : isLast || isNadir ? 5 : 4}
                fill={isLast ? PD_INK : SLD_INK}
                stroke="#ffffff"
                strokeWidth={2}
              />
              {labelled.has(i) && (
                <text
                  x={x(i) - dx}
                  y={y(p.sld_mm) - 12}
                  textAnchor={anchor}
                  fill="#12181f"
                  style={{ fontSize: 11, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}
                >
                  {p.sld_mm}
                </text>
              )}
            </g>
          );
        })}

        {/* The nadir is the number the progression test is measured against, so it is named
            on the chart rather than left to the reader to spot as "the lowest dot". */}
        <text
          x={x(nadirIndex)}
          y={y(tl[nadirIndex].sld_mm) + 20}
          textAnchor="middle"
          fill="#697684"
          style={{ fontSize: 9, fontWeight: 600 }}
        >
          nadir
        </text>
      </ChartFrame>
      <p className="mt-2 text-2xs text-ink-muted">
        The response line is 30% below the {baseline.toFixed(0)} mm baseline. The progression
        line is 20% above the {nadir.toFixed(0)} mm nadir — the smallest this disease ever
        got, at scan {nadirIndex + 1}.
      </p>
    </>
  );
}

function Threshold({
  y,
  padR,
  color,
  label,
}: {
  y: number;
  padR: number;
  color: string;
  label: string;
}) {
  return (
    <g>
      <line
        x1={PAD_L}
        x2={W - padR}
        y1={y}
        y2={y}
        stroke={color}
        strokeWidth={1}
        strokeDasharray="5 4"
        opacity={0.7}
      />
      <text x={PAD_L + 4} y={y - 5} fill="#697684" style={{ fontSize: 8.5 }}>
        {label}
      </text>
    </g>
  );
}

function LesionChart({
  progression,
  hover,
  setHover,
}: {
  progression: RecistProgression;
  hover: number | null;
  setHover: (i: number | null) => void;
}) {
  const dates = progression.timeline.map((p) => p.date);
  const n = dates.length;
  const H = 300;
  const PAD_R = 84;
  const byDate = useMemo(
    () =>
      progression.targets.map((t) => {
        const m = new Map(t.series.map((s) => [s.date, s.mm]));
        return { target: t, values: dates.map((d) => m.get(d) ?? null) };
      }),
    [progression.targets, dates]
  );
  const maxValue = Math.max(1, ...byDate.flatMap((s) => s.values.map((v) => v ?? 0)));
  const { top, x, y } = useScale(n, maxValue, H, PAD_R);

  return (
    <ChartFrame
      height={H}
      hover={hover}
      n={n}
      padR={PAD_R}
      setHover={setHover}
      tooltip={
        hover === null ? null : (
          <LesionTooltip date={dates[hover]} rows={byDate} index={hover} />
        )
      }
      x={x}
      label="Each target lesion over time"
    >
      {n > 1 && (
        <rect
          x={x(n - 2)}
          y={PAD_T}
          width={x(n - 1) - x(n - 2)}
          height={H - PAD_T - PAD_B}
          fill="#c0362c"
          opacity={0.06}
        />
      )}

      <GridAndAxis dates={dates} height={H} padR={PAD_R} top={top} x={x} y={y} hover={hover} />

      {byDate.map((s, si) => {
        const hue = LESION_HUES[si % LESION_HUES.length];
        const pts = s.values
          .map((v, i) => (v === null ? null : ([i, v] as [number, number])))
          .filter(Boolean) as [number, number][];
        if (!pts.length) return null;
        const d = pts.map(([i, v], k) => `${k === 0 ? "M" : "L"} ${x(i)} ${y(v)}`).join(" ");
        const [lastI, lastV] = pts[pts.length - 1];
        return (
          <g key={s.target.confirmed_track_key}>
            <path d={d} fill="none" stroke={hue} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
            {pts.map(([i, v]) => (
              <circle
                key={i}
                cx={x(i)}
                cy={y(v)}
                r={hover === i ? 5.5 : 4}
                fill={hue}
                stroke="#ffffff"
                strokeWidth={2}
              />
            ))}
            {/* Value at the line end; identity comes from the legend and the coloured dot
                beside it, never from colouring the text. */}
            <text
              x={x(lastI) + 12}
              y={y(lastV) + 3}
              fill="#3a4652"
              style={{ fontSize: 10, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}
            >
              {lastV} mm
            </text>
          </g>
        );
      })}
    </ChartFrame>
  );
}

function Legend({ targets }: { targets: ProgressionTarget[] }) {
  return (
    <ul className="mt-2 flex flex-wrap gap-x-5 gap-y-1">
      {targets.map((t, i) => (
        <li key={t.confirmed_track_key} className="flex items-center gap-1.5">
          <span
            className="inline-block h-0.5 w-4 rounded-full"
            style={{ backgroundColor: LESION_HUES[i % LESION_HUES.length] }}
            aria-hidden
          />
          <span className="text-xs text-ink-soft">{t.display_name}</span>
        </li>
      ))}
    </ul>
  );
}

// ---------------------------------------------------------------------------

/** Scroll frame + hover/keyboard layer shared by both charts. */
function ChartFrame({
  children,
  height,
  hover,
  n,
  padR,
  setHover,
  tooltip,
  x,
  label,
}: {
  children: React.ReactNode;
  height: number;
  hover: number | null;
  n: number;
  padR: number;
  setHover: (i: number | null) => void;
  tooltip: React.ReactNode;
  x: (i: number) => number;
  label: string;
}) {
  return (
    <div className="mt-3 overflow-x-auto scroll-thin">
      <div className="relative min-w-[680px]">
        <svg
          viewBox={`0 0 ${W} ${height}`}
          className="w-full focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 rounded"
          role="img"
          aria-label={label}
          tabIndex={0}
          onFocus={() => {
            if (hover === null) setHover(0);
          }}
          onBlur={() => setHover(null)}
          onKeyDown={(e) => {
            if (e.key === "ArrowRight") {
              e.preventDefault();
              setHover(Math.min(n - 1, (hover ?? -1) + 1));
            } else if (e.key === "ArrowLeft") {
              e.preventDefault();
              setHover(Math.max(0, (hover ?? n) - 1));
            } else if (e.key === "Escape") {
              setHover(null);
            }
          }}
        >
          {children}
          <HoverBands n={n} height={height} padR={padR} x={x} onHover={setHover} />
        </svg>
        {tooltip !== null && hover !== null && (
          <div
            className="pointer-events-none absolute top-1 z-10 -translate-x-1/2 rounded-lg border border-line bg-paper px-3 py-2 shadow-pop"
            style={{ left: `${(x(hover) / W) * 100}%` }}
          >
            {tooltip}
          </div>
        )}
      </div>
    </div>
  );
}

function BurdenTooltip({
  point,
  index,
}: {
  point: RecistProgression["timeline"][number];
  index: number;
}) {
  return (
    <div className="min-w-[9rem] space-y-1">
      <p className="text-2xs text-ink-muted">
        Scan {index + 1} · {fmtDate(point.date)}
      </p>
      <p className="text-sm font-semibold text-ink tabular-nums">{point.sld_mm} mm</p>
      <p className="text-2xs text-ink-muted tabular-nums">
        {signed(point.pct_from_baseline)}% vs baseline · {signed(point.pct_from_nadir)}% vs
        nadir
      </p>
      <Badge tone={tone(point.classification)}>{point.classification}</Badge>
    </div>
  );
}

function LesionTooltip({
  date,
  rows,
  index,
}: {
  date: string;
  rows: { target: ProgressionTarget; values: (number | null)[] }[];
  index: number;
}) {
  return (
    <div className="min-w-[11rem] space-y-1">
      <p className="text-2xs text-ink-muted">
        Scan {index + 1} · {fmtDate(date)}
      </p>
      <ul className="space-y-0.5">
        {rows.map((r, i) => (
          <li key={r.target.confirmed_track_key} className="flex items-center gap-2 text-xs">
            <span
              className="inline-block h-0.5 w-3 shrink-0 rounded-full"
              style={{ backgroundColor: LESION_HUES[i % LESION_HUES.length] }}
              aria-hidden
            />
            <span className="flex-1 truncate text-ink-soft">{shortName(r.target)}</span>
            <span className="font-mono tabular-nums text-ink">
              {r.values[index] ?? "—"} mm
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------------------

/** The table twin — every value the charts draw, reachable without colour or hover. */
function TrajectoryTable({
  progression,
  nadirIndex,
}: {
  progression: RecistProgression;
  nadirIndex: number;
}) {
  const dates = progression.timeline.map((p) => p.date);
  const cols = progression.targets.map((t) => {
    const m = new Map(t.series.map((s) => [s.date, s.mm]));
    return { target: t, values: dates.map((d) => m.get(d) ?? null) };
  });

  return (
    <Card className="p-5">
      <h2 className="text-sm font-semibold text-ink">Every measurement</h2>
      <div className="mt-3 overflow-x-auto scroll-thin">
        <table className="w-full text-sm">
          <caption className="sr-only">
            Target lesion diameters, tumour burden and RECIST response by scan
          </caption>
          <thead>
            <tr className="border-b border-line text-left text-2xs uppercase tracking-wide text-ink-faint">
              <th scope="col" className="px-3 py-2 font-semibold">
                Scan
              </th>
              <th scope="col" className="px-3 py-2 font-semibold">
                Date
              </th>
              {cols.map((c) => (
                <th key={c.target.confirmed_track_key} scope="col" className="px-3 py-2 font-semibold">
                  {shortName(c.target)}
                </th>
              ))}
              <th scope="col" className="px-3 py-2 font-semibold">
                Burden
              </th>
              <th scope="col" className="px-3 py-2 font-semibold">
                vs baseline
              </th>
              <th scope="col" className="px-3 py-2 font-semibold">
                vs nadir
              </th>
              <th scope="col" className="px-3 py-2 font-semibold">
                Call
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line-soft">
            {progression.timeline.map((p, i) => (
              <tr key={p.date} className={i === progression.timeline.length - 1 ? "bg-danger-soft/50" : undefined}>
                <th scope="row" className="px-3 py-2 text-left font-normal text-ink-muted tabular-nums">
                  {i + 1}
                </th>
                <td className="px-3 py-2 text-ink-soft">
                  {fmtDate(p.date)}
                  {i === nadirIndex && (
                    <span className="ml-1.5 text-2xs uppercase tracking-wide text-ink-muted">
                      nadir
                    </span>
                  )}
                </td>
                {cols.map((c) => (
                  <td key={c.target.confirmed_track_key} className="px-3 py-2 font-mono tabular-nums text-ink-soft">
                    {c.values[i] ?? "—"}
                  </td>
                ))}
                <td className="px-3 py-2 font-mono tabular-nums font-semibold text-ink">
                  {p.sld_mm}
                </td>
                <td className="px-3 py-2 font-mono tabular-nums text-ink-muted">
                  {signed(p.pct_from_baseline)}%
                </td>
                <td className="px-3 py-2 font-mono tabular-nums text-ink-muted">
                  {signed(p.pct_from_nadir)}% ({signed(p.abs_from_nadir_mm, 0)})
                </td>
                <td className="px-3 py-2">
                  <Badge tone={tone(p.classification)}>{p.classification}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-2xs text-ink-muted">
        Diameters in millimetres. Burden = sum of the target diameters. Progression needs a
        rise over the nadir of at least 20% <em>and</em> 5&nbsp;mm.
      </p>
    </Card>
  );
}
