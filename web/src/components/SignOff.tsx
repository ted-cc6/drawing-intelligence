import { useState } from "react";
import { CheckCheck, Info, Users, X } from "lucide-react";
import type { Finding } from "../api";

/** The demo's sign-off state for one open review: kept in the browser only, never stored. */
export interface Stamp {
  kind: "checked" | "returned";
  by: string;
  date: string;
  accepted: number;
  rejected: number;
  open: number;
}

export const today = () => new Date().toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

export function counts(findings: Finding[]) {
  return {
    accepted: findings.filter((f) => f.feedback === "accept").length,
    rejected: findings.filter((f) => f.feedback === "reject").length,
    open: findings.filter((f) => !f.feedback).length,
  };
}

export function stampText(s: Stamp): string {
  return s.kind === "checked"
    ? `Checked by ${s.by} · ${s.date} · ${s.accepted} accepted, ${s.rejected} rejected, ${s.open} open`
    : `Returned to designer · ${s.date}`;
}

export function SignOffDialog(p: {
  findings: Finding[];
  onSign: (s: Stamp) => void;
  onNextOpen: () => void;
  onSend?: () => void;
  onClose: () => void;
}) {
  const [by, setBy] = useState("Demo checker");
  const c = counts(p.findings);
  const acceptedFails = p.findings.filter((f) => f.feedback === "accept" && f.result === "fail").length;
  const sign = () => p.onSign({ kind: "checked", by: by.trim() || "Demo checker", date: today(), ...c });
  return (
    <div className="overlay" style={{ position: "fixed", background: "rgba(20,30,40,0.25)", zIndex: 10 }} onClick={p.onClose}>
      <div className="dialog" style={{ width: 460 }} onClick={(e) => e.stopPropagation()}>
        <div className="dhead">
          <CheckCheck size={14} /> Mark as checked
          <span style={{ flex: 1 }} />
          <button className="iconbtn" onClick={p.onClose}>
            <X size={13} />
          </button>
        </div>
        <div className="dbody para">
          <label className="signrow">
            Checker <input value={by} onChange={(e) => setBy(e.target.value)} />
          </label>
          <p>
            <b>{c.accepted}</b> accepted · <b>{c.rejected}</b> rejected · <b>{c.open}</b> no decision yet
          </p>
          {c.open > 0 && (
            <p className="warnline">
              {c.open} {c.open === 1 ? "finding has" : "findings have"} no decision.{" "}
              <button className="btn" onClick={p.onNextOpen}>
                Next open finding
              </button>
            </p>
          )}
          {acceptedFails > 0 && p.onSend && (
            <p className="warnline">
              {acceptedFails} accepted {acceptedFails === 1 ? "fail" : "fails"}: send to the designer instead?{" "}
              <button className="btn" onClick={p.onSend}>
                <Users size={13} /> Send to designer
              </button>
            </p>
          )}
          <div className="pilotnote" style={{ margin: "10px 0" }}>
            <Info size={15} /> Demo: nothing is stored. In the pilot the sign-off is saved with the review and the drawing's status changes for
            everyone.
          </div>
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
            <button className="btn" onClick={p.onClose}>
              Cancel
            </button>
            <button className="btn primary" onClick={sign}>
              {c.open > 0 ? "Sign off anyway" : "Sign off"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
