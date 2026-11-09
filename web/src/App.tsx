import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BookOpen, Cpu, FileText, History, Home, Loader2, X } from "lucide-react";
import type { Cite, Demo, SessionInfo } from "./api";
import { ApiError, api, token, withToken } from "./api";
import { Login, StatusBar, TitleBar } from "./components/Chrome";
import { ReportsView, RulebookView, SettingsView, Welcome } from "./components/DocViews";
import { FindingsList } from "./components/FindingsList";
import { PathFinder } from "./components/PathFinder";
import { Ribbon, type Filters, type RibbonTab } from "./components/Ribbon";
import { RightDock, type ChatMsg, type DockTab } from "./components/RightDock";
import { SheetView, type SheetHandle } from "./components/SheetView";
import { isAI, money, scaleFactor, secs } from "./format";

type DocKind = "start" | "drawing" | "rules" | "reports" | "settings";
interface Doc {
  key: string;
  kind: DocKind;
  sid?: string;
}

const STATIC_DOCS: Record<Exclude<DocKind, "drawing">, { label: string; icon: JSX.Element }> = {
  start: { label: "Start", icon: <Home size={13} /> },
  rules: { label: "Rulebook", icon: <BookOpen size={13} /> },
  reports: { label: "Reports", icon: <History size={13} /> },
  settings: { label: "Options", icon: <Cpu size={13} /> },
};

export default function App() {
  const [auth, setAuth] = useState<"checking" | "login" | "ok">("checking");

  useEffect(() => {
    api
      .auth()
      .then((a) => setAuth(a.ok ? "ok" : "login"))
      .catch(() => setAuth("login"));
  }, []);

  if (auth === "checking")
    return (
      <div className="login">
        <Loader2 className="spin" />
      </div>
    );
  if (auth === "login") return <Login onDone={() => setAuth("ok")} />;
  return <Workbench onSignedOut={() => (token.clear(), setAuth("login"))} />;
}

function Workbench({ onSignedOut }: { onSignedOut: () => void }) {
  const [demos, setDemos] = useState<Demo[]>([]);
  const [sessions, setSessions] = useState<Record<string, SessionInfo>>({});
  const [docs, setDocs] = useState<Doc[]>([{ key: "start", kind: "start" }]);
  const [active, setActive] = useState("start");
  const [selected, setSelected] = useState<Record<string, number | null>>({});
  const [page, setPage] = useState<Record<string, number>>({});
  const [chats, setChats] = useState<Record<string, ChatMsg[]>>({});
  const [asking, setAsking] = useState<string | null>(null);
  const [filters, setFilters] = useState<Filters>({ fail: true, warning: true, code: true, ai: true });
  const [showMarkups, setShowMarkups] = useState(true);
  const [ribbonTab, setRibbonTab] = useState<RibbonTab>("home");
  const [dockTab, setDockTab] = useState<DockTab>("props");
  const [zoom, setZoom] = useState<number | undefined>();
  const [cursor, setCursor] = useState("");
  const [cite, setCite] = useState<{ page: number; bbox: [number, number, number, number] } | null>(null);
  const [prompt, setPrompt] = useState("Ready. Open a drawing from PathFinder or the Start page.");
  const [help, setHelp] = useState(false);
  const [measuring, setMeasuring] = useState(false);
  const [notice, setNotice] = useState<{ title: string; text: string } | null>(null);
  const sheetRef = useRef<SheetHandle>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const fail = useCallback(
    (e: unknown) => {
      if (e instanceof ApiError && e.status === 401) return onSignedOut();
      setPrompt(e instanceof Error ? e.message : String(e));
    },
    [onSignedOut],
  );

  useEffect(() => {
    api.demos().then(setDemos).catch(fail);
  }, [fail]);

  // Poll the sessions that are still running.
  const running = Object.values(sessions).filter((s) => s.status === "queued" || s.status === "running");
  useEffect(() => {
    if (running.length === 0) return;
    const t = setInterval(() => {
      for (const s of running)
        api
          .session(s.id)
          .then((n) => {
            setSessions((m) => ({ ...m, [n.id]: n }));
            if (n.status === "done") setPrompt(`Review of ${n.name} finished: ${n.findings?.length ?? 0} findings.`);
            if (n.status === "error") setPrompt(`Review of ${n.name} failed. ${n.error ?? ""}`);
          })
          .catch(fail);
    }, 700);
    return () => clearInterval(t);
  }, [running.map((s) => s.id).join(","), fail]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setMeasuring(false);
  }, [active]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && measuring) setMeasuring(false), setPrompt("Measure off.");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [measuring]);

  const doc = docs.find((d) => d.key === active) ?? docs[0];
  const sess = doc.kind === "drawing" && doc.sid ? sessions[doc.sid] ?? null : null;
  const openSessions = docs.filter((d) => d.kind === "drawing" && d.sid).map((d) => sessions[d.sid!]).filter(Boolean);

  const addSession = (s: SessionInfo) => {
    setSessions((m) => ({ ...m, [s.id]: s }));
    setDocs((ds) => [...ds, { key: s.id, kind: "drawing", sid: s.id }]);
    setActive(s.id);
    setPrompt(`Reviewing ${s.name}…`);
  };

  const openDemo = (id: string) => {
    const open = openSessions.find((s) => s.demo_id === id);
    if (open) return setActive(open.id);
    api.openDemo(id).then(addSession).catch(fail);
  };

  const openStatic = (kind: Exclude<DocKind, "drawing">) => {
    if (!docs.some((d) => d.key === kind)) setDocs((ds) => [...ds, { key: kind, kind }]);
    setActive(kind);
  };

  const onUploadFile = (f: File | undefined) => {
    if (!f) return;
    setPrompt(`Uploading ${f.name}…`);
    api
      .upload(f)
      .then(addSession)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) return onSignedOut();
        const text = e instanceof Error ? e.message : String(e);
        setPrompt(`${f.name} was not reviewed.`);
        setNotice({ title: `${f.name} was not reviewed`, text });
      });
  };

  const closeDoc = (key: string) => {
    const d = docs.find((x) => x.key === key);
    if (!d) return;
    if (d.kind === "drawing" && d.sid) {
      const s = sessions[d.sid];
      const wasRunning = s && (s.status === "queued" || s.status === "running");
      setPrompt(`Closed ${s?.name ?? "the drawing"}${wasRunning ? "; its review was stopped" : ""}. Its files were deleted.`);
      api.close(d.sid).catch(() => undefined);
      setSessions((m) => {
        const n = { ...m };
        delete n[d.sid!];
        return n;
      });
    }
    const rest = docs.filter((x) => x.key !== key);
    setDocs(rest.length ? rest : [{ key: "start", kind: "start" }]);
    if (active === key) setActive((rest[rest.length - 1] ?? { key: "start" }).key);
    setCite(null);
  };

  // Findings after the ribbon's Show filters.
  const allFindings = sess?.findings ?? [];
  const shown = useMemo(
    () =>
      allFindings.filter(
        (f) => (f.result === "fail" ? filters.fail : filters.warning) && (isAI(f) ? filters.ai : filters.code),
      ),
    [allFindings, filters],
  );
  const sel = sess ? selected[sess.id] ?? null : null;
  const finding = allFindings.find((f) => f.no === sel) ?? null;
  const sheets = sess?.sheets ?? [];
  const pageNo = sess ? page[sess.id] ?? sheets[0]?.page ?? 1 : 1;
  const sheet = sheets.find((s) => s.page === pageNo) ?? sheets[0];

  const select = (no: number | null) => {
    if (!sess) return;
    setSelected((m) => ({ ...m, [sess.id]: no }));
    setCite(null);
    if (no != null) {
      const f = allFindings.find((x) => x.no === no);
      const ev = f?.evidence.find((e) => e.bbox);
      if (ev && ev.page !== pageNo) setPage((m) => ({ ...m, [sess.id]: ev.page }));
      setDockTab("props");
      if (f) setPrompt(`#${f.no} ${f.result === "fail" ? "Fail" : "Warning"} · ${f.rule_id} · ${f.location}`);
    }
  };

  const feedback = (no: number, decision: "accept" | "reject") => {
    if (!sess) return;
    const patch = (d: "accept" | "reject" | null) =>
      setSessions((m) => {
        const s = m[sess.id];
        if (!s?.findings) return m;
        return { ...m, [sess.id]: { ...s, findings: s.findings.map((f) => (f.no === no ? { ...f, feedback: d } : f)) } };
      });
    const before = allFindings.find((f) => f.no === no)?.feedback ?? null;
    patch(decision);
    api
      .feedback(sess.id, no, decision)
      .then(() => setPrompt(`Finding ${no} ${decision === "accept" ? "accepted" : "rejected"}; logged for the rulebook owner.`))
      .catch((e) => (patch(before), fail(e)));
  };

  const ask = (q: string) => {
    if (!sess) return;
    const sid = sess.id;
    setChats((m) => ({ ...m, [sid]: [...(m[sid] ?? []), { q }] }));
    setAsking(sid);
    api
      .ask(sid, q)
      .then((a) => {
        setChats((m) => ({ ...m, [sid]: (m[sid] ?? []).map((x, i, arr) => (i === arr.length - 1 ? { ...x, a } : x)) }));
        setSessions((m) => (m[sid] ? { ...m, [sid]: { ...m[sid], qa_cost_usd: (m[sid].qa_cost_usd ?? 0) + a.cost_usd } } : m));
      })
      .catch((e) => {
        const msg = e instanceof Error ? e.message : String(e);
        setChats((m) => ({ ...m, [sid]: (m[sid] ?? []).map((x, i, arr) => (i === arr.length - 1 ? { ...x, error: msg } : x)) }));
        if (e instanceof ApiError && e.status === 401) onSignedOut();
      })
      .finally(() => setAsking(null));
  };

  const onCite = (c: Cite) => {
    if (c.finding_no != null) return select(c.finding_no);
    if (c.bbox && c.page != null && sess) {
      setPage((m) => ({ ...m, [sess.id]: c.page! }));
      setCite({ page: c.page, bbox: c.bbox });
      setPrompt(`${c.cite}: ${c.text ?? ""}`);
    }
  };

  const download = (url: string) => {
    const a = document.createElement("a");
    a.href = withToken(url);
    a.download = "";
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  const nextOpen = () => {
    const open = shown.filter((f) => !f.feedback);
    if (!open.length) return setPrompt("Every finding shown has a decision.");
    const i = open.findIndex((f) => f.no === sel);
    select(open[(i + 1) % open.length].no);
  };

  const acceptAllCodeFails = () => {
    for (const f of shown) if (!f.feedback && f.result === "fail" && !isAI(f)) feedback(f.no, "accept");
  };

  const demoQuestions = (sess?.demo_id ? demos.find((d) => d.id === sess.demo_id)?.questions : undefined) ?? [
    "What are the most serious problems on this drawing?",
    "Is this drawing ready to send to the shop?",
    "What is the material and the surface treatment?",
  ];

  const docLabel = (d: Doc) => (d.kind === "drawing" ? sessions[d.sid!]?.name ?? "Drawing" : STATIC_DOCS[d.kind].label);
  const done = sess?.status === "done";
  const nFail = allFindings.filter((f) => f.result === "fail").length;

  let center: JSX.Element;
  if (doc.kind === "start") center = <Welcome demos={demos} onOpenDemo={openDemo} onUpload={() => fileRef.current?.click()} />;
  else if (doc.kind === "rules") center = <RulebookView />;
  else if (doc.kind === "reports") center = <ReportsView sessions={Object.values(sessions)} />;
  else if (doc.kind === "settings") center = <SettingsView />;
  else if (!sess) center = <div className="graphics" />;
  else if (!done) center = <Progress s={sess} />;
  else
    center = (
      <>
        {sheet ? (
          <div style={{ position: "relative", flex: 1, display: "flex", minHeight: 0 }}>
            <SheetView
              ref={sheetRef}
              sheet={sheet}
              findings={shown}
              selected={sel}
              onSelect={select}
              showMarkups={showMarkups}
              cite={cite}
              onZoom={setZoom}
              onHover={setCursor}
              measure={measuring ? { factor: scaleFactor(sess.title_block?.scale), onResult: setPrompt } : null}
            />
            <div className="legend">
              <span>
                <i style={{ borderColor: "var(--fail)" }} />
                Fail
              </span>
              <span>
                <i style={{ borderColor: "var(--warn)" }} />
                Warning (confirm)
              </span>
              <span style={{ color: "var(--text-3)" }}>Scroll to zoom · drag to pan · click a box</span>
            </div>
          </div>
        ) : (
          <div className="graphics" />
        )}
        <div className="sheettabs">
          {sheets.map((s) => (
            <button key={s.page} className={`sheettab${s.page === pageNo ? " on" : ""}`} onClick={() => setPage((m) => ({ ...m, [sess.id]: s.page }))}>
              Sheet {s.page}
            </button>
          ))}
          <span className="grow" />
          <span className="hint">{sess.title_block?.sheet_size ? `${sess.title_block.sheet_size} · ${sess.title_block.scale ?? ""}` : ""}</span>
        </div>
      </>
    );

  return (
    <div className="app">
      <TitleBar doc={sess ? sess.name : doc.kind === "start" ? null : docLabel(doc)} onOpen={() => openStatic("start")} onHelp={() => setHelp(true)} />
      <Ribbon
        tab={ribbonTab}
        onTab={setRibbonTab}
        onFileMenu={() => openStatic("start")}
        hasDrawing={!!sess}
        reviewDone={!!done}
        filters={filters}
        onFilters={setFilters}
        showMarkups={showMarkups}
        onShowMarkups={setShowMarkups}
        onOpen={() => openStatic("start")}
        onUpload={() => fileRef.current?.click()}
        onFit={() => sheetRef.current?.fit()}
        onZoom={(f) => sheetRef.current?.zoomBy(f)}
        onExcel={() => sess && download(`/api/sessions/${sess.id}/report.xlsx`)}
        onAnnotated={() => sess && download(`/api/sessions/${sess.id}/annotated/${pageNo}.png`)}
        onClose={() => sess && closeDoc(sess.id)}
        onAsk={() => setDockTab("ask")}
        onProps={() => setDockTab("props")}
        onDoc={openStatic}
        onNextOpen={nextOpen}
        onAcceptAll={acceptAllCodeFails}
        measuring={measuring}
        onMeasure={() => {
          setMeasuring((m) => !m);
          setPrompt(measuring ? "Measure off." : "Measure: click the first point on the sheet (Esc to stop).");
        }}
      />
      <input ref={fileRef} type="file" accept="application/pdf,.pdf" hidden onChange={(e) => (onUploadFile(e.target.files?.[0]), (e.target.value = ""))} />
      <div className={`work${doc.kind === "drawing" ? "" : " nodoc"}`}>
        <PathFinder demos={demos} sessions={openSessions} active={sess} onOpenDemo={openDemo} onActivate={setActive} />
        <div className="center">
          <div className="doctabs">
            {docs.map((d) => (
              <button key={d.key} className={`doctab${d.key === active ? " on" : ""}`} onClick={() => setActive(d.key)} title={docLabel(d)}>
                {d.kind === "drawing" ? <FileText size={13} /> : STATIC_DOCS[d.kind].icon}
                <span className="nm">{docLabel(d)}</span>
                {!(d.kind === "start" && docs.length === 1) && (
                  <span
                    className="x"
                    onClick={(e) => {
                      e.stopPropagation();
                      closeDoc(d.key);
                    }}
                    title={d.kind === "drawing" ? "Close drawing (ends the session and deletes its files)" : "Close"}
                  >
                    <X size={11} />
                  </span>
                )}
              </button>
            ))}
          </div>
          {center}
        </div>
        <RightDock
          tab={dockTab}
          onTab={setDockTab}
          session={sess}
          finding={finding}
          onFeedback={feedback}
          chat={sess ? chats[sess.id] ?? [] : []}
          questions={demoQuestions}
          onAsk={ask}
          asking={asking != null && asking === sess?.id}
          onCite={onCite}
        />
        <FindingsList findings={shown} total={allFindings.length} selected={sel} onSelect={select} rejected={sess?.rejected ?? 0} />
      </div>
      <StatusBar
        prompt={prompt}
        sheet={done ? `Sheet ${pageNo} of ${sheets.length}` : undefined}
        cursor={done && doc.kind === "drawing" ? cursor : ""}
        zoom={done && doc.kind === "drawing" ? zoom : undefined}
        findings={done ? `${nFail} fail · ${allFindings.length - nFail} warning` : undefined}
        time={done ? `Review ${secs(sess!.seconds)}` : undefined}
        cost={done ? `Cost ${money((sess!.cost_usd ?? 0) + (sess!.qa_cost_usd ?? 0))}` : undefined}
        model={done ? sess!.model ?? undefined : undefined}
      />
      {help && <Help onClose={() => setHelp(false)} />}
      {notice && <Notice title={notice.title} text={notice.text} onClose={() => setNotice(null)} />}
    </div>
  );
}

function Progress({ s }: { s: SessionInfo }) {
  const doneN = s.stages.filter((x) => x.status === "done").length;
  return (
    <div className="graphics" style={{ cursor: "default" }}>
      <div className="overlay">
        <div className="dialog">
          <div className="dhead">
            {s.status === "error" ? null : <Loader2 size={14} className="spin" />} Reviewing {s.name}
          </div>
          <div className="dbody">
            <div className="muted">
              {s.live
                ? "Live review: the vision model reads the sheet and three AI reviewers check it. This takes about two minutes."
                : "Replaying the saved review of this demo drawing."}
            </div>
            <div className="progressbar">
              <span style={{ width: `${(100 * doneN) / s.stages.length}%` }} />
            </div>
            {s.stages.map((st) => (
              <div key={st.key} className="stage">
                <span className={`dot ${st.status}`} />
                <span className="lbl">{st.label}</span>
                <span className="t">{st.status !== "pending" ? secs(st.seconds) : ""}</span>
              </div>
            ))}
            {s.error && <div className="err" style={{ marginTop: 10 }}>{s.error}</div>}
          </div>
        </div>
      </div>
    </div>
  );
}

function Notice({ title, text, onClose }: { title: string; text: string; onClose: () => void }) {
  return (
    <div className="overlay" style={{ position: "fixed", background: "rgba(20,30,40,0.25)", zIndex: 10 }} onClick={onClose}>
      <div className="dialog" style={{ width: 440 }} onClick={(e) => e.stopPropagation()}>
        <div className="dhead">
          {title}
          <span style={{ flex: 1 }} />
          <button className="iconbtn" onClick={onClose}>
            <X size={13} />
          </button>
        </div>
        <div className="dbody para">
          <p style={{ marginTop: 0 }}>{text}</p>
          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <button className="btn primary" onClick={onClose}>
              OK
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Help({ onClose }: { onClose: () => void }) {
  return (
    <div className="overlay" style={{ position: "fixed", background: "rgba(20,30,40,0.25)", zIndex: 10 }} onClick={onClose}>
      <div className="dialog" style={{ width: 520 }} onClick={(e) => e.stopPropagation()}>
        <div className="dhead">
          How to use this demo
          <span style={{ flex: 1 }} />
          <button className="iconbtn" onClick={onClose}>
            <X size={13} />
          </button>
        </div>
        <div className="dbody para">
          <p style={{ marginTop: 0 }}>
            <b>1. Open a drawing</b> from PathFinder (left) or the Start page. The demo drawings open instantly; <b>Upload PDF</b> runs a live
            review of your own drawing.
          </p>
          <p>
            <b>2. Read the findings.</b> Each numbered box on the sheet is a finding: red boxes are fails from exact code checks, orange boxes
            are AI warnings to confirm. Click a box or a row in the Findings list to see the evidence, the rule and a plain-English explanation.
          </p>
          <p>
            <b>3. Decide.</b> Accept or reject each finding; decisions are logged for the rulebook owner.
          </p>
          <p>
            <b>4. Ask.</b> The Ask tab answers questions about the drawing. Click a reference in an answer to see it on the sheet.
          </p>
          <p style={{ marginBottom: 0 }}>
            <b>5. Export</b> the Excel checklist in PARI's columns, or the annotated sheet. Commands marked <span className="pilot" style={{ position: "static" }}>PILOT</span> are part of the pilot.
          </p>
        </div>
      </div>
    </div>
  );
}
