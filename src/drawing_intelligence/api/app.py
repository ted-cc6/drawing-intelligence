"""The web demo's API (FastAPI): a thin layer over the package, plus the built React app (web/).

Run it locally with `uv run uvicorn drawing_intelligence.api.app:create_app --factory --port 8000`.
Environment:

    DI_DEMO_PASSWORD      when set, every /api call needs the token returned by POST /api/auth/login
    DI_WEB_DIST           the built front end (default: <repo>/web/dist); not served when missing
    DI_DEMO_MAX_LIVE_RUNS uploads this server will review with live model calls (default 100)
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal, cast

import yaml
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from drawing_intelligence.api.runs import DemoSession, SessionStore
from drawing_intelligence.api.uploads import UploadRejected, screen_pdf
from drawing_intelligence.api.views import answer_view, session_detail, session_summary, sheet_image
from drawing_intelligence.llm import load_registry
from drawing_intelligence.llm.registry import Registry, Role
from drawing_intelligence.review import load_rulebook
from drawing_intelligence.review.checks import param_models
from drawing_intelligence.schemas import FindingFeedback
from drawing_intelligence.schemas.review import CATEGORY_LABELS
from drawing_intelligence.settings import PROJECT_ROOT, Settings, get_settings

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class Login(BaseModel):
    password: str


class OpenDemo(BaseModel):
    demo_id: str


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    model: str | None = None  # the Q&A model chosen in Options; None = the registry's default
    thinking: str | None = None


class Feedback(BaseModel):
    decision: Literal["accept", "reject"]
    comment: str | None = Field(default=None, max_length=1000)


def check_choice(
    reg: Registry, settings: Settings, role: str, model: str | None, thinking: str | None
) -> tuple[str | None, str | None]:
    """A model and thinking level picked for one role, checked against the registry; 422 if unusable."""
    if not model and not thinking:
        return None, None
    name = model or reg.defaults[cast(Role, role)]
    spec = reg.models.get(name)
    if spec is None:
        raise HTTPException(422, f"Unknown model {name!r}.")
    if role not in spec.roles:
        raise HTTPException(422, f"{spec.label} cannot be used for the {role} role.")
    if not settings.api_key(reg.providers[spec.provider].api_key_env):
        raise HTTPException(
            422, f"{spec.label} is not available on this server (no API key for its provider)."
        )
    if thinking and thinking not in spec.thinking.options:
        raise HTTPException(422, f"{spec.label} has no thinking level {thinking!r}.")
    return model, thinking


def load_demos(settings: Settings) -> list[dict[str, Any]]:
    p = settings.config_path / "demo" / "drawings.yaml"
    data = (yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.exists() else {}
    common = data.get("questions") or []
    out = []
    for d in data.get("drawings") or []:
        path = PROJECT_ROOT / d["path"]
        if path.exists():  # a deployment may ship only some of them
            out.append({**d, "path": path, "questions": [*(d.get("questions") or []), *common]})
    return out


def create_app(
    settings: Settings | None = None,
    *,
    password: str | None = None,
    web_dist: Path | None = None,
    store: SessionStore | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    password = password if password is not None else os.environ.get("DI_DEMO_PASSWORD") or None
    secret = secrets.token_bytes(32)  # tokens last as long as this process, like the sessions
    token = hmac.new(secret, b"drawing-intelligence-demo", hashlib.sha256).hexdigest()
    dist = web_dist or Path(os.environ.get("DI_WEB_DIST", PROJECT_ROOT / "web" / "dist"))
    max_live = int(os.environ.get("DI_DEMO_MAX_LIVE_RUNS", "100"))
    the_store = store or SessionStore(settings, Path(tempfile.mkdtemp(prefix="di-web-")), max_live=max_live)
    demos = {d["id"]: d for d in load_demos(settings)}

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        the_store.shutdown()

    app = FastAPI(title="Drawing Intelligence demo API", version="0.1.0", lifespan=lifespan)

    def authed(
        x_demo_token: Annotated[str | None, Header()] = None, t: Annotated[str | None, Query()] = None
    ) -> None:
        if password is None:
            return
        given = x_demo_token or t or ""
        if not hmac.compare_digest(given, token):
            raise HTTPException(401, "sign in first")

    Auth = Depends(authed)

    def session_or_404(sid: str) -> DemoSession:
        sess = the_store.get(sid)
        if sess is None:
            raise HTTPException(404, "this session has ended; open the drawing again")
        return sess

    def done_or_409(sess: DemoSession) -> None:
        if sess.status != "done" or sess.data is None:
            raise HTTPException(409, "the review has not finished")

    def start_upload(data: bytes, filename: str | None, models: dict[str, str]) -> DemoSession:
        """Screen one uploaded PDF and start its live review; HTTPException (a sentence) if turned away."""
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "The PDF is larger than 25 MB.")
        if not data.startswith(b"%PDF"):
            raise HTTPException(415, "Only PDF drawings can be reviewed.")
        try:
            screen_pdf(data, settings.config_path)  # before the allowance: a turned-away file costs nothing
        except UploadRejected as e:
            raise HTTPException(e.status, e.message) from e
        if the_store.live_left <= 0:
            raise HTTPException(
                429, "The demo's allowance of live reviews is used up. Open a demo drawing instead."
            )
        the_store.live_left -= 1
        tmp = Path(tempfile.mkdtemp(prefix="di-up-")) / "upload.pdf"
        tmp.write_bytes(data)
        try:
            name = Path(filename or "drawing.pdf").name
            return the_store.create(tmp, name, None, live=True, models=models)
        finally:
            tmp.unlink(missing_ok=True)
            tmp.parent.rmdir()

    # --- auth -----------------------------------------------------------------------------------------------

    @app.get("/api/auth")
    def auth_status(x_demo_token: Annotated[str | None, Header()] = None) -> dict[str, bool]:
        ok = password is None or hmac.compare_digest(x_demo_token or "", token)
        return {"required": password is not None, "ok": ok}

    @app.post("/api/auth/login")
    def login(body: Login) -> dict[str, str]:
        if password is not None and not hmac.compare_digest(body.password, password):
            raise HTTPException(401, "wrong password")
        return {"token": token}

    # --- reference data -------------------------------------------------------------------------------------

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, **the_store.stats()}

    @app.get("/api/demos", dependencies=[Auth])
    def list_demos() -> list[dict[str, Any]]:
        return [{k: v for k, v in d.items() if k != "path"} for d in demos.values()]

    @app.get("/api/rules", dependencies=[Auth])
    def list_rules() -> dict[str, Any]:
        checks = param_models()
        book = load_rulebook(settings.config_path / "rules", checks=checks)
        rules = [
            {
                "id": r.id,
                "category": r.category,
                "category_label": CATEGORY_LABELS.get(r.category, r.category),
                "requirement": r.requirement,
                "severity": r.severity,
                "check_type": r.check_type,
                "built": r.check_type == "llm" or r.check in checks,
                "status": r.status,
                "source": r.source.document,
            }
            for r in book.rules
        ]
        return {"version": book.version, "rules": rules}

    @app.get("/api/models", dependencies=[Auth])
    def list_models() -> dict[str, Any]:
        reg = load_registry(settings.config_path / "models.yaml")
        return {
            "defaults": reg.defaults,
            "models": [
                {
                    "id": mid,
                    "label": m.label,
                    "provider": reg.providers[m.provider].label,
                    "roles": m.roles,
                    "thinking": list(m.thinking.options),
                    "thinking_default": m.thinking.default,
                    "price_in": m.price.input_per_mtok,
                    "price_out": m.price.output_per_mtok,
                    "available": bool(settings.api_key(reg.providers[m.provider].api_key_env)),
                }
                for mid, m in reg.models.items()
            ],
        }

    # --- sessions -------------------------------------------------------------------------------------------

    @app.post("/api/sessions", dependencies=[Auth])
    def open_demo(body: OpenDemo) -> dict[str, Any]:
        d = demos.get(body.demo_id)
        if d is None:
            raise HTTPException(404, "unknown demo drawing")
        return session_summary(the_store.create(d["path"], d["title"], d["id"], live=False))

    @app.post("/api/sessions/upload", dependencies=[Auth])
    async def upload(
        file: Annotated[UploadFile, File()],
        understand_model: Annotated[str | None, Form()] = None,
        understand_thinking: Annotated[str | None, Form()] = None,
        review_model: Annotated[str | None, Form()] = None,
        review_thinking: Annotated[str | None, Form()] = None,
    ) -> dict[str, Any]:
        reg = load_registry(settings.config_path / "models.yaml")
        um, ut = check_choice(reg, settings, "understand", understand_model, understand_thinking)
        rm, rt = check_choice(reg, settings, "review", review_model, review_thinking)
        chosen = {"model": um, "thinking": ut, "review_model": rm, "review_thinking": rt}
        models = {k: v for k, v in chosen.items() if v}
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        return session_summary(start_upload(data, file.filename, models))

    @app.get("/api/sessions/{sid}", dependencies=[Auth])
    def get_session(sid: str) -> dict[str, Any]:
        sess = session_or_404(sid)
        return session_detail(sess, settings.config_path) if sess.status == "done" else session_summary(sess)

    @app.delete("/api/sessions/{sid}", dependencies=[Auth])
    def end_session(sid: str) -> dict[str, bool]:
        return {"deleted": the_store.delete(sid)}

    @app.get("/api/sessions/{sid}/sheets/{page}.png", dependencies=[Auth])
    def sheet(sid: str, page: int) -> FileResponse:
        sess = session_or_404(sid)
        done_or_409(sess)
        assert sess.data is not None
        p = sess.data.pages.get(page)
        if p is None or p.images is None:
            raise HTTPException(404, "no such sheet")
        return FileResponse(sheet_image(sess, p), media_type="image/png")

    @app.get("/api/sessions/{sid}/report.xlsx", dependencies=[Auth])
    def report(sid: str) -> FileResponse:
        sess = session_or_404(sid)
        done_or_409(sess)
        p = sess.out_dir / "review_report.xlsx"
        if not p.exists():
            raise HTTPException(404, "no report")
        return FileResponse(p, filename=f"{Path(sess.name).stem}_review.xlsx")

    @app.get("/api/sessions/{sid}/annotated/{page}.png", dependencies=[Auth])
    def annotated(sid: str, page: int) -> FileResponse:
        sess = session_or_404(sid)
        done_or_409(sess)
        p = sess.out_dir / f"page_{page}_review.png"
        if not p.exists():
            raise HTTPException(404, "no annotated sheet")
        return FileResponse(p, filename=f"{Path(sess.name).stem}_sheet{page}_review.png")

    @app.post("/api/sessions/{sid}/ask", dependencies=[Auth])
    def ask(sid: str, body: Question) -> dict[str, Any]:
        sess = session_or_404(sid)
        done_or_409(sess)
        assert sess.data is not None
        reg = load_registry(settings.config_path / "models.yaml")
        model, thinking = check_choice(reg, settings, "qa", body.model, body.thinking)
        try:
            answer = the_store.ask(sess, body.question.strip(), model, thinking)
        except Exception as e:  # e.g. no API key and no cached reply: tell the user, keep the session
            raise HTTPException(502, f"the Q&A model could not answer: {type(e).__name__}") from e
        return answer_view(answer, sess.data, sess)

    @app.post("/api/sessions/{sid}/findings/{no}/feedback", dependencies=[Auth])
    def feedback(sid: str, no: int, body: Feedback) -> dict[str, Any]:
        sess = session_or_404(sid)
        done_or_409(sess)
        assert sess.data is not None
        f = sess.data.findings.get(no)
        if f is None:
            raise HTTPException(404, "no such finding")
        the_store.record_feedback(
            sess,
            FindingFeedback(finding_id=f.id, decision=body.decision, comment=body.comment, role="checker"),
        )
        return {"no": no, "decision": body.decision}

    # --- the front end --------------------------------------------------------------------------------------

    if (dist / "index.html").exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")

    return app
