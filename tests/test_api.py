"""The web demo's API (src/drawing_intelligence/api): auth, the demo catalogue, a review session end to end.

The seeded P13 drawing's model replies are in data/cache, so the session replays them; the fake completion
function makes a cache miss fail loudly instead of reaching a provider.
"""

import re
import shutil
import threading
import time
from typing import Any, cast

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
    assert _wait(lambda: not queued.folder.exists())
    time.sleep(0.3)
    assert queued.started is None and queued.status == "queued"  # it never ran
