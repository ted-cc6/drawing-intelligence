# 0012 Web demo: FastAPI over the package, a React front end, one Docker image

**Status:** accepted · 2026-11-02

## Context
PROJECT.md §7 planned a dashboard over the package (milestone M5). The client demo on 2026-11-03 needs it: the
audience is LatentView's consultants, who judge the design and are not engineers. The user's requirements:
React + FastAPI; the look of an engineering desktop application (Solid Edge, which PARI uses), not a web page;
the must-have features working (open or upload a drawing, live stage progress, the sheet with numbered findings,
the findings list with filters, rule coverage, Q&A with citations, accept/reject, Excel download); the other
planned features visible but marked "pilot"; hosted on a Hugging Face Space that the consultants can open
themselves afterwards.

## Decision
- **API:** `src/drawing_intelligence/api/` (FastAPI, optional extra `web`). It calls `run_workflow`, `DrawingData`
  and the Q&A `Conversation` exactly as the CLI does and adds no review logic. One addition to the package:
  `run_workflow(progress=...)`, a callback per finished graph node, for the stage bar.
- **Sessions:** one in-memory `DemoSession` per opened drawing, in a temporary folder deleted when the user closes
  the drawing or after two idle hours (ADR 0003). Runs use `retention: keep` so the shared response cache is
  read; the workspace still lives inside the session folder.
- **Demo drawings** (`config/demo/drawings.yaml`): four drawings whose replies are cached, so they open in seconds
  for $0. Uploads run live (about 2 minutes, about $0.04); `DI_DEMO_MAX_LIVE_RUNS` caps them per restart.
- **Plain-English explanations** (`config/demo/plain_english.yaml`) per rule, with a category fallback: wording
  for non-engineers, written by hand, never generated.
- **Access:** a public Space with a password screen (`DI_DEMO_PASSWORD`). The token travels in a header, not a
  cookie, because the Space runs inside an iframe on huggingface.co. Keys are Space secrets.
- **Front end:** `web/` (React 18 + Vite + TypeScript, lucide icons, hand-written CSS, no UI kit). The layout
  follows an engineering desktop application: ribbon, PathFinder tree, graphics window with zoom and pan,
  docked Properties and Ask panes, a markups-style findings table and a status bar. No Siemens logos or names.
- **Image:** one `Dockerfile` (node build stage, then Python with uv) that copies only the package, `config/`,
  `data/cache/` and the four demo PDFs.

## Consequences
- The CLI and the web demo share every result; the web demo is a view.
- Feedback from the web goes to the same `feedback.jsonl` as the Q&A agent's; on a Space it is lost on restart
  (acceptable for a demo; the pilot needs persistent storage).
- New npm dependencies are a second toolchain; CI builds the front end on Linux only.
- `npm install` fails on the WSL `/mnt/d` mount, so the front end is installed and built outside the repo there.

## Update 2026-11-08 (before the in-office client demo)
- **Two run lanes:** live uploads and cached demo replays have separate two-thread pools, so a demo drawing
  never waits behind uploads. Closing a session cancels its run (skipped if queued, stopped at the next graph
  node if running).
- **Upload screen** (`api/uploads.py`): before any model call and before the live allowance is used, an upload
  must open as a PDF, have at most 4 pages, have a text layer and look like a PARI drawing (standard title
  block by its anchors, or "scale" and "material" for the older variant blocks). Rejections are plain
  sentences in a dialog. `DI_DEMO_MAX_LIVE_RUNS` defaults to 100.
- Review failures show a sentence; details go to the server log, never server paths to the user.

## Update 2026-11-08 (pilot phase 1: four PILOT placeholders built)
- **Model per role:** Options chooses model and thinking for Understand, the AI reviewers and Q&A; kept in the
  browser, sent with each upload and question, checked against `config/models.yaml` (role, thinking level,
  provider key present) with 422 before anything runs. Models without a key are shown disabled.
- **Measure:** two clicks on the sheet give the distance on paper and at the title-block scale (`px_per_pt`
  per sheet).
- **Rulebook (.xlsx):** `GET /api/rules.xlsx`.
- **Batch review:** `POST /api/batches` (up to 10 PDFs, each screened, accepted ones are ordinary live
  sessions), `GET`/`DELETE /api/batches/{id}`, `GET /api/batches/{id}/reports.zip` (summary + checklists).
- Still PILOT: compare revisions, sign-off, send to designer, confirm and edit rules, feedback analytics, run
  history across users. They need persistent storage and user accounts first.
