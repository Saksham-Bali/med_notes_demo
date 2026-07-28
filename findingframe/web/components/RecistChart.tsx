"use client";

import type { RecistAssessment } from "@/lib/types";
import { fmtDate } from "@/lib/format";

/** Minimal, dependency-free SLD timeline. Provenance-first: exact values labeled. */
export function RecistChart({
  assessments,
  baselineSld,
}: {
  assessments: RecistAssessment[];
  baselineSld: number;
}) {
  const pts = assessments
    .map((a) => ({
      date: a.report_date ?? a.date ?? "",
      sld: a.sld_mm ?? a.sum_longest_diameter_mm ?? 0,
      response: a.response ?? null,
    }))
    .filter((p) => p.date);
  if (pts.length === 0) return null;

  const W = 640;
  const H = 220;
  const padL = 44;
  const padR = 16;
  const padT = 16;
  const padB = 34;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;

  const maxSld = Math.max(...pts.map((p) => p.sld), baselineSld) * 1.15 || 1;
  const x = (i: number) => padL + (pts.length === 1 ? innerW / 2 : (i / (pts.length - 1)) * innerW);
  const y = (v: number) => padT + innerH - (v / maxSld) * innerH;

  const baseline = baselineSld || pts[0].sld;
  const nadir = Math.min(...pts.map((p) => p.sld), baseline);
  const prLine = baseline * 0.7; // -30% from baseline => PR
  const pdLine = nadir * 1.2; // +20% from nadir => PD

  const linePath = pts
    .map((p, i) => `${i === 0 ? "M" : "L"} ${x(i).toFixed(1)} ${y(p.sld).toFixed(1)}`)
    .join(" ");

  const respColor: Record<string, string> = {
    PD: "#c0362c",
    PR: "#2f855a",
    CR: "#2f855a",
    SD: "#1b64c9",
  };

  return (
    <div className="overflow-x-auto scroll-thin">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full min-w-[520px]" role="img" aria-label="SLD timeline">
        {[0, 0.25, 0.5, 0.75, 1].map((f) => {
          const val = maxSld * f;
          return (
            <g key={f}>
              <line x1={padL} x2={W - padR} y1={y(val)} y2={y(val)} stroke="#eef2f6" strokeWidth={1} />
              <text x={padL - 6} y={y(val) + 3} textAnchor="end" className="fill-ink-faint" style={{ fontSize: 9 }}>
                {Math.round(val)}
              </text>
            </g>
          );
        })}

        {prLine <= maxSld && (
          <g>
            <line x1={padL} x2={W - padR} y1={y(prLine)} y2={y(prLine)} stroke="#2f855a" strokeWidth={1} strokeDasharray="4 3" opacity={0.55} />
            <text x={W - padR} y={y(prLine) - 3} textAnchor="end" className="fill-good" style={{ fontSize: 8 }}>
              PR threshold (−30% baseline)
            </text>
          </g>
        )}
        {pdLine <= maxSld && Math.abs(pdLine - prLine) > 8 && (
          <g>
            <line x1={padL} x2={W - padR} y1={y(pdLine)} y2={y(pdLine)} stroke="#c0362c" strokeWidth={1} strokeDasharray="4 3" opacity={0.55} />
            <text x={W - padR} y={y(pdLine) - 3} textAnchor="end" className="fill-danger" style={{ fontSize: 8 }}>
              PD threshold (+20% nadir)
            </text>
          </g>
        )}

        <path d={linePath} fill="none" stroke="#1b64c9" strokeWidth={2} />

        {pts.map((p, i) => (
          <g key={`${p.date}-${i}`}>
            <circle cx={x(i)} cy={y(p.sld)} r={4} fill={respColor[p.response ?? "SD"] ?? "#1b64c9"} stroke="#fff" strokeWidth={1.5} />
            <text x={x(i)} y={y(p.sld) - 9} textAnchor="middle" className="fill-ink" style={{ fontSize: 9, fontWeight: 600 }}>
              {p.sld}
            </text>
            <text x={x(i)} y={H - padB + 14} textAnchor="middle" className="fill-ink-muted" style={{ fontSize: 8 }}>
              {fmtDate(p.date)}
            </text>
            {p.response && (
              <text x={x(i)} y={H - padB + 24} textAnchor="middle" style={{ fontSize: 8, fontWeight: 700, fill: respColor[p.response] }}>
                {p.response}
              </text>
            )}
          </g>
        ))}
      </svg>
    </div>
  );
}
