import { useState, type ReactNode } from "react";
import { ChevronDown, ChevronRight, FileText, FlaskConical, FolderClosed, Loader2, Upload } from "lucide-react";
import type { Demo, SessionInfo } from "../api";
import { TB_LABEL, secs } from "../format";

interface Props {
  demos: Demo[];
  sessions: SessionInfo[]; // open drawings, in tab order
  active: SessionInfo | null;
  onOpenDemo: (id: string) => void;
  onActivate: (sid: string) => void;
}

function Section({ title, children, open = true }: { title: string; children: ReactNode; open?: boolean }) {
  const [o, setO] = useState(open);
  return (
    <div className="tsec">
      <div className="tsec-head" onClick={() => setO(!o)}>
        {o ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        {title}
      </div>
      {o && children}
    </div>
  );
}

const KIND_LABEL = { real: "Real", seeded: "Planted", clean: "Clean" } as const;
const COV: [string, string, string][] = [
  ["fail", "Rules failed", "#d13438"],
  ["warning", "Rules with a warning", "#e39400"],
  ["pass", "Rules passed", "#2e8540"],
  ["not_checked", "Rules not checked", "#9aa3ad"],
  ["not_applicable", "Rules not applicable", "#d5dade"],
];

export function PathFinder({ demos, sessions, active, onOpenDemo, onActivate }: Props) {
  const uploads = sessions.filter((s) => s.live);
  const openByDemo = new Map(sessions.filter((s) => s.demo_id).map((s) => [s.demo_id!, s]));
  const cov = active?.coverage;
  const total = cov ? Object.values(cov).reduce((a, b) => a + b, 0) : 0;
  const tb = active?.title_block ?? {};
  const tbKeys = ["number", "title", "revision", "material", "surface_treatment", "heat_treatment", "scale", "sheet_size", "general_tolerance_standard", "drawn_date", "checked_date"];

  return (
    <div className="pane left">
      <div className="pane-head">
        <FolderClosed size={14} />
        <span className="grow">PathFinder</span>
      </div>
      <div className="pane-body tree">
        <Section title="Drawings">
          <div className="trow" style={{ ["--lvl" as string]: 0 }}>
            <FolderClosed size={14} />
            <span className="lbl">Demo drawings</span>
            <span className="meta">{demos.length}</span>
          </div>
          {demos.map((d) => {
            const s = openByDemo.get(d.id);
            const on = s != null && active?.id === s.id;
            return (
              <div
                key={d.id}
                className={`trow click${on ? " on" : ""}`}
                style={{ ["--lvl" as string]: 1 }}
                onClick={() => (s ? onActivate(s.id) : onOpenDemo(d.id))}
                title={`${d.subtitle}\n${d.note}`}
              >
                {d.kind === "real" ? <FileText size={14} /> : <FlaskConical size={14} />}
                <span className="lbl">{d.title}</span>
                <span className={`chip ${d.kind}`}>{KIND_LABEL[d.kind]}</span>
              </div>
            );
          })}
          <div className="trow" style={{ ["--lvl" as string]: 0 }}>
            <FolderClosed size={14} />
            <span className="lbl">Uploaded</span>
            <span className="meta">{uploads.length}</span>
          </div>
          {uploads.length === 0 && (
            <div className="trow" style={{ ["--lvl" as string]: 1, color: "var(--text-3)" }}>
              <Upload size={13} />
              <span className="lbl">Home ▸ Upload PDF</span>
            </div>
          )}
          {uploads.map((s) => (
            <div key={s.id} className={`trow click${active?.id === s.id ? " on" : ""}`} style={{ ["--lvl" as string]: 1 }} onClick={() => onActivate(s.id)}>
              {s.status === "running" || s.status === "queued" ? <Loader2 size={14} className="spin" /> : <FileText size={14} />}
              <span className="lbl">{s.name}</span>
              <span className="chip live">Live</span>
            </div>
          ))}
        </Section>

        <Section title="Review pipeline">
          {active ? (
            <>
              {active.stages.map((st) => (
                <div key={st.key} className="stage">
                  <span className={`dot ${st.status}`} />
                  <span className="lbl">{st.label}</span>
                  <span className="t">{st.status === "done" || st.status === "running" ? secs(st.seconds) : ""}</span>
                </div>
              ))}
              {active.status === "done" && (
                <div className="stage" style={{ color: "var(--text-2)" }}>
                  <span className="lbl">{active.cached ? "Replayed from cache" : "Live model calls"}</span>
                  <span className="t">{secs(active.seconds)}</span>
                </div>
              )}
            </>
          ) : (
            <div className="stage" style={{ color: "var(--text-3)" }}>
              No drawing open
            </div>
          )}
        </Section>

        <Section title="Rule coverage">
          {cov ? (
            <div className="cov">
              <div style={{ color: "var(--text-2)" }}>
                {total} rules, counted once each (one rule can raise several findings)
              </div>
              <div className="covbar">
                {COV.map(([k, , c]) => (
                  <span key={k} style={{ width: `${(100 * (cov[k as keyof typeof cov] ?? 0)) / Math.max(total, 1)}%`, background: c }} />
                ))}
              </div>
              {COV.map(([k, l, c]) => (
                <div key={k} className="covrow" title={k === "not_checked" ? "No check is built for this rule yet, so it is reported as not checked — never as passed" : undefined}>
                  <span className="swatch" style={{ background: c }} />
                  {l}
                  <span className="n">{cov[k as keyof typeof cov] ?? 0}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="stage" style={{ color: "var(--text-3)" }}>
              —
            </div>
          )}
        </Section>

        <Section title="Title block">
          {Object.keys(tb).length ? (
            <div className="props">
              {tbKeys
                .filter((k) => tb[k])
                .map((k) => (
                  <div key={k} className="prow">
                    <span className="k">{TB_LABEL[k] ?? k}</span>
                    <span className="v">{tb[k]}</span>
                  </div>
                ))}
            </div>
          ) : (
            <div className="stage" style={{ color: "var(--text-3)" }}>
              —
            </div>
          )}
        </Section>
      </div>
    </div>
  );
}
