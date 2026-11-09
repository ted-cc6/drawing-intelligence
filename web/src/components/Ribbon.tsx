import type { ReactNode } from "react";
import {
  BarChart3,
  BookOpen,
  Bot,
  CheckCheck,
  Cpu,
  Download,
  Eye,
  FileImage,
  FileSpreadsheet,
  FileUp,
  FolderOpen,
  GitCompare,
  Gauge,
  History,
  Layers,
  ListChecks,
  Maximize,
  MessageSquareText,
  PlayCircle,
  Ruler,
  ScanSearch,
  Settings2,
  ShieldCheck,
  SquareX,
  ThumbsUp,
  Users,
  ZoomIn,
  ZoomOut,
} from "lucide-react";

export type RibbonTab = "home" | "review" | "rules" | "reports" | "tools";

export interface Filters {
  fail: boolean;
  warning: boolean;
  code: boolean;
  ai: boolean;
}

interface Props {
  tab: RibbonTab;
  onTab: (t: RibbonTab) => void;
  onFileMenu: () => void;
  hasDrawing: boolean;
  reviewDone: boolean;
  filters: Filters;
  onFilters: (f: Filters) => void;
  showMarkups: boolean;
  onShowMarkups: (v: boolean) => void;
  onOpen: () => void;
  onUpload: () => void;
  onFit: () => void;
  onZoom: (f: number) => void;
  onExcel: () => void;
  onAnnotated: () => void;
  onClose: () => void;
  onAsk: () => void;
  onProps: () => void;
  onDoc: (kind: "rules" | "reports" | "settings") => void;
  onNextOpen: () => void;
  onAcceptAll: () => void;
  measuring: boolean;
  onMeasure: () => void;
  onRulebookExcel: () => void;
}

function Big(p: { icon: ReactNode; label: string; onClick?: () => void; disabled?: boolean; on?: boolean; pilot?: boolean; tip?: string }) {
  return (
    <button className={`big${p.on ? " on" : ""}`} onClick={p.onClick} disabled={p.disabled || p.pilot} title={p.tip ?? (p.pilot ? `${p.label} — coming in the pilot` : p.label)}>
      {p.icon}
      <span>{p.label}</span>
      {p.pilot && <span className="pilot">PILOT</span>}
    </button>
  );
}

function Small(p: { icon: ReactNode; label: string; onClick?: () => void; disabled?: boolean; on?: boolean; pilot?: boolean; tip?: string }) {
  return (
    <button className={`small${p.on ? " on" : ""}`} onClick={p.onClick} disabled={p.disabled || p.pilot} title={p.tip ?? (p.pilot ? `${p.label} — coming in the pilot` : p.label)}>
      {p.icon}
      <span>{p.label}</span>
      {p.pilot && <span className="pilot">PILOT</span>}
    </button>
  );
}

function Group({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="rgroup">
      <div className="cmds">{children}</div>
      <div className="glabel">{label}</div>
    </div>
  );
}

const TABS: [RibbonTab, string][] = [
  ["home", "Home"],
  ["review", "Review"],
  ["rules", "Rulebook"],
  ["reports", "Reports"],
  ["tools", "Tools"],
];

export function Ribbon(p: Props) {
  const d = !p.reviewDone;
  const f = p.filters;
  const toggle = (k: keyof Filters) => p.onFilters({ ...f, [k]: !f[k] });
  const sw = (c: string) => <span className="swatch" style={{ background: c }} />;

  const home = (
    <>
      <Group label="Drawing">
        <Big icon={<FolderOpen size={24} />} label="Open drawing" onClick={p.onOpen} tip="Open one of the demo drawings" />
        <Big icon={<FileUp size={24} />} label="Upload PDF" onClick={p.onUpload} tip="Review your own PDF drawing (live AI calls, about 2 minutes)" />
        <div className="rcol">
          <Small icon={<SquareX size={15} />} label="Close drawing" onClick={p.onClose} disabled={!p.hasDrawing} tip="End this session and delete its files" />
        </div>
      </Group>
      <Group label="Review">
        <Big icon={<PlayCircle size={24} />} label="Run review" onClick={p.onUpload} tip="Upload a PDF to run a new review" />
        <div className="rcol">
          <Small icon={<GitCompare size={15} />} label="Compare revisions" pilot />
          <Small icon={<Layers size={15} />} label="Batch review" pilot />
        </div>
      </Group>
      <Group label="Show">
        <div className="rcol">
          <Small icon={sw("#d13438")} label="Fails" on={f.fail} onClick={() => toggle("fail")} disabled={d} />
          <Small icon={sw("#e39400")} label="Warnings" on={f.warning} onClick={() => toggle("warning")} disabled={d} />
          <Small icon={<Eye size={15} />} label="Markups" on={p.showMarkups} onClick={() => p.onShowMarkups(!p.showMarkups)} disabled={d} />
        </div>
        <div className="rcol">
          <Small icon={<Cpu size={15} />} label="Code checks" on={f.code} onClick={() => toggle("code")} disabled={d} tip="Findings from deterministic code checks and table lookups" />
          <Small icon={<Bot size={15} />} label="AI reviewers" on={f.ai} onClick={() => toggle("ai")} disabled={d} tip="Warnings from the AI reviewers, to confirm" />
        </div>
      </Group>
      <Group label="View">
        <Big icon={<Maximize size={22} />} label="Fit sheet" onClick={p.onFit} disabled={d} />
        <div className="rcol">
          <Small icon={<ZoomIn size={15} />} label="Zoom in" onClick={() => p.onZoom(1.25)} disabled={d} />
          <Small icon={<ZoomOut size={15} />} label="Zoom out" onClick={() => p.onZoom(0.8)} disabled={d} />
        </div>
      </Group>
      <Group label="Inspect">
        <Big icon={<ListChecks size={22} />} label="Properties" onClick={p.onProps} disabled={d} />
        <Big icon={<MessageSquareText size={22} />} label="Ask about drawing" onClick={p.onAsk} disabled={d} />
      </Group>
      <Group label="Output">
        <Big icon={<FileSpreadsheet size={24} />} label="Excel checklist" onClick={p.onExcel} disabled={d} tip="The review in PARI's checklist columns (.xlsx)" />
        <Big icon={<FileImage size={24} />} label="Annotated sheet" onClick={p.onAnnotated} disabled={d} tip="The sheet with numbered boxes (.png)" />
      </Group>
    </>
  );

  const review = (
    <>
      <Group label="Findings">
        <Big icon={<ScanSearch size={22} />} label="Next open finding" onClick={p.onNextOpen} disabled={d} tip="Select the next finding without a decision" />
        <Big icon={<ThumbsUp size={22} />} label="Accept all code fails" onClick={p.onAcceptAll} disabled={d} tip="Accept every code-check fail still open" />
      </Group>
      <Group label="Sign-off">
        <Big icon={<CheckCheck size={22} />} label="Mark as checked" pilot />
        <Big icon={<Users size={22} />} label="Send to designer" pilot />
      </Group>
      <Group label="Measure">
        <Big icon={<Ruler size={22} />} label="Measure" on={p.measuring} onClick={p.onMeasure} disabled={d} tip="Click two points on the sheet to measure between them (Esc to stop)" />
      </Group>
    </>
  );

  const rules = (
    <>
      <Group label="Rulebook">
        <Big icon={<BookOpen size={24} />} label="Browse rules" onClick={() => p.onDoc("rules")} tip="All rules, with where each comes from and how it is checked" />
        <div className="rcol">
          <Small icon={<Download size={15} />} label="Rulebook (.xlsx)" onClick={p.onRulebookExcel} tip="All 174 rules, their sources and whether a check runs today" />
          <Small icon={<ShieldCheck size={15} />} label="Confirm rules" pilot />
        </div>
      </Group>
      <Group label="Edit">
        <Big icon={<Settings2 size={22} />} label="Edit rule" pilot />
      </Group>
    </>
  );

  const reports = (
    <>
      <Group label="History">
        <Big icon={<History size={24} />} label="Run history" onClick={() => p.onDoc("reports")} />
        <Big icon={<BarChart3 size={24} />} label="Cost & latency" onClick={() => p.onDoc("reports")} />
      </Group>
      <Group label="Quality">
        <Big icon={<Gauge size={22} />} label="Feedback analytics" pilot />
      </Group>
    </>
  );

  const tools = (
    <>
      <Group label="Models">
        <Big icon={<Cpu size={24} />} label="Model per role" onClick={() => p.onDoc("settings")} />
      </Group>
      <Group label="Options">
        <Big icon={<Settings2 size={22} />} label="Options" onClick={() => p.onDoc("settings")} />
      </Group>
    </>
  );

  return (
    <>
      <div className="tabstrip">
        <button className="apptab" onClick={p.onFileMenu} title="Open a drawing">
          File
        </button>
        {TABS.map(([k, l]) => (
          <button key={k} className={`tab${p.tab === k ? " on" : ""}`} onClick={() => p.onTab(k)}>
            {l}
          </button>
        ))}
        <span className="spacer" />
      </div>
      <div className="ribbon">{{ home, review, rules, reports, tools }[p.tab]}</div>
    </>
  );
}
