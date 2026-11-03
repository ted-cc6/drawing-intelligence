---
title: Drawing Intelligence for Wipro PARI
emoji: 📐
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
short_description: AI first-pass review of 2D engineering drawings (demo)
---

# Drawing Intelligence: web demo

LatentView Drawing Intelligence for Wipro PARI, a UChicago MSADS capstone. This Space runs the repo's
`Dockerfile`: the FastAPI app in `src/drawing_intelligence/api` serving the React front end in `web/`.

Space secrets: `QWEN_API_KEY` (live reviews and Q&A) and `DI_DEMO_PASSWORD` (the sign-in screen).
Optional variable: `DI_DEMO_MAX_LIVE_RUNS` (uploads reviewed live per restart, default 30).

The four demo drawings replay cached model replies, so opening them costs nothing. Uploaded PDFs are reviewed
live and deleted when the session is closed or after two idle hours.
