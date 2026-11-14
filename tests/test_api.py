"""The web demo's API (src/drawing_intelligence/api): auth, the demo catalogue, a review session end to end.

The seeded P13 drawing's model replies are in data/cache, so the session replays them; the fake completion
function makes a cache miss fail loudly instead of reaching a provider.
"""

import re
import shutil
import threading
import time
from typing import Any, cast

import pymupdf
import pytest
from fastapi.testclient import TestClient

from drawing_intelligence.api import create_app
from drawing_intelligence.api.runs import SessionStore
from drawing_intelligence.llm.client import CompletionFn
from drawing_intelligence.settings import PROJECT_ROOT


def _no_model(**_: Any) -> Any:
    raise AssertionError("cache miss: the API test would have called a model")


no_model = cast(CompletionFn, _no_model)


@pytest.fixture
def client(settings, tmp_path):
    # the repo's cached replies, copied: the run writes telemetry and the log next to them, never into data/
    shutil.copytree(PROJECT_ROOT / "data" / "cache", settings.cache_dir, copy_function=shutil.copyfile)
    store = SessionStore(settings, tmp_path / "sessions", completion_fn=no_model)
    app = create_app(settings, password="secret", web_dist=tmp_path / "none", store=store)
    with TestClient(app) as c:
        yield c


def _login(c: TestClient) -> dict[str, str]:
    token = c.post("/api/auth/login", json={"password": "secret"}).json()["token"]
    return {"X-Demo-Token": token}


def test_everything_needs_the_password(client):
    assert client.get("/api/auth").json() == {"required": True, "ok": False}
    assert client.get("/api/demos").status_code == 401
    assert client.post("/api/auth/login", json={"password": "nope"}).status_code == 401
    h = _login(client)
    assert client.get("/api/auth", headers=h).json()["ok"]
    demos = client.get("/api/demos", headers=h).json()
    assert {d["id"] for d in demos} >= {"cam-plate-seeded", "bearing-housing"}
    assert all("path" not in d and d["questions"] for d in demos)


def test_rules_and_models(client):
    h = _login(client)
    rules = client.get("/api/rules", headers=h).json()["rules"]
    assert len(rules) > 100 and {"id", "built", "check_type"} <= rules[0].keys()
    models = client.get("/api/models", headers=h).json()["models"]
    assert any(m["id"] == "qwen3.8-max" for m in models)


def test_a_review_session_end_to_end(client, settings):
    h = _login(client)
    sid = client.post("/api/sessions", json={"demo_id": "cam-plate-seeded"}, headers=h).json()["id"]
    s: dict[str, Any] = {}
    for _ in range(200):
        s = client.get(f"/api/sessions/{sid}", headers=h).json()
        if s["status"] in ("done", "error"):
            break
        time.sleep(0.1)
    assert s["status"] == "done", s.get("error")
    assert [st["status"] for st in s["stages"]] == ["done"] * 5
    assert s["cached"] and s["cost_usd"] == 0
    rules = {f["rule_id"] for f in s["findings"]}
    assert {"RQ-002", "WST-207"} <= rules  # the planted error, by code and by lookup
    boxed = [e for f in s["findings"] for e in f["evidence"] if e["bbox"]]
    assert boxed and all(0 <= e["bbox"][0] < s["sheets"][0]["w"] for e in boxed)
    assert all(f["plain_english"] for f in s["findings"])

    assert client.get(f"/api/sessions/{sid}/sheets/1.png", headers=h).headers["content-type"] == "image/png"
    t = h["X-Demo-Token"]
    assert client.get(f"/api/sessions/{sid}/report.xlsx?t={t}").status_code == 200

    r = client.post(f"/api/sessions/{sid}/findings/1/feedback", json={"decision": "reject"}, headers=h)
    assert r.json() == {"no": 1, "decision": "reject"}
    assert client.get(f"/api/sessions/{sid}", headers=h).json()["findings"][0]["feedback"] == "reject"
    assert '"decision":"reject"' in settings.feedback_log.read_text(encoding="utf-8")

    assert client.delete(f"/api/sessions/{sid}", headers=h).json() == {"deleted": True}
    assert client.get(f"/api/sessions/{sid}", headers=h).status_code == 404


def test_upload_accepts_only_pdfs(client):
    h = _login(client)
    r = client.post(
        "/api/sessions/upload", files={"file": ("x.pdf", b"not a pdf", "application/pdf")}, headers=h
    )
    assert r.status_code == 415


def test_front_end_effects_return_nothing():
    # `useEffect(() => expr)` hands expr's value to React as the cleanup. Chrome 156 returns a Promise from
    # scrollIntoView, so the Q&A pane's effect blanked the whole app on the first question.
    src = PROJECT_ROOT / "web" / "src"
    bad = [
        f"{p.relative_to(src)}:{i}"
        for p in sorted(src.rglob("*.tsx"))
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if re.search(r"use(Layout)?Effect\(\(\) => [^{\s]", line)
    ]
    assert not bad, f"effects with an expression body: {bad}"


P13 = PROJECT_ROOT / "data" / "eval" / "seeded" / "P13_fit_limits_inverted" / "P13_fit_limits_inverted.pdf"


def _wait(cond, timeout=60.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


@pytest.fixture
def gated_store(settings, tmp_path):
    """A store whose model calls block until `gate` is set (then fail): live uploads hang in Understand."""
    shutil.copytree(PROJECT_ROOT / "data" / "cache", settings.cache_dir, copy_function=shutil.copyfile)
    gate = threading.Event()

    def blocked(*_: Any, **__: Any) -> Any:
        gate.wait(30)
        raise AssertionError("the gated test model was called")

    store = SessionStore(settings, tmp_path / "sessions", completion_fn=cast(CompletionFn, blocked))
    yield store, gate
    gate.set()
    store.shutdown()


def test_demo_replays_do_not_wait_for_live_uploads(gated_store, make_pdf):
    store, _ = gated_store
    live = [store.create(make_pdf(f"up{i}.pdf"), f"up{i}.pdf", None, live=True) for i in range(2)]
    assert _wait(lambda: all(s.status == "running" for s in live))
    demo = store.create(P13, "P13", "cam-plate-seeded", live=False)
    assert _wait(lambda: demo.status in ("done", "error")), demo.status
    assert demo.status == "done", demo.error
    # the uploads are still stuck in their model call
    assert all(s.status == "running" for s in live), [(s.status, s.error) for s in live]


def test_closing_a_session_stops_its_review(gated_store, make_pdf):
    store, gate = gated_store
    running = [store.create(make_pdf(f"up{i}.pdf"), f"up{i}.pdf", None, live=True) for i in range(2)]
    assert _wait(lambda: all(s.status == "running" for s in running))
    queued = store.create(make_pdf("up2.pdf"), "up2.pdf", None, live=True)
    assert queued.status == "queued"
    assert store.delete(queued.id) and store.delete(running[0].id)
    gate.set()  # the stuck model call returns (and fails); the closed run must not go on to the reviewers
    assert _wait(lambda: running[0].status != "running" and running[1].status != "running")
    assert running[0].status == "cancelled" and not running[0].folder.exists()
    assert running[1].status == "error"  # still open: its failure is shown, not swallowed
    assert running[1].error and "could not finish" in running[1].error and "/" not in running[1].error
    assert _wait(lambda: not queued.folder.exists())
    time.sleep(0.3)
    assert queued.started is None and queued.status == "queued"  # it never ran


def _pdf_bytes(pages: int = 1, text: str = "") -> bytes:
    doc = pymupdf.open()
    for _ in range(pages):
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text, fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.mark.parametrize(
    ("data", "status", "says"),
    [
        (b"%PDF-1.4\n" + b"garbage" * 50, 415, "could not be opened"),
        (_pdf_bytes(5, "SCALE 1:1 MATERIAL EN8 " * 4), 422, "5 pages"),
        (_pdf_bytes(1), 422, "no readable text"),
        (_pdf_bytes(1, "Plating process selection guideline for alloy steels, rev 3"), 422, "PARI drawing"),
    ],
    ids=["corrupt", "too-many-pages", "scan-or-blank", "not-a-drawing"],
)
def test_uploads_are_screened_before_any_cost(client, data, status, says):
    h = _login(client)
    before = client.get("/api/health").json()["live_runs_left"]
    r = client.post("/api/sessions/upload", files={"file": ("x.pdf", data, "application/pdf")}, headers=h)
    assert r.status_code == status and says in r.json()["detail"]
    assert "/" not in r.json()["detail"].replace("1:1", "")  # no server paths in what the user sees
    assert client.get("/api/health").json()["live_runs_left"] == before  # a turned-away file is free


def test_a_pari_drawing_passes_the_screen(client):
    h = _login(client)
    before = client.get("/api/health").json()["live_runs_left"]
    r = client.post(
        "/api/sessions/upload", files={"file": ("p13.pdf", P13.read_bytes(), "application/pdf")}, headers=h
    )
    assert r.status_code == 200
    assert client.get("/api/health").json()["live_runs_left"] == before - 1
    client.delete(f"/api/sessions/{r.json()['id']}", headers=h)


def test_models_say_whether_their_provider_has_a_key(settings, tmp_path):
    no_openai = settings.model_copy(update={"openai_api_key": None})
    store = SessionStore(no_openai, tmp_path / "s", completion_fn=no_model)
    app = create_app(no_openai, password="secret", web_dist=tmp_path / "none", store=store)
    with TestClient(app) as c:
        models = {m["id"]: m for m in c.get("/api/models", headers=_login(c)).json()["models"]}
    assert models["qwen3.8-max"]["available"] and not models["gpt-6-astra"]["available"]


@pytest.mark.parametrize(
    ("fields", "says"),
    [
        ({"review_model": "qwen3-vl-plus"}, "cannot be used for the review role"),
        ({"understand_model": "no-such-model"}, "Unknown model"),
        ({"understand_model": "qwen3-vl-plus", "understand_thinking": "ultra"}, "no thinking level"),
    ],
)
def test_an_unusable_model_choice_is_refused_before_anything_runs(client, fields, says):
    h = _login(client)
    before = client.get("/api/health").json()["live_runs_left"]
    r = client.post(
        "/api/sessions/upload",
        files={"file": ("p13.pdf", P13.read_bytes(), "application/pdf")},
        data=fields,
        headers=h,
    )
    assert r.status_code == 422 and says in r.json()["detail"]
    assert client.get("/api/health").json()["live_runs_left"] == before


def test_the_chosen_models_reach_the_session(client):
    h = _login(client)
    fields = {"review_model": "qwen3.8-max", "review_thinking": "on"}
    r = client.post(
        "/api/sessions/upload",
        files={"file": ("p13.pdf", P13.read_bytes(), "application/pdf")},
        data=fields,
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["models"] == fields
    client.delete(f"/api/sessions/{r.json()['id']}", headers=h)


def test_a_qa_model_choice_is_checked(client):
    h = _login(client)
    sid = client.post("/api/sessions", json={"demo_id": "cam-plate-seeded"}, headers=h).json()["id"]
    assert _wait(lambda: client.get(f"/api/sessions/{sid}", headers=h).json()["status"] == "done")
    r = client.post(f"/api/sessions/{sid}/ask", json={"question": "Why?", "model": "nope"}, headers=h)
    assert r.status_code == 422


def test_the_rulebook_downloads_as_a_spreadsheet(client):
    from io import BytesIO

    import openpyxl

    h = _login(client)
    r = client.get(f"/api/rules.xlsx?t={h['X-Demo-Token']}")
    assert r.status_code == 200 and "rulebook" in r.headers["content-disposition"]
    ws = openpyxl.load_workbook(BytesIO(r.content))["Rules"]
    rows = list(ws.iter_rows(values_only=True))
    n_rules = len(client.get("/api/rules", headers=h).json()["rules"])
    assert rows[0][:3] == ("Rule", "Category", "Requirement") and len(rows) == n_rules + 1
    assert (
        "yes" in {str(row[5]) for row in rows[1:]} <= {"yes", "not built yet"}
    )  # every rule built since 2026-11-13


def test_a_batch_runs_each_drawing_and_zips_the_reports(client):
    import zipfile
    from io import BytesIO

    h = _login(client)
    files = [
        ("files", ("cam_a.pdf", P13.read_bytes(), "application/pdf")),
        ("files", ("cam_b.pdf", P13.read_bytes(), "application/pdf")),  # replies cached: finishes for $0
        ("files", ("blank.pdf", _pdf_bytes(1), "application/pdf")),
    ]
    b = client.post("/api/batches", files=files, headers=h).json()
    assert [i["status"] for i in b["items"]][2] == "rejected" and "no readable text" in b["items"][2][
        "detail"
    ]

    def view():
        return client.get(f"/api/batches/{b['id']}", headers=h).json()

    assert _wait(lambda: view()["running"] == 0, timeout=120)
    v = view()
    assert v["done"] == 2 and all(i["findings"] >= 1 and i["fails"] >= 1 for i in v["items"][:2])
    z = zipfile.ZipFile(
        BytesIO(client.get(f"/api/batches/{b['id']}/reports.zip?t={h['X-Demo-Token']}").content)
    )
    assert sorted(z.namelist()) == ["cam_a_review.xlsx", "cam_b_review.xlsx", "summary.xlsx"]

    # a drawing of the batch is an ordinary session, and closing the batch ends them all
    sid = v["items"][0]["session_id"]
    assert client.get(f"/api/sessions/{sid}", headers=h).json()["status"] == "done"
    assert client.delete(f"/api/batches/{b['id']}", headers=h).json() == {"deleted": True}
    assert client.get(f"/api/sessions/{sid}", headers=h).status_code == 404


def test_a_batch_has_a_size_limit(client):
    h = _login(client)
    files = [("files", (f"d{i}.pdf", b"%PDF-1.4", "application/pdf")) for i in range(11)]
    r = client.post("/api/batches", files=files, headers=h)
    assert r.status_code == 422 and "up to 10" in r.json()["detail"]
