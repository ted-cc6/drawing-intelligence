import { forwardRef, useCallback, useEffect, useImperativeHandle, useLayoutEffect, useRef, useState } from "react";
import type { Finding, Sheet } from "../api";
import { withToken } from "../api";

export interface SheetHandle {
  fit: () => void;
  zoomBy: (factor: number) => void;
}

interface Props {
  sheet: Sheet;
  findings: Finding[]; // already filtered
  selected: number | null;
  onSelect: (no: number | null) => void;
  showMarkups: boolean;
  cite: { page: number; bbox: [number, number, number, number] } | null;
  onZoom: (z: number) => void;
  onHover: (text: string) => void;
}

interface View {
  s: number;
  x: number;
  y: number;
  animate: boolean;
}

const PAD = 7;
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/** The drawing sheet in a pan/zoom graphics window, with each finding boxed and numbered on top. */
export const SheetView = forwardRef<SheetHandle, Props>(function SheetView(
  { sheet, findings, selected, onSelect, showMarkups, cite, onZoom, onHover },
  ref,
) {
  const box = useRef<HTMLDivElement>(null);
  const [view, setView] = useState<View>({ s: 0.3, x: 0, y: 0, animate: false });
  const [drag, setDrag] = useState<{ x: number; y: number; vx: number; vy: number; moved: boolean } | null>(null);
  const fitScale = useRef(0.3);

  const fit = useCallback(() => {
    const el = box.current;
    if (!el) return;
    const s = Math.min(el.clientWidth / sheet.w, el.clientHeight / sheet.h) * 0.95;
    fitScale.current = s;
    setView({ s, x: (el.clientWidth - sheet.w * s) / 2, y: (el.clientHeight - sheet.h * s) / 2, animate: true });
  }, [sheet.w, sheet.h]);

  const zoomAt = useCallback((factor: number, cx?: number, cy?: number, animate = false) => {
    const el = box.current;
    if (!el) return;
    setView((v) => {
      const s = clamp(v.s * factor, fitScale.current * 0.5, 4);
      const px = cx ?? el.clientWidth / 2;
      const py = cy ?? el.clientHeight / 2;
      return { s, x: px - ((px - v.x) * s) / v.s, y: py - ((py - v.y) * s) / v.s, animate };
    });
  }, []);

  useImperativeHandle(ref, () => ({ fit, zoomBy: (f) => zoomAt(f, undefined, undefined, true) }), [fit, zoomAt]);

  useLayoutEffect(() => {
    fit();
  }, [fit, sheet.url]);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    let last = `${el.clientWidth}x${el.clientHeight}`;
    const ro = new ResizeObserver(() => {
      const now = `${el.clientWidth}x${el.clientHeight}`;
      if (now !== last) fit(); // only a real change of the window's size refits the sheet
      last = now;
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [fit]);

  useEffect(() => onZoom(view.s), [view.s, onZoom]);

  // Bring a box into view: the selected finding's first box on this sheet, or a cited item.
  const focus = useCallback(
    (b: [number, number, number, number]) => {
      const el = box.current;
      if (!el) return;
      const [x0, y0, x1, y1] = b;
      const w = Math.max(x1 - x0, 40) + 900; // keep the surroundings in view, like a zoom-to-selection
      const h = Math.max(y1 - y0, 40) + 640;
      const s = clamp(Math.min(el.clientWidth / w, el.clientHeight / h), fitScale.current, 0.85);
      const cx = (x0 + x1) / 2;
      const cy = (y0 + y1) / 2;
      setView({ s, x: el.clientWidth / 2 - cx * s, y: el.clientHeight / 2 - cy * s, animate: true });
    },
    [],
  );

  useEffect(() => {
    if (selected == null) return;
    const f = findings.find((x) => x.no === selected);
    const ev = f?.evidence.find((e) => e.page === sheet.page && e.bbox);
    if (ev?.bbox) focus(ev.bbox);
  }, [selected, sheet.page, findings, focus]);

  useEffect(() => {
    if (cite && cite.page === sheet.page) focus(cite.bbox);
  }, [cite, sheet.page, focus]);

  const onWheel = (e: React.WheelEvent) => {
    const r = box.current!.getBoundingClientRect();
    zoomAt(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX - r.left, e.clientY - r.top);
  };

  const onDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    (e.target as Element).setPointerCapture?.(e.pointerId);
    setDrag({ x: e.clientX, y: e.clientY, vx: view.x, vy: view.y, moved: false });
  };
  const onMove = (e: React.PointerEvent) => {
    if (drag) {
      const dx = e.clientX - drag.x;
      const dy = e.clientY - drag.y;
      if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
      setView((v) => ({ ...v, x: drag.vx + dx, y: drag.vy + dy, animate: false }));
    }
    const r = box.current!.getBoundingClientRect();
    const sx = (e.clientX - r.left - view.x) / view.s;
    const sy = (e.clientY - r.top - view.y) / view.s;
    onHover(sx >= 0 && sy >= 0 && sx <= sheet.w && sy <= sheet.h ? `X ${Math.round(sx)}  Y ${Math.round(sy)} px` : "");
  };
  const onUp = (e: React.PointerEvent) => {
    const wasClick = drag && !drag.moved;
    setDrag(null);
    if (wasClick && (e.target as Element).closest?.(".mk") == null) onSelect(null);
  };

  const marks = showMarkups
    ? findings.flatMap((f) =>
        f.evidence
          .map((e, i) => ({ e, i }))
          .filter(({ e }) => e.page === sheet.page && e.bbox)
          .map(({ e, i }) => ({ f, bbox: e.bbox!, first: i === f.evidence.findIndex((x) => x.page === sheet.page && x.bbox) })),
      )
    : [];

  return (
    <div
      ref={box}
      className={`graphics${drag?.moved ? " dragging" : ""}`}
      onWheel={onWheel}
      onPointerDown={onDown}
      onPointerMove={onMove}
      onPointerUp={onUp}
      onPointerLeave={() => onHover("")}
    >
      <div
        className="sheetwrap"
        style={{
          transform: `translate(${view.x}px, ${view.y}px) scale(${view.s})`,
          transition: view.animate ? "transform 0.28s ease-out" : "none",
        }}
      >
        <img src={withToken(sheet.url)} width={sheet.w} height={sheet.h} alt={`Sheet ${sheet.page}`} draggable={false} />
        <svg width={sheet.w} height={sheet.h} viewBox={`0 0 ${sheet.w} ${sheet.h}`}>
          {marks.map(({ f, bbox, first }, k) => {
            const [x0, y0, x1, y1] = bbox;
            const label = String(f.no);
            const tw = 14 + 12 * label.length;
            const cls = `mk ${f.result}${selected === f.no ? " sel" : ""}${selected != null && selected !== f.no ? " dim" : ""}`;
            return (
              <g
                key={`${f.no}-${k}`}
                className={cls}
                onPointerDown={(e) => e.stopPropagation()}
                onClick={() => onSelect(f.no)}
              >
                <title>{`#${f.no} ${f.result === "fail" ? "Fail" : "Warning"} · ${f.rule_id ?? ""} · ${f.requirement}`}</title>
                <rect className="box" x={x0 - PAD} y={y0 - PAD} width={x1 - x0 + 2 * PAD} height={y1 - y0 + 2 * PAD} rx={2} />
                {first && (
                  <>
                    <rect className="tag" x={x0 - PAD} y={Math.max(0, y0 - PAD - 30)} width={tw} height={28} rx={2} />
                    <text x={x0 - PAD + tw / 2} y={Math.max(0, y0 - PAD - 30) + 21} fontSize={20} textAnchor="middle">
                      {label}
                    </text>
                  </>
                )}
              </g>
            );
          })}
          {cite && cite.page === sheet.page && (
            <rect
              className="citebox"
              x={cite.bbox[0] - 10}
              y={cite.bbox[1] - 10}
              width={cite.bbox[2] - cite.bbox[0] + 20}
              height={cite.bbox[3] - cite.bbox[1] + 20}
            />
          )}
        </svg>
      </div>
    </div>
  );
});
