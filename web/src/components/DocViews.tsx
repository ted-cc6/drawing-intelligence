import { Fragment, useEffect, useMemo, useState } from "react";
import { Download, FileText, FileUp, FlaskConical, Info, Loader2, Search } from "lucide-react";
import type { Demo, ModelChoice, ModelInfo, Role, Rule, SessionInfo } from "../api";
import { api, modelChoice } from "../api";
import { SEVERITY_COLOR, SOURCE_SHORT, money, secs } from "../format";

export function Welcome({ demos, onOpenDemo, onUpload }: { demos: Demo[]; onOpenDemo: (id: string) => void; onUpload: () => void }) {
  return (
    <div className="graphics" style={{ cursor: "default", overflow: "auto" }}>
      <div className="welcome">
        <h1>Drawing Intelligence for Wipro PARI</h1>
        <p className="sub">An AI first pass for the last point check: every finding cites the drawing, and the engineer signs off.</p>
        <div className="cards">
          {demos.map((d) => (
            <button key={d.id} className="dcard" onClick={() => onOpenDemo(d.id)}>
              <span className="ic">{d.kind === "real" ? <FileText size={26} /> : <FlaskConical size={26} />}</span>
              <span className="t">{d.title}</span>
              <span className="s">{d.subtitle}</span>
              <span className="n">{d.note}</span>
            </button>
          ))}
          <button className="dcard" onClick={onUpload}>
            <span className="ic">
              <FileUp size={26} />
            </span>
            <span className="t">Upload a PDF drawing</span>
            <span className="s">Live review with the AI models, about 2 minutes</span>
            <span className="n">Native PDF on the PARI template; deleted when the session ends.</span>
          </button>
        </div>
        <div className="steps">
          {[
            ["1 Intake", "Exact text, symbols and title block read by code"],
            ["2 Understand", "A vision model reads the views and features"],
            ["3 Review", "174-rule rulebook: code checks + AI reviewers"],
            ["4 Verify", "No evidence on the drawing, no finding"],
            ["5 Report", "Excel checklist + annotated sheet"],
          ].map(([b, s]) => (
            <div key={b}>
              <b>{b}</b>
              <span>{s}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function RulebookView({ onDownload }: { onDownload: () => void }) {
  const [data, setData] = useState<{ version: string; rules: Rule[] } | null>(null);
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("");
  const [type, setType] = useState("");
  const [built, setBuilt] = useState("");
  useEffect(() => {
    api.rules().then(setData).catch(() => setData({ version: "?", rules: [] }));
  }, []);
  const cats = useMemo(() => [...new Map((data?.rules ?? []).map((r) => [r.category, r.category_label])).entries()], [data]);
  const rows = (data?.rules ?? []).filter(
    (r) =>
      (!cat || r.category === cat) &&
      (!type || r.check_type === type) &&
      (!built || (built === "yes") === r.built) &&
      (!q || `${r.id} ${r.requirement} ${r.source}`.toLowerCase().includes(q.toLowerCase())),
  );
  if (!data) return <div className="docview empty"><Loader2 size={14} className="spin" /> Loading the rulebook…</div>;
  return (
    <div className="docview">
      <div className="toolbar">
        <Search size={14} />
        <input placeholder="Search rules, e.g. tolerance, IS 919, title block" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: 300 }} />
        <select value={cat} onChange={(e) => setCat(e.target.value)}>
          <option value="">All categories</option>
          {cats.map(([k, l]) => (
            <option key={k} value={k}>
              {l}
            </option>
          ))}
        </select>
        <select value={type} onChange={(e) => setType(e.target.value)}>
          <option value="">All check types</option>
          <option value="code">Code check</option>
          <option value="lookup">Table lookup</option>
          <option value="llm">AI judgement</option>
        </select>
        <select value={built} onChange={(e) => setBuilt(e.target.value)}>
          <option value="">Built and not built</option>
          <option value="yes">Runs today</option>
          <option value="no">Not built yet</option>
        </select>
        <span className="count">
          {rows.length} of {data.rules.length} rules · version <span className="mono">{data.version}</span>
        </span>
        <button className="btn" onClick={onDownload} title="All rules as a spreadsheet">
          <Download size={13} /> Download (.xlsx)
        </button>
      </div>
      <table className="grid">
        <colgroup>
          <col style={{ width: 84 }} />
          <col style={{ width: 150 }} />
          <col />
          <col style={{ width: 78 }} />
          <col style={{ width: 66 }} />
          <col style={{ width: 86 }} />
          <col style={{ width: 230 }} />
        </colgroup>
        <thead>
          <tr>
            <th>Rule</th>
            <th>Category</th>
            <th>Requirement</th>
            <th>Severity</th>
            <th>Check</th>
            <th>Status</th>
            <th>Source</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} style={{ cursor: "default" }}>
              <td className="mono">{r.id}</td>
              <td>{r.category_label}</td>
              <td title={r.requirement}>{r.requirement}</td>
              <td>
                <span className="sev" style={{ ["--c" as string]: SEVERITY_COLOR[r.severity] }}>
                  {r.severity}
                </span>
              </td>
              <td>
                <span className={`src ${r.check_type}`}>{SOURCE_SHORT[r.check_type]}</span>
              </td>
              <td>{r.built ? <span className="status-ok">Runs today</span> : <span style={{ color: "var(--text-3)" }}>Not built</span>}</td>
              <td title={r.source} style={{ color: "var(--text-2)" }}>
                {r.source}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ReportsView({ sessions }: { sessions: SessionInfo[] }) {
  const done = sessions.filter((s) => s.status === "done");
  const cost = done.reduce((a, s) => a + (s.cost_usd ?? 0) + (s.qa_cost_usd ?? 0), 0);
  const avg = done.length ? done.reduce((a, s) => a + (s.seconds ?? 0), 0) / done.length : 0;
  const findings = done.reduce((a, s) => a + (s.findings?.length ?? 0), 0);
  const decided = done.reduce((a, s) => a + (s.findings?.filter((f) => f.feedback).length ?? 0), 0);
  return (
    <div className="docview">
      <div className="kpis">
        <div className="kpi">
          <div className="v">{done.length}</div>
          <div className="l">Reviews this session</div>
        </div>
        <div className="kpi">
          <div className="v">{secs(avg) || "–"}</div>
          <div className="l">Average review time</div>
        </div>
        <div className="kpi">
          <div className="v">{money(cost)}</div>
          <div className="l">Model cost (review + Q&amp;A)</div>
        </div>
        <div className="kpi">
          <div className="v">
            {decided} / {findings}
          </div>
          <div className="l">Findings with a decision</div>
        </div>
      </div>
      <table className="grid">
        <thead>
          <tr>
            <th>Drawing</th>
            <th>Mode</th>
            <th>Findings</th>
            <th>Fails</th>
            <th>Review time</th>
            <th>Review cost</th>
            <th>Q&amp;A cost</th>
            <th>Model</th>
          </tr>
        </thead>
        <tbody>
          {done.map((s) => (
            <tr key={s.id} style={{ cursor: "default" }}>
              <td>{s.name}</td>
              <td>{s.cached ? "Cached" : "Live"}</td>
              <td>{s.findings?.length}</td>
              <td>{s.findings?.filter((f) => f.result === "fail").length}</td>
              <td>{secs(s.seconds)}</td>
              <td>{money(s.cost_usd)}</td>
              <td>{money(s.qa_cost_usd)}</td>
              <td className="mono">{s.model}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {done.length === 0 && <div className="empty">Reviews you open in this session appear here.</div>}
      <div className="pilotnote">
        <Info size={15} /> In the pilot this page keeps the history of every review across users, with cost and latency per model and the
        accept/reject rate per rule.
      </div>
    </div>
  );
}

const ROLES: [Role, string][] = [
  ["understand", "Understand the drawing (vision)"],
  ["review", "AI reviewers"],
  ["qa", "Q&A assistant"],
];

export function SettingsView() {
  const [m, setM] = useState<{ defaults: Record<string, string>; models: ModelInfo[] } | null>(null);
  const [choice, setChoice] = useState<ModelChoice>(modelChoice.get());
  useEffect(() => {
    api.models().then(setM).catch(() => setM({ defaults: {}, models: [] }));
  }, []);
  const update = (c: ModelChoice) => (setChoice(c), modelChoice.set(c));
  const custom = Object.keys(choice).length > 0;
  return (
    <div className="docview">
      <div className="pilotnote">
        <Info size={15} /> Choose the model and thinking level for each role. The choice is kept in this browser and applies to the
        drawings you upload and the questions you ask from now on; the demo drawings replay their saved review.
      </div>
      <div className="formgrid">
        <span className="h">Role</span>
        <span className="h">Model</span>
        <span className="h">Thinking</span>
        <span className="h">Price per million tokens (in / out)</span>
        {ROLES.map(([role, label]) => {
          const models = m?.models.filter((x) => x.roles.includes(role)) ?? [];
          const id = choice[role]?.model ?? m?.defaults[role];
          const model = models.find((x) => x.id === id);
          const thinking = choice[role]?.thinking ?? model?.thinking_default ?? "";
          const pick = (mid: string, t?: string) => {
            const next = models.find((x) => x.id === mid);
            if (!next) return;
            update({ ...choice, [role]: { model: mid, thinking: t ?? next.thinking_default } });
          };
          return (
            <Fragment key={role}>
              <span>{label}</span>
              <select value={model?.id ?? ""} onChange={(e) => pick(e.target.value)} aria-label={`${label} model`}>
                {models.map((x) => (
                  <option key={x.id} value={x.id} disabled={!x.available}>
                    {x.label} ({x.provider}){x.available ? "" : " — no API key on this server"}
                  </option>
                ))}
              </select>
              <select value={thinking} onChange={(e) => model && pick(model.id, e.target.value)} aria-label={`${label} thinking`}>
                {(model?.thinking ?? []).map((t) => (
                  <option key={t}>{t}</option>
                ))}
              </select>
              <span className="mono">{model ? `$${model.price_in} / $${model.price_out}` : "–"}</span>
            </Fragment>
          );
        })}
      </div>
      <div style={{ marginTop: 14, display: "flex", gap: 10, alignItems: "center" }}>
        <button className="btn" disabled={!custom} onClick={() => (setChoice({}), modelChoice.clear())}>
          Reset to the defaults
        </button>
        <span style={{ color: "var(--text-3)" }}>{custom ? "Using your choice." : "Using the server's defaults."}</span>
      </div>
    </div>
  );
}
