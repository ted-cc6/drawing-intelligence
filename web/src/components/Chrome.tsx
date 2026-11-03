import { useState } from "react";
import { CircleHelp, FolderOpen, Loader2, LogIn, RotateCcw, Save, Undo2, UserCircle2 } from "lucide-react";
import { api, token } from "../api";

export function TitleBar({ doc, onOpen, onHelp }: { doc: string | null; onOpen: () => void; onHelp: () => void }) {
  return (
    <div className="titlebar">
      <img className="appicon" src="/favicon.svg" alt="" />
      <div className="qat">
        <button title="Open drawing" onClick={onOpen}>
          <FolderOpen size={14} />
        </button>
        <button title="Save (not needed: nothing on the drawing is changed)" disabled>
          <Save size={14} />
        </button>
        <button title="Undo" disabled>
          <Undo2 size={14} />
        </button>
        <button title="Redo" disabled>
          <RotateCcw size={14} style={{ transform: "scaleX(-1)" }} />
        </button>
      </div>
      <div className="title">
        {doc ? <b>{doc}</b> : null}
        {doc ? " — " : ""}LatentView Drawing Intelligence for Wipro PARI
      </div>
      <img className="brand" src="/latentview_navy.png" alt="LatentView" />
      <span className="who">
        <UserCircle2 size={15} /> Checker
      </span>
      <button className="iconbtn" title="How to use this demo" onClick={onHelp}>
        <CircleHelp size={15} />
      </button>
    </div>
  );
}

export interface StatusInfo {
  prompt: string;
  sheet?: string;
  cursor?: string;
  zoom?: number;
  findings?: string;
  time?: string;
  cost?: string;
  model?: string;
}

export function StatusBar(s: StatusInfo) {
  return (
    <div className="statusbar">
      <span className="cell prompt">{s.prompt}</span>
      {s.sheet && <span className="cell">{s.sheet}</span>}
      <span className="cell" style={{ minWidth: 140 }}>
        {s.cursor || " "}
      </span>
      {s.zoom != null && <span className="cell">Zoom {Math.round(s.zoom * 100)}%</span>}
      {s.findings && <span className="cell">{s.findings}</span>}
      {s.time && <span className="cell">{s.time}</span>}
      {s.cost && <span className="cell">{s.cost}</span>}
      {s.model && <span className="cell mono">{s.model}</span>}
      <span className="cell">Rulebook v1 · 174 rules</span>
    </div>
  );
}

export function Login({ onDone }: { onDone: () => void }) {
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      token.set((await api.login(pw)).token);
      onDone();
    } catch {
      setErr("That password is not right.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="login">
      <div className="loginbox">
        <div className="band">
          <img src="/latentview_white.png" alt="LatentView" />
          <h1>Drawing Intelligence</h1>
          <p>AI first-pass review of 2D engineering drawings · for Wipro PARI</p>
        </div>
        <form onSubmit={submit}>
          <label htmlFor="pw">Demo password</label>
          <input id="pw" type="password" autoFocus value={pw} onChange={(e) => setPw(e.target.value)} />
          <div className="row">
            <span className="err">{err}</span>
            <button className="btn primary" disabled={busy || !pw}>
              {busy ? <Loader2 size={14} className="spin" /> : <LogIn size={14} />} Sign in
            </button>
          </div>
        </form>
        <div className="fine">
          UChicago MSADS capstone with LatentView Analytics. Drawings you upload are reviewed in a private session and deleted
          when you close them or after two idle hours.
        </div>
      </div>
    </div>
  );
}
