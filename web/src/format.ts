import type { Finding, Severity, Source } from "./api";

export const SEVERITY_COLOR: Record<Severity, string> = {
  critical: "#a4262c",
  major: "#d13438",
  minor: "#e39400",
  info: "#8a94a0",
};

export const SOURCE_LABEL: Record<Source, string> = { code: "Code check", lookup: "Table lookup", llm: "AI reviewer" };
export const SOURCE_SHORT: Record<Source, string> = { code: "Code", lookup: "Lookup", llm: "AI" };

export const REVIEWER_LABEL: Record<string, string> = {
  checks: "Code checks",
  drawing_practice: "AI · drawing practice",
  manufacturability: "AI · manufacturability",
  design_intent: "AI · design intent",
};

export const TB_LABEL: Record<string, string> = {
  number: "Drawing no.",
  title: "Description",
  revision: "Revision",
  material: "Material",
  surface_treatment: "Surface treatment",
  heat_treatment: "Heat treatment",
  scale: "Scale",
  sheet_size: "Sheet size",
  sheet: "Sheet",
  units: "Units",
  weight: "Weight",
  general_tolerance_standard: "Gen. tolerance",
  drawing_type: "Drawing type",
  drawn_by: "Drawn by",
  drawn_date: "Drawn",
  checked_by: "Checked by",
  checked_date: "Checked",
  approved_by: "Approved by",
  approved_date: "Approved",
};

export const money = (v: number | undefined | null) =>
  v == null ? "–" : v === 0 ? "$0.00" : v < 0.01 ? `$${v.toFixed(4)}` : `$${v.toFixed(3)}`;

export const secs = (v: number | null | undefined) => (v == null ? "" : v < 10 ? `${v.toFixed(1)} s` : `${Math.round(v)} s`);

export const firstZone = (f: Finding) => f.evidence.find((e) => e.zone)?.zone ?? "";

export const isAI = (f: Finding) => f.source === "llm";

/** "1 : 2" -> 2 (real size per paper size); null when the scale cannot be read. */
export function scaleFactor(scale: string | null | undefined): number | null {
  const m = /(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)/.exec(scale ?? "");
  if (!m) return null;
  const a = parseFloat(m[1]);
  const b = parseFloat(m[2]);
  return a > 0 && b > 0 ? b / a : null;
}

/** A distance between two sheet-image points, on the paper and at the drawing's scale. */
export function measureText(px: number, pxPerPt: number, factor: number | null): string {
  const paper = ((px / pxPerPt) * 25.4) / 72;
  const fmt = (v: number) => (v >= 100 ? v.toFixed(0) : v.toFixed(1));
  return factor == null || factor === 1
    ? `${fmt(paper)} mm${factor == null ? " on paper (scale not read)" : ""}`
    : `${fmt(paper * factor)} mm at scale (${fmt(paper)} mm on paper)`;
}
