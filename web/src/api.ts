// Typed calls to the FastAPI back end (src/drawing_intelligence/api). The shapes mirror api/views.py.

export type Result = "fail" | "warning";
export type Severity = "critical" | "major" | "minor" | "info";
export type Source = "code" | "lookup" | "llm";

export interface Demo {
  id: string;
  title: string;
  subtitle: string;
  kind: "real" | "seeded" | "clean";
  note: string;
  questions: string[];
}

export interface Stage {
  key: string;
  label: string;
  status: "pending" | "running" | "done" | "skipped" | "error";
  seconds: number | null;
}

export interface Evidence {
  page: number;
  ref: string | null;
  quote: string | null;
  kind: string;
  bbox: [number, number, number, number] | null; // sheet-image pixels
  zone: string | null;
}

export interface Finding {
  no: number;
  id: string;
  rule_id: string | null;
  requirement: string;
  rule_source: string | null;
  category: string;
  category_label: string;
  result: Result;
  severity: Severity;
  source: Source;
  reviewer: string;
  comment: string;
  recommended_correction: string | null;
  location: string;
  evidence: Evidence[];
  plain_english: string | null;
  feedback: "accept" | "reject" | null;
}

export interface Sheet {
  page: number;
  url: string;
  w: number;
  h: number;
}

export interface SessionInfo {
  id: string;
  name: string;
  demo_id: string | null;
  live: boolean;
  status: "queued" | "running" | "done" | "error";
  error: string | null;
  stages: Stage[];
  seconds: number | null;
  // present once the review is done
  title_block?: Record<string, string>;
  sheets?: Sheet[];
  findings?: Finding[];
  rejected?: number;
  coverage?: Record<"fail" | "warning" | "pass" | "not_checked" | "not_applicable", number>;
  rules_total?: number;
  reviewers_run?: string[];
  cost_usd?: number;
  qa_cost_usd?: number;
  cached?: boolean;
  model?: string | null;
  rulebook_version?: string;
}

export interface Cite {
  cite: string;
  finding_no?: number;
  page?: number;
  bbox?: [number, number, number, number] | null;
  text?: string;
}

export interface AnswerView {
  text: string;
  verified: boolean;
  problems: string[];
  cost_usd: number;
  stopped_by: string | null;
  cites: Cite[];
}

export interface Rule {
  id: string;
  category: string;
  category_label: string;
  requirement: string;
  severity: Severity;
  check_type: Source;
  built: boolean;
  status: string;
  source: string;
}

export interface ModelInfo {
  id: string;
  label: string;
  provider: string;
  roles: string[];
  thinking: string[];
  thinking_default: string;
  price_in: number;
  price_out: number;
}

const TOKEN_KEY = "di-demo-token";
export const token = {
  get: () => sessionStorage.getItem(TOKEN_KEY) ?? "",
  set: (t: string) => sessionStorage.setItem(TOKEN_KEY, t),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
};

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (token.get()) headers.set("X-Demo-Token", token.get());
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const r = await fetch(path, { ...init, headers });
  if (!r.ok) {
    let detail = r.statusText;
    try {
      detail = (await r.json()).detail ?? detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(r.status, String(detail));
  }
  return r.json() as Promise<T>;
}

/** A URL for <img> and downloads, which cannot send the token header. */
export const withToken = (url: string) => (token.get() ? `${url}${url.includes("?") ? "&" : "?"}t=${token.get()}` : url);

export const api = {
  auth: () => call<{ required: boolean; ok: boolean }>("/api/auth"),
  login: (password: string) => call<{ token: string }>("/api/auth/login", { method: "POST", body: JSON.stringify({ password }) }),
  demos: () => call<Demo[]>("/api/demos"),
  rules: () => call<{ version: string; rules: Rule[] }>("/api/rules"),
  models: () => call<{ defaults: Record<string, string>; models: ModelInfo[] }>("/api/models"),
  openDemo: (demo_id: string) => call<SessionInfo>("/api/sessions", { method: "POST", body: JSON.stringify({ demo_id }) }),
  upload: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return call<SessionInfo>("/api/sessions/upload", { method: "POST", body: fd });
  },
  session: (id: string) => call<SessionInfo>(`/api/sessions/${id}`),
  close: (id: string) => call<{ deleted: boolean }>(`/api/sessions/${id}`, { method: "DELETE" }),
  ask: (id: string, question: string) =>
    call<AnswerView>(`/api/sessions/${id}/ask`, { method: "POST", body: JSON.stringify({ question }) }),
  feedback: (id: string, no: number, decision: "accept" | "reject") =>
    call<{ no: number; decision: string }>(`/api/sessions/${id}/findings/${no}/feedback`, {
      method: "POST",
      body: JSON.stringify({ decision }),
    }),
};
