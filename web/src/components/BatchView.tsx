import { useEffect, useState } from "react";
import { Download, FolderOpen, Info, Loader2 } from "lucide-react";
import type { BatchInfo, BatchRow } from "../api";
import { api } from "../api";
import { money, secs } from "../format";

const STATUS: Record<BatchRow["status"], string> = {
  queued: "Waiting",
  running: "Reviewing",
  done: "Done",
  error: "Failed",
  cancelled: "Stopped",
  rejected: "Not reviewed",
  closed: "Closed",
};

/** A batch review: one row per drawing, refreshed while any is still running. */
export function BatchView({
  id,
  onOpen,
  onDownload,
  onGone,
}: {
  id: string;
  onOpen: (sessionId: string) => void;
  onDownload: () => void;
  onGone: (message: string) => void;
}) {
  const [b, setB] = useState<BatchInfo | null>(null);
  useEffect(() => {
    let stop = false;
    let t: ReturnType<typeof setTimeout> | undefined;
    const load = () =>
      api
        .getBatch(id)
        .then((n) => {
          if (stop) return;
          setB(n);
          if (n.running > 0) t = setTimeout(load, 2000);
        })
        .catch((e) => !stop && onGone(e instanceof Error ? e.message : String(e)));
    load();
    return () => {
      stop = true;
      clearTimeout(t);
    };
  }, [id, onGone]);

  if (!b)
    return (
      <div className="docview empty">
        <Loader2 size={14} className="spin" /> Loading the batch…
      </div>
    );
  const reviewed = b.items.filter((i) => i.status !== "rejected").length;
  return (
    <div className="docview">
      <div className="kpis">
        <div className="kpi">
          <div className="v">
            {b.done} / {reviewed}
          </div>
          <div className="l">Drawings reviewed</div>
        </div>
        <div className="kpi">
          <div className="v">{b.items.reduce((a, i) => a + (i.fails ?? 0), 0)}</div>
          <div className="l">Fails found</div>
        </div>
        <div className="kpi">
          <div className="v">{money(b.cost_usd)}</div>
          <div className="l">Model cost</div>
        </div>
        <div className="kpi">
          <div className="v">{b.running > 0 ? <Loader2 size={18} className="spin" /> : "–"}</div>
          <div className="l">{b.running > 0 ? `${b.running} still running (two at a time)` : "All finished"}</div>
        </div>
      </div>
      <div className="toolbar">
        <button className="btn primary" onClick={onDownload} disabled={b.done === 0} title="summary.xlsx and each drawing's checklist">
          <Download size={13} /> Download all reports (.zip)
        </button>
        <span className="count">Closing this tab stops the batch and deletes its drawings.</span>
      </div>
      <table className="grid">
        <colgroup>
          <col style={{ width: 220 }} />
          <col />
          <col style={{ width: 80 }} />
          <col style={{ width: 60 }} />
          <col style={{ width: 80 }} />
          <col style={{ width: 100 }} />
          <col style={{ width: 80 }} />
          <col style={{ width: 90 }} />
        </colgroup>
        <thead>
          <tr>
            <th>Drawing</th>
            <th>Status</th>
            <th>Findings</th>
            <th>Fails</th>
            <th>Warnings</th>
            <th>Review time</th>
            <th>Cost</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {b.items.map((i, k) => (
            <tr key={k} style={{ cursor: "default" }}>
              <td>{i.name}</td>
              <td title={i.detail ?? undefined} style={{ whiteSpace: "normal" }}>
                {i.status === "running" || i.status === "queued" ? <Loader2 size={11} className="spin" /> : null} {STATUS[i.status]}
                {i.detail && i.status !== "done" ? <span style={{ color: "var(--text-3)" }}> — {i.detail}</span> : null}
              </td>
              <td>{i.findings ?? ""}</td>
              <td>{i.fails ?? ""}</td>
              <td>{i.warnings ?? ""}</td>
              <td>{i.seconds != null ? secs(i.seconds) : ""}</td>
              <td>{i.cost_usd != null ? money(i.cost_usd) : ""}</td>
              <td>
                {i.status === "done" && i.session_id && (
                  <button className="btn" onClick={() => onOpen(i.session_id!)}>
                    <FolderOpen size={12} /> Open
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="pilotnote">
        <Info size={15} /> Each drawing is screened first; a file that is not a PARI drawing is listed with the reason and costs nothing.
        Accepted drawings are reviewed live, two at a time.
      </div>
    </div>
  );
}
