# The web demo (FastAPI + the React app in web/) as one container, for a Hugging Face Docker Space or any host.
#   docker build -t drawing-intelligence-demo .
#   docker run -p 7860:7860 -e QWEN_API_KEY=... -e DI_DEMO_PASSWORD=... drawing-intelligence-demo
# Secrets come from the environment (Space secrets); .env is never copied in (see .dockerignore).

# --- 1. build the front end ---------------------------------------------------------------------------------------
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# --- 2. the API, the package and the demo data -----------------------------------------------------------------
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /usr/local/bin/uv
ENV PYTHONUNBUFFERED=1 UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_PROJECT_ENVIRONMENT=/app/.venv
RUN useradd -m -u 1000 user
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --extra web --no-install-project
COPY src/ src/
COPY config/ config/
RUN uv sync --frozen --no-dev --extra web

# Only what the demo needs from data/: the cached model replies and the four demo drawings (config/demo).
COPY data/cache/ data/cache/
COPY ["data/client_set/Generic Round Parts (Pins, Shafts)/P23Y5B091115002.PDF", "data/client_set/Generic Round Parts (Pins, Shafts)/"]
COPY ["data/client_set/Generic Prismatic Parts/20K_MODULE PALLET ANTI BACK LEAVER_01.pdf", "data/client_set/Generic Prismatic Parts/"]
COPY data/eval/seeded/P13_fit_limits_inverted/P13_fit_limits_inverted.pdf data/eval/seeded/P13_fit_limits_inverted/
COPY data/eval/seeded/C01_clean_cam_plate/C01_clean_cam_plate.pdf data/eval/seeded/C01_clean_cam_plate/
COPY --from=web /web/dist web/dist

# The app writes telemetry, the feedback log and new cache entries under data/, and sessions under /tmp.
RUN chown -R user:user /app
USER user
ENV DI_WEB_DIST=/app/web/dist DI_SESSIONS_ROOT=/tmp/di-sessions HOME=/home/user
EXPOSE 7860
CMD ["/app/.venv/bin/uvicorn", "drawing_intelligence.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "7860"]
