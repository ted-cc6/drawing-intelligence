import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, ChevronDown, ChevronRight, ListChecks } from "lucide-react";
import type { Finding } from "../api";
import { SEVERITY_COLOR, SOURCE_SHORT, firstZone } from "../format";

interface Props {
  findings: Finding[]; // filtered
  total: number;
  selected: number | null;
  onSelect: (no: number) => void;
  rejected: number;
}

// Three or more findings from the same rule and result (e.g. 35 dimensions with too many decimals) share one
// expandable row, so the list reads by problem. The sheet still boxes each one and the Excel keeps every row.
const GROUP_MIN = 3;

type Col = "no" | "result" | "severity" | "category" | "rule" | "requirement" | "source" | "zone" | "status";
const SEV_ORDER = { critical: 0, major: 1, minor: 2, info: 3 };

const COLS: [Col, string, string][] = [
  ["no", "#", "44px"],
  ["result", "Result", "86px"],
  ["severity", "Severity", "86px"],
  ["category", "Category", "150px"],
  ["rule", "Rule", "84px"],
  ["requirement", "Requirement / comment", "auto"],
  ["source", "Checked by", "86px"],
  ["zone", "Zone", "54px"],
  ["status", "Status", "90px"],
];

function key(f: Finding, c: Col): string | number {
  switch (c) {
    case "no":
      return f.no;
    case "result":
      return f.result;
    case "severity":
      return SEV_ORDER[f.severity];
    case "category":
      return f.category_label;
    case "rule":
      return f.rule_id ?? "";
    case "requirement":
      return f.requirement;
    case "source":
      return f.source;
    case "zone":
      return firstZone(f);
    case "status":
      return f.feedback ?? "";
  }
}

export function FindingsList({ findings, total, selected, onSelect, rejected }: Props) {
  const [sort, setSort] = useState<{ c: Col; asc: boolean }>({ c: "no", asc: true });
  const rows = useMemo(() => {
    const r = [...findings].sort((a, b) => {
      const x = key(a, sort.c);
      const y = key(b, sort.c);
      return (x < y ? -1 : x > y ? 1 : a.no - b.no) * (sort.asc ? 1 : -1);
    });
    return r;
  }, [findings, sort]);
  const open = findings.filter((f) => !f.feedback).length;
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const groups = useMemo(() => {
    const byKey = new Map<string, Finding[]>();
    for (const f of rows) {
      const k = f.rule_id ? `${f.rule_id}|${f.result}` : `#${f.no}`;
      byKey.set(k, [...(byKey.get(k) ?? []), f]);
    }
    return [...byKey.entries()].flatMap(([k, fs]) => (fs.length >= GROUP_MIN ? [{ k, fs }] : fs.map((f) => ({ k: `#${f.no}`, fs: [f] }))));
  }, [rows]);
  const toggle = (k: string) =>
    setExpanded((s) => {
      const n = new Set(s);
      if (n.has(k)) n.delete(k);
      else n.add(k);
      return n;
    });

  const row = (f: Finding, child = false) => (
    <tr key={f.no} className={`${selected === f.no ? "on" : ""}${child ? " child" : ""}`} onClick={() => onSelect(f.no)}>
      <td className="mono">{f.no}</td>
      <td>
        <span className={`res ${f.result}`}>{f.result === "fail" ? "Fail" : "Warning"}</span>
      </td>
      <td>
        <span className="sev" style={{ ["--c" as string]: SEVERITY_COLOR[f.severity] }}>
          {f.severity}
        </span>
      </td>
      <td>{f.category_label}</td>
      <td className="mono">{f.rule_id}</td>
      <td title={f.comment}>
        {f.requirement}
        <span style={{ color: "var(--text-3)" }}> — {f.comment}</span>
      </td>
      <td>
        <span className={`src ${f.source}`}>{SOURCE_SHORT[f.source]}</span>
      </td>
      <td className="mono">{firstZone(f)}</td>
      <td>
        {f.feedback === "accept" ? (
          <span className="status-ok">Accepted</span>
        ) : f.feedback === "reject" ? (
          <span className="status-no">Rejected</span>
        ) : (
          <span style={{ color: "var(--text-3)" }}>Open</span>
        )}
      </td>
    </tr>
  );

  return (
    <div className="pane bottom">
      <div className="pane-head">
        <ListChecks size={14} />
        <span>Findings</span>
        <span style={{ fontWeight: 400, color: "var(--text-2)" }}>
          {findings.length === total ? `${total} findings` : `${findings.length} of ${total} shown`} · {open} open
          {rejected > 0 && ` · ${rejected} dropped by the verifier (no evidence)`}
        </span>
        <span className="grow" />
      </div>
      <div className="pane-body">
        {total === 0 ? (
          <div className="empty">No findings yet. Open a drawing from PathFinder or upload a PDF.</div>
        ) : (
          <table className="grid">
            <colgroup>
              {COLS.map(([c, , w]) => (
                <col key={c} style={{ width: w === "auto" ? undefined : w }} />
              ))}
            </colgroup>
            <thead>
              <tr>
                {COLS.map(([c, l]) => (
                  <th key={c} onClick={() => setSort((s) => ({ c, asc: s.c === c ? !s.asc : true }))}>
                    {l} {sort.c === c && (sort.asc ? <ArrowUp size={10} /> : <ArrowDown size={10} />)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {groups.map(({ k, fs }) => {
                if (fs.length === 1) return row(fs[0]);
                const f = fs[0];
                const isOpen = expanded.has(k) || fs.some((x) => x.no === selected);
                const undecided = fs.filter((x) => !x.feedback).length;
                return [
                  <tr key={k} className="group" onClick={() => toggle(k)} title={isOpen ? "Hide these findings" : "Show each finding"}>
                    <td className="mono">
                      {isOpen ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
                    </td>
                    <td>
                      <span className={`res ${f.result}`}>{f.result === "fail" ? "Fail" : "Warning"}</span>
                    </td>
                    <td>
                      <span className="sev" style={{ ["--c" as string]: SEVERITY_COLOR[f.severity] }}>
                        {f.severity}
                      </span>
                    </td>
                    <td>{f.category_label}</td>
                    <td className="mono">{f.rule_id}</td>
                    <td title={`${fs.length} findings: #${fs.map((x) => x.no).join(", #")}`}>
                      <b>{fs.length} findings</b> · {f.requirement}
                    </td>
                    <td>
                      <span className={`src ${f.source}`}>{SOURCE_SHORT[f.source]}</span>
                    </td>
                    <td className="mono">×{fs.length}</td>
                    <td>{undecided ? <span style={{ color: "var(--text-3)" }}>{undecided} open</span> : <span className="status-ok">All decided</span>}</td>
                  </tr>,
                  ...(isOpen ? fs.map((x) => row(x, true)) : []),
                ];
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
