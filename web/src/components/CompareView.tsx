import type { ReactNode } from "react";
import { FileText, GitCompare, Info, X } from "lucide-react";
import type { Comparison, Demo, Finding, SessionInfo } from "../api";

// The drawing a demo drawing is best compared with (the seeded cam plate is the clean one plus a planted error).
const PAIR: Record<string, string> = { "cam-plate-seeded": "cam-plate-clean", "cam-plate-clean": "cam-plate-seeded" };

export type ComparePick = { sid: string } | { demoId: string };

export function ComparePicker(p: {
  demos: Demo[];
  sessions: SessionInfo[];
  current: SessionInfo;
  onPick: (c: ComparePick) => void;
  onClose: () => void;
}) {
  const open = p.sessions.filter((s) => s.status === "done" && s.id !== p.current.id);
  const best = p.current.demo_id ? PAIR[p.current.demo_id] : undefined;
  const closed = p.demos
    .filter((d) => d.id !== p.current.demo_id && !p.sessions.some((s) => s.demo_id === d.id))
    .sort((a, b) => Number(b.id === best) - Number(a.id === best));
  open.sort((a, b) => Number(b.demo_id === best) - Number(a.demo_id === best));
  return (
    <div className="overlay" style={{ position: "fixed", background: "rgba(20,30,40,0.25)", zIndex: 10 }} onClick={p.onClose}>
      <div className="dialog" style={{ width: 480 }} onClick={(e) => e.stopPropagation()}>
        <div className="dhead">
          <GitCompare size={14} /> Compare this drawing with…
          <span style={{ flex: 1 }} />
          <button className="iconbtn" onClick={p.onClose}>
            <X size={13} />
          </button>
        </div>
        <div className="dbody para">
          <p style={{ marginTop: 0 }} className="muted">
            {p.current.name} is the new revision; pick the old one.
          </p>
          {open.length > 0 && <h4 className="pickh">Open drawings</h4>}
          {open.map((s) => (
            <button key={s.id} className="pickrow" onClick={() => p.onPick({ sid: s.id })}>
              <FileText size={14} /> <b>{s.name}</b>
              {s.demo_id === best && <span className="muted"> · suggested</span>}
            </button>
          ))}
          {closed.length > 0 && <h4 className="pickh">Demo drawings (opens it, from the saved review)</h4>}
          {closed.map((d) => (
            <button key={d.id} className="pickrow" onClick={() => p.onPick({ demoId: d.id })}>
              <FileText size={14} /> <b>{d.title}</b> <span className="muted">{d.subtitle}</span>
              {d.id === best && <span className="muted"> · suggested</span>}
            </button>
          ))}
          {open.length + closed.length === 0 && <div className="empty">No other drawing to compare with.</div>}
        </div>
      </div>
    </div>
  );
}

function Row({ f, extra, onClick }: { f: Finding; extra?: string; onClick: () => void }) {
  const q = f.evidence.find((e) => e.quote)?.quote;
  const zone = f.evidence.find((e) => e.zone)?.zone;
  return (
    <tr onClick={onClick} title="Show this finding on its drawing">
      <td className="mono">{f.rule_id}</td>
      <td>
        <span className={`res ${f.result}`}>{f.result === "fail" ? "Fail" : "Warning"}</span>
      </td>
      <td className="mono" style={extra ? { whiteSpace: "normal" } : undefined}>
        {extra ?? q ?? f.location}
      </td>
      <td className="mono">{zone ?? ""}</td>
      <td>{f.requirement}</td>
    </tr>
  );
}

function Section({ title, children, n }: { title: string; n: number; children: ReactNode }) {
  return (
    <>
      <h3 className="cmph">
        {title} ({n})
      </h3>
      {n === 0 ? (
        <div className="empty" style={{ textAlign: "left", padding: "4px 12px" }}>
          None.
        </div>
      ) : (
        <table className="grid">
          <tbody>{children}</tbody>
        </table>
      )}
    </>
  );
}

export function CompareView({ data, onSelect }: { data: Comparison; onSelect: (sid: string, no: number) => void }) {
  const { findings: f, old, new: cur } = data;
  return (
    <div className="docview">
      <div className="toolbar">
        <GitCompare size={14} /> <b>{old.name}</b> → <b>{cur.name}</b>
      </div>
      {data.notes.map((n) => (
        <div key={n} className="pilotnote">
          <Info size={15} /> {n}
        </div>
      ))}
      <Section title="New" n={f.new.length}>
        {f.new.map((x) => (
          <Row key={x.id} f={x} onClick={() => onSelect(cur.id, x.no)} />
        ))}
      </Section>
      <Section title="Fixed" n={f.fixed.length}>
        {f.fixed.map((x) => (
          <Row key={x.id} f={x} onClick={() => onSelect(old.id, x.no)} />
        ))}
      </Section>
      <Section title="Still open" n={f.still_open.length}>
        {f.still_open.map((x) => (
          <Row key={x.id} f={x} extra={x.was != null ? `was ${x.was} → now ${x.now}` : undefined} onClick={() => onSelect(cur.id, x.no)} />
        ))}
      </Section>
      <h3 className="cmph">Title block</h3>
      {data.title_block.length === 0 ? (
        <div className="empty" style={{ textAlign: "left", padding: "4px 12px" }}>
          No changes.
        </div>
      ) : (
        <table className="grid">
          <tbody>
            {data.title_block.map((c) => (
              <tr key={c.field} style={{ cursor: "default" }}>
                <td className="mono">{c.field}</td>
                <td>
                  {c.old ?? "(empty)"} → {c.new ?? "(empty)"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <h3 className="cmph">Revision table</h3>
      {data.revision_rows.added.length + data.revision_rows.removed.length === 0 ? (
        <div className="empty" style={{ textAlign: "left", padding: "4px 12px" }}>
          No changes.
        </div>
      ) : (
        <table className="grid">
          <tbody>
            {data.revision_rows.added.map((r) => (
              <tr key={`a${r}`} style={{ cursor: "default" }}>
                <td>Added</td>
                <td className="mono">{r}</td>
              </tr>
            ))}
            {data.revision_rows.removed.map((r) => (
              <tr key={`r${r}`} style={{ cursor: "default" }}>
                <td>Removed</td>
                <td className="mono">{r}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
