import { useEffect, useRef, useState, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Info, Loader2, Send, ThumbsDown, ThumbsUp } from "lucide-react";
import type { AnswerView, Cite, Finding, SessionInfo } from "../api";
import { REVIEWER_LABEL, SEVERITY_COLOR, SOURCE_LABEL, money } from "../format";

export type DockTab = "props" | "ask";

export interface ChatMsg {
  q: string;
  a?: AnswerView;
  error?: string;
}

interface Props {
  tab: DockTab;
  onTab: (t: DockTab) => void;
  session: SessionInfo | null;
  finding: Finding | null;
  onFeedback: (no: number, d: "accept" | "reject") => void;
  chat: ChatMsg[];
  questions: string[];
  onAsk: (q: string) => void;
  asking: boolean;
  onCite: (c: Cite) => void;
}

export function RightDock(p: Props) {
  return (
    <div className="pane right">
      <div className="pane-head tabs">
        <button className={`ptab${p.tab === "props" ? " on" : ""}`} onClick={() => p.onTab("props")}>
          Properties
        </button>
        <button className={`ptab${p.tab === "ask" ? " on" : ""}`} onClick={() => p.onTab("ask")}>
          Ask about this drawing
        </button>
      </div>
      <div className="pane-body" style={p.tab === "ask" ? { overflow: "hidden" } : undefined}>
        {p.tab === "props" ? <Properties {...p} /> : <Ask {...p} />}
      </div>
    </div>
  );
}

function Properties({ session, finding, onFeedback }: Props) {
  if (!session || session.status !== "done") {
    return <div className="empty">Open a drawing to see its findings here.</div>;
  }
  if (!finding) {
    const n = session.findings?.length ?? 0;
    const fails = session.findings?.filter((f) => f.result === "fail").length ?? 0;
    return (
      <>
        <div className="section">
          <h4>Review summary</h4>
          <div className="kv">
            <span className="k">Drawing</span>
            <span className="v mono">{session.title_block?.number ?? session.name}</span>
            <span className="k">Findings</span>
            <span className="v">
              {fails} fail · {n - fails} warning
            </span>
            <span className="k">Rules applied</span>
            <span className="v">{session.rules_total}</span>
            <span className="k">Reviewers</span>
            <span className="v">{session.reviewers_run?.map((r) => REVIEWER_LABEL[r] ?? r).join(", ")}</span>
            <span className="k">Review time</span>
            <span className="v">{session.seconds} s</span>
            <span className="k">Cost</span>
            <span className="v">
              {money(session.cost_usd)} {session.cached ? "(replayed from cache)" : ""}
            </span>
            <span className="k">Rulebook</span>
            <span className="v mono">{session.rulebook_version}</span>
          </div>
        </div>
        <div className="section">
          <div className="explain">
            Select a numbered box on the sheet or a row in the Findings list. Fails come from exact code checks against
            PARI's rules; warnings come from the AI reviewers and need an engineer to confirm them.
          </div>
        </div>
      </>
    );
  }
  const f = finding;
  return (
    <>
      <div className="section">
        <div className="fhead">
          <span className={`fno ${f.result}`}>{f.no}</span>
          <div>
            <div className="ftitle">{f.requirement}</div>
            <div style={{ color: "var(--text-2)" }}>
              {f.result === "fail" ? "Fail" : "Warning — confirm"} · <span style={{ color: SEVERITY_COLOR[f.severity], textTransform: "capitalize" }}>{f.severity}</span> · {f.category_label}
            </div>
          </div>
        </div>
      </div>
      {f.plain_english && (
        <div className="section">
          <h4>In plain English</h4>
          <div className="explain">{f.plain_english}</div>
        </div>
      )}
      <div className="section">
        <h4>Finding</h4>
        <div className="para">{f.comment}</div>
        {f.recommended_correction && (
          <>
            <h4 style={{ marginTop: 10 }}>Recommended correction</h4>
            <div className="para">{f.recommended_correction}</div>
          </>
        )}
      </div>
      <div className="section">
        <h4>Evidence on the drawing</h4>
        {f.evidence.map((e, i) => (
          <div key={i} className="kv" style={{ marginBottom: 4 }}>
            <span className="k">
              Sheet {e.page}
              {e.zone ? `, zone ${e.zone}` : ""}
            </span>
            <span className="v">
              {e.quote ? <span className="quote">{e.quote}</span> : <span style={{ color: "var(--text-3)" }}>{e.ref ?? "marked area"}</span>}
            </span>
          </div>
        ))}
      </div>
      <div className="section">
        <h4>Rule</h4>
        <div className="kv">
          <span className="k">Rule</span>
          <span className="v mono">{f.rule_id}</span>
          <span className="k">Checked by</span>
          <span className="v">
            {SOURCE_LABEL[f.source]}
            {f.source === "llm" ? " (warning only)" : ""}
          </span>
          {f.rule_source && (
            <>
              <span className="k">Source</span>
              <span className="v">{f.rule_source}</span>
            </>
          )}
        </div>
      </div>
      <div className="section">
        <h4>Your decision</h4>
        <div className="fbbar">
          <button className={`btn${f.feedback === "accept" ? " accepted" : ""}`} onClick={() => onFeedback(f.no, "accept")}>
            <ThumbsUp size={14} /> {f.feedback === "accept" ? "Accepted" : "Accept"}
          </button>
          <button className={`btn${f.feedback === "reject" ? " rejected" : ""}`} onClick={() => onFeedback(f.no, "reject")}>
            <ThumbsDown size={14} /> {f.feedback === "reject" ? "Rejected" : "Reject"}
          </button>
        </div>
        <div style={{ color: "var(--text-3)", marginTop: 6, fontSize: 11 }}>Decisions are logged so the rulebook owner can see which rules help.</div>
      </div>
    </>
  );
}

function renderAnswer(text: string, cites: Cite[], onCite: (c: Cite) => void): ReactNode[] {
  const byKey = new Map(cites.map((c) => [c.cite, c]));
  const out: ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(/\[([^[\]\n]{1,80})\]/g)) {
    out.push(text.slice(last, m.index));
    const c = byKey.get(m[1].trim());
    out.push(
      c && (c.finding_no != null || c.bbox) ? (
        <button key={m.index} className="cite" onClick={() => onCite(c)} title={c.text ?? `Finding ${c.finding_no}`}>
          {m[1]}
        </button>
      ) : (
        <span key={m.index} className="mono" style={{ color: "var(--text-3)" }}>
          [{m[1]}]
        </span>
      ),
    );
    last = (m.index ?? 0) + m[0].length;
  }
  out.push(text.slice(last));
  return out;
}

function Ask({ session, chat, questions, onAsk, asking, onCite }: Props) {
  const [q, setQ] = useState("");
  const end = useRef<HTMLDivElement>(null);
  // Braces matter: newer browsers return a Promise from scrollIntoView, and React would call it as a cleanup.
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth" });
  }, [chat.length, asking]);
  if (!session || session.status !== "done") return <div className="empty">Open a drawing to ask questions about it.</div>;
  const send = (text: string) => {
    if (!text.trim() || asking) return;
    onAsk(text.trim());
    setQ("");
  };
  return (
    <div className="chat">
      <div className="msgs">
        {chat.length === 0 && (
          <div className="explain">
            Ask anything about this drawing, its findings or the standards. Every answer cites what it uses — click a
            reference to see it on the sheet — and is checked against the saved data before it is shown.
          </div>
        )}
        {chat.map((m, i) => (
          <div key={i} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <div className="msg q">{m.q}</div>
            {m.a && (
              <div className="msg a">
                <div style={{ whiteSpace: "pre-wrap" }}>{renderAnswer(m.a.text, m.a.cites, onCite)}</div>
                <div className="foot">
                  {m.a.verified ? (
                    <span className="ver ok">
                      <CheckCircle2 size={12} /> Verified against the drawing
                    </span>
                  ) : (
                    <span className="ver no" title={m.a.problems.join("; ")}>
                      <AlertTriangle size={12} /> Not verified
                    </span>
                  )}
                  <span>{money(m.a.cost_usd)}</span>
                </div>
              </div>
            )}
            {m.error && (
              <div className="msg a err">
                <Info size={12} /> {m.error}
              </div>
            )}
          </div>
        ))}
        {asking && (
          <div className="msg a typing">
            <Loader2 size={12} className="spin" /> Looking it up in the drawing…
          </div>
        )}
        <div ref={end} />
      </div>
      <div className="suggest">
        {questions.map((s) => (
          <button key={s} onClick={() => send(s)} disabled={asking}>
            {s}
          </button>
        ))}
      </div>
      <div className="ask">
        <textarea
          value={q}
          placeholder="Type a question, e.g. What fit is on the ⌀50 bore?"
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(q);
            }
          }}
        />
        <button className="btn primary" onClick={() => send(q)} disabled={asking || !q.trim()} title="Ask (Enter)">
          <Send size={14} />
        </button>
      </div>
    </div>
  );
}
