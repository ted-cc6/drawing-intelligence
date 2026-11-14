import { FileImage, FileSpreadsheet, Info, Send, Users, X } from "lucide-react";
import type { Finding, SessionInfo } from "../api";

/** The message to the designer: one numbered line per accepted finding (shared by the preview and Copy text). */
export function buildMessage(s: SessionInfo, accepted: Finding[]): { to: string; subject: string; body: string } {
  const tb = s.title_block ?? {};
  const to = tb.drawn_by ? `Designer ${tb.drawn_by} (drawn by, from the title block)` : "Designer (drawn by not read)";
  const n = accepted.length;
  const subject = `${tb.number ?? s.name} rev ${tb.revision ?? "?"} (${tb.title ?? s.name}): ${n} ${n === 1 ? "correction" : "corrections"} from the drawing check`;
  const lines = accepted.map(
    (f, i) => `${i + 1}. ${f.requirement}\n   Where: ${f.location}${f.recommended_correction ? `\n   Correction: ${f.recommended_correction}` : ""}`,
  );
  const body = ["Hello,", "", "The drawing check found these points to correct:", "", ...lines, "", "The checklist and the marked-up sheet are attached.", "", "Thanks"].join("\n");
  return { to, subject, body };
}

export function SendToDesignerDialog(p: {
  session: SessionInfo;
  accepted: Finding[];
  page: number;
  onDownload: (url: string) => void;
  onCopy: (text: string) => void;
  onSend: () => void;
  onClose: () => void;
}) {
  const m = buildMessage(p.session, p.accepted);
  const sid = p.session.id;
  return (
    <div className="overlay" style={{ position: "fixed", background: "rgba(20,30,40,0.25)", zIndex: 10 }} onClick={p.onClose}>
      <div className="dialog" style={{ width: 620 }} onClick={(e) => e.stopPropagation()}>
        <div className="dhead">
          <Users size={14} /> Send to designer
          <span style={{ flex: 1 }} />
          <button className="iconbtn" onClick={p.onClose}>
            <X size={13} />
          </button>
        </div>
        <div className="dbody para">
          <div className="mailhead">
            <span className="k">To</span>
            <span>{m.to}</span>
            <span className="k">Subject</span>
            <span>{m.subject}</span>
            <span className="k">Attached</span>
            <span>
              <button className="linkbtn" onClick={() => p.onDownload(`/api/sessions/${sid}/report.xlsx`)}>
                <FileSpreadsheet size={13} /> review_report.xlsx
              </button>{" "}
              <button className="linkbtn" onClick={() => p.onDownload(`/api/sessions/${sid}/annotated/${p.page}.png`)}>
                <FileImage size={13} /> annotated sheet (.png)
              </button>
            </span>
          </div>
          <pre className="mailbody">{m.body}</pre>
          <div className="pilotnote" style={{ margin: "10px 0" }}>
            <Info size={15} /> Demo: nothing is sent. In the pilot the address comes from the employee directory and the drawing's status becomes
            "Returned to designer".
          </div>
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
            <button className="btn" onClick={() => p.onCopy(`To: ${m.to}\nSubject: ${m.subject}\n\n${m.body}`)}>
              Copy text
            </button>
            <button className="btn primary" onClick={p.onSend}>
              <Send size={13} /> Send (demo)
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
