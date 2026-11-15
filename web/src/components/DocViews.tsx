import { Fragment, useEffect, useMemo, useState } from "react";
import { Download, FileText, FileUp, FlaskConical, Info, Loader2, Search } from "lucide-react";
import type { Demo, ModelChoice, ModelInfo, Role, Rule } from "../api";
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

/** Fetch on open and every 5 s while the page is open (other visitors keep adding rows). */
function usePoll<T>(load: () => Promise<T>): T | null {
  const [data, setData] = useState<T | null>(null);
  useEffect(() => {
    let live = true;
    const tick = () => {
      load()
        .then((d) => {
          if (live) setData(d);
        })
        .catch(() => undefined);
    };
    tick();
    const t = setInterval(tick, 5000);
    return () => {
      live = false;
      clearInterval(t);
    };
  }, [load]);
  return data;
}

const hhmm = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
const pct = (r: number | null) => (r == null ? "–" : `${Math.round(r * 100)}%`);

export function ReportsView() {
  const h = usePoll(api.history);
  if (!h) return <div className="docview"><div className="empty">Loading…</div></div>;
  const live = h.runs.filter((r) => !r.cached && r.status === "done");
  const cost = h.runs.reduce((a, r) => a + r.cost_usd + r.qa_cost_usd, 0);
  const avg = live.length ? live.reduce((a, r) => a + (r.seconds ?? 0), 0) / live.length : 0;
  return (
    <div className="docview">
      <div className="kpis">
        <div className="kpi">
          <div className="v">{h.runs.length}</div>
          <div className="l">Reviews since {hhmm(h.since)}</div>
        </div>
        <div className="kpi">
          <div className="v">{h.visitors}</div>
          <div className="l">Visitors</div>
        </div>
        <div className="kpi">
          <div className="v">{money(cost)}</div>
          <div className="l">Model cost (review + Q&amp;A)</div>
        </div>
        <div className="kpi">
          <div className="v">{live.length ? secs(avg) : "–"}</div>
          <div className="l">Average live review</div>
        </div>
      </div>
      <h3 className="cmph">Run history</h3>
      {h.runs.length === 0 ? (
        <div className="empty">No reviews yet. Open a demo drawing to start.</div>
      ) : (
        <table className="grid">
          <thead>
            <tr>
              <th>Time</th>
              <th>Visitor</th>
              <th>Drawing</th>
              <th>Mode</th>
              <th>Status</th>
              <th>Findings</th>
              <th>Fails</th>
              <th>Review time</th>
              <th>Review cost</th>
              <th>Q&amp;A cost</th>
              <th>Model</th>
            </tr>
          </thead>
          <tbody>
            {h.runs.map((r) => (
              <tr key={r.session_id} style={{ cursor: "default", fontWeight: r.you ? 600 : undefined }}>
                <td>{hhmm(r.at)}</td>
                <td>{r.you ? `${r.visitor} (you)` : r.visitor}</td>
                <td>{r.drawing}</td>
                <td>{r.mode}</td>
                <td>{r.status}</td>
                <td>{r.findings}</td>
                <td>{r.fails}</td>
                <td>{secs(r.seconds)}</td>
                <td>{money(r.cost_usd)}</td>
                <td>{money(r.qa_cost_usd)}</td>
                <td className="mono">{r.model ?? "default"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <h3 className="cmph">Cost and latency per model</h3>
      {h.models.length === 0 ? (
        <div className="empty">No reviews yet. Open a demo drawing to start.</div>
      ) : (
        <table className="grid">
          <thead>
            <tr>
              <th>Model</th>
              <th>Runs</th>
              <th>Live</th>
              <th>Average live review</th>
              <th>Average live cost</th>
              <th>Review cost</th>
              <th>Q&amp;A cost</th>
            </tr>
          </thead>
          <tbody>
            {h.models.map((m) => (
              <tr key={m.model ?? "default"} style={{ cursor: "default" }}>
                <td className="mono">{m.model ?? "default"}</td>
                <td>{m.runs}</td>
                <td>{m.live_runs}</td>
                <td>{m.avg_live_seconds == null ? "–" : secs(m.avg_live_seconds)}</td>
                <td>{m.avg_live_cost_usd == null ? "–" : money(m.avg_live_cost_usd)}</td>
                <td>{money(m.total_cost_usd)}</td>
                <td>{money(m.qa_cost_usd)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="pilotnote">
        <Info size={15} /> Demo: kept in the server's memory since it started ({hhmm(h.since)}); a restart clears it. Uploaded drawings are
        listed as "Uploaded PDF": nothing about an upload outlives its session. In the pilot this history is stored and covers every user by
        name.
      </div>
    </div>
  );
}

function RateBar({ rate }: { rate: number | null }) {
  return (
    <span className="ratebar" title={pct(rate)}>
      <i style={{ width: `${Math.round((rate ?? 0) * 100)}%` }} />
      <b>{pct(rate)}</b>
    </span>
  );
}

export function FeedbackView() {
  const s = usePoll(api.feedbackSummary);
  if (!s) return <div className="docview"><div className="empty">Loading…</div></div>;
  const code = s.by_source.filter((x) => x.source !== "llm");
  const ai = s.by_source.filter((x) => x.source === "llm");
  const rate = (xs: { decisions: number; accepted: number }[]) => {
    const d = xs.reduce((a, x) => a + x.decisions, 0);
    return d ? xs.reduce((a, x) => a + x.accepted, 0) / d : null;
  };
  return (
    <div className="docview">
      <div className="kpis">
        <div className="kpi">
          <div className="v">{s.decisions}</div>
          <div className="l">Decisions since {hhmm(s.since)}</div>
        </div>
        <div className="kpi">
          <div className="v">{pct(s.decisions ? s.accepted / s.decisions : null)}</div>
          <div className="l">Accepted</div>
        </div>
        <div className="kpi">
          <div className="v">{pct(rate(code))}</div>
          <div className="l">Code checks accepted</div>
        </div>
        <div className="kpi">
          <div className="v">{pct(rate(ai))}</div>
          <div className="l">AI reviewers accepted</div>
        </div>
      </div>
      {s.decisions === 0 ? (
        <div className="empty">No decisions yet. Accept or reject findings on a drawing.</div>
      ) : (
        <>
          <h3 className="cmph">By reviewer</h3>
          <table className="grid">
            <thead>
              <tr>
                <th>Reviewer</th>
                <th>Decisions</th>
                <th>Accepted</th>
                <th>Accept rate</th>
              </tr>
            </thead>
            <tbody>
              {s.by_reviewer.map((r) => (
                <tr key={r.reviewer} style={{ cursor: "default" }}>
                  <td className="mono">{r.reviewer}</td>
                  <td>{r.decisions}</td>
                  <td>{r.accepted}</td>
                  <td>
                    <RateBar rate={r.rate} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <h3 className="cmph">By rule (most rejected first)</h3>
          <table className="grid">
            <thead>
              <tr>
                <th>Rule</th>
                <th>Requirement</th>
                <th>Checked by</th>
                <th>Decisions</th>
                <th>Accepted</th>
                <th>Rejected</th>
                <th>Accept rate</th>
              </tr>
            </thead>
            <tbody>
              {s.by_rule.map((r) => (
                <tr key={r.rule_id} style={{ cursor: "default" }}>
                  <td className="mono">{r.rule_id}</td>
                  <td>{r.requirement}</td>
                  <td>{SOURCE_SHORT[r.source as keyof typeof SOURCE_SHORT] ?? r.source}</td>
                  <td>{r.decisions}</td>
                  <td>{r.accepted}</td>
                  <td>{r.rejected}</td>
                  <td>
                    <RateBar rate={r.rate} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      <div className="pilotnote">
        <Info size={15} /> Demo: decisions from the Accept/Reject buttons of every visitor since the server started; a restart clears them. In
        the pilot the rulebook owner reviews the most-rejected rules here.
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
