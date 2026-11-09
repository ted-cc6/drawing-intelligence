"""Deploy the web demo to its public Hugging Face Docker Space (ADR 0012).

Usage (from the repo root; needs `huggingface_hub`, e.g. `uv run --with huggingface_hub python ...`):

    HF_TOKEN=... python deploy/huggingface/space.py <command>

  files     list what an upload would send (nothing is sent)
  create    create the public Docker Space (cpu-basic)
  secrets   set QWEN_API_KEY (from .env) and DI_DEMO_PASSWORD (from the environment); values never printed
  upload    upload the allowlisted files in one commit, removing Space files no longer in the list
  wait      poll the runtime until RUNNING
  logs      print the end of the run log ('logs build' for the build log)

Only the allowlist below is uploaded: never .env, tests, docs, spikes or the rest of data/.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx
from huggingface_hub import CommitOperationAdd, CommitOperationDelete, HfApi

ROOT = Path(__file__).resolve().parents[2]
SPACE_NAME = "drawing-intelligence"

ALLOW_FILES = [
    "Dockerfile",
    ".dockerignore",
    "pyproject.toml",
    "uv.lock",
    "web/package.json",
    "web/package-lock.json",
    "web/index.html",
    "web/tsconfig.json",
    "web/vite.config.ts",
    "data/client_set/Generic Round Parts (Pins, Shafts)/P23Y5B091115002.PDF",
    "data/client_set/Generic Prismatic Parts/20K_MODULE PALLET ANTI BACK LEAVER_01.pdf",
    "data/eval/seeded/P13_fit_limits_inverted/P13_fit_limits_inverted.pdf",
    "data/eval/seeded/C01_clean_cam_plate/C01_clean_cam_plate.pdf",
]
ALLOW_DIRS = ["src/drawing_intelligence", "config", "data/cache", "web/src", "web/public"]
SKIP_PARTS = {"__pycache__", "node_modules", "dist"}


def _api() -> HfApi:
    token = os.environ.get("HF_TOKEN")
    if not token:
        sys.exit("set HF_TOKEN (a write token for your account) in the environment")
    return HfApi(token=token)


def _space(api: HfApi) -> str:
    return f"{api.whoami()['name']}/{SPACE_NAME}"


def files() -> list[str]:
    out = [f for f in ALLOW_FILES if (ROOT / f).is_file()]
    for d in ALLOW_DIRS:
        for p in sorted((ROOT / d).rglob("*")):
            rel = p.relative_to(ROOT)
            if p.is_file() and not SKIP_PARTS & set(rel.parts) and p.suffix != ".pyc":
                out.append(rel.as_posix())
    return out


def create(api: HfApi) -> None:
    space = _space(api)
    api.create_repo(
        space, repo_type="space", private=False, exist_ok=True, space_sdk="docker", space_hardware="cpu-basic"
    )
    print(f"space {space} private={api.space_info(space).private}")


def secrets(api: HfApi) -> None:
    from drawing_intelligence.settings import get_settings

    space = _space(api)
    key = get_settings().api_key("QWEN_API_KEY")
    password = os.environ.get("DI_DEMO_PASSWORD")
    if not key or not password:
        sys.exit("need QWEN_API_KEY in .env and DI_DEMO_PASSWORD in the environment")
    api.add_space_secret(space, "QWEN_API_KEY", key)
    api.add_space_secret(space, "DI_DEMO_PASSWORD", password)
    api.add_space_variable(space, "DI_DEMO_MAX_LIVE_RUNS", os.environ.get("DI_DEMO_MAX_LIVE_RUNS", "100"))
    print("secrets set: QWEN_API_KEY, DI_DEMO_PASSWORD; variable: DI_DEMO_MAX_LIVE_RUNS")


def upload(api: HfApi) -> None:
    space = _space(api)
    local = files()
    readme = ROOT / "deploy" / "huggingface" / "README.md"  # the Space card; also the README the build needs
    ops = [CommitOperationAdd(path_in_repo=f, path_or_fileobj=str(ROOT / f)) for f in local]
    ops.append(CommitOperationAdd(path_in_repo="README.md", path_or_fileobj=str(readme)))
    keep = {*local, "README.md", ".gitattributes"}
    stale = [f for f in api.list_repo_files(space, repo_type="space") if f not in keep]
    ops += [CommitOperationDelete(path_in_repo=f) for f in stale]
    api.create_commit(space, repo_type="space", operations=ops, commit_message="Deploy the web demo")
    print(f"uploaded {len(local) + 1} files, removed {len(stale)}")


def wait(api: HfApi, timeout: float = 1800) -> None:
    space, t0, last = _space(api), time.perf_counter(), None
    while time.perf_counter() - t0 < timeout:
        stage = api.get_space_runtime(space).stage
        if stage != last:
            print(f"  {time.perf_counter() - t0:6.1f}s  {stage}", flush=True)
            last = stage
        if stage == "RUNNING":
            return
        if stage in ("BUILD_ERROR", "RUNTIME_ERROR", "CONFIG_ERROR"):
            sys.exit(f"stage {stage}: run 'logs build' or 'logs'")
        time.sleep(10)
    sys.exit("timeout")


def logs(api: HfApi, kind: str = "run", tail: int = 60) -> None:
    url = f"https://huggingface.co/api/spaces/{_space(api)}/logs/{kind}"
    lines: list[str] = []
    try:
        with httpx.stream(
            "GET", url, headers={"Authorization": f"Bearer {api.token}"}, timeout=httpx.Timeout(20, read=8)
        ) as r:
            for line in r.iter_lines():
                if line.startswith("data:"):
                    try:
                        lines.append(json.loads(line[5:]).get("data", "").rstrip())
                    except ValueError:
                        lines.append(line[5:].rstrip())
    except httpx.ReadTimeout:
        pass  # the stream stays open; a quiet stream means everything has been read
    print("\n".join(lines[-tail:]) or "(no log lines)")


if __name__ == "__main__":
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "files":
        print("\n".join(files()))
    else:
        hf = _api()
        {"create": create, "secrets": secrets, "upload": upload, "wait": wait}.get(cmd, lambda a: None)(hf)
        if cmd == "logs":
            logs(hf, args[0] if args else "run")
