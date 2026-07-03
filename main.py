from __future__ import annotations

import logging
import shutil

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router as count_reps_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

app = FastAPI(title="FitVision Pose & Rep Counting", version="3.0.0")


@app.on_event("startup")
def _log_startup():
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        logging.getLogger(__name__).info("ffmpeg found at %s", ffmpeg)
    else:
        logging.getLogger(__name__).warning(
            "ffmpeg not found — annotated videos will fail to transcode for browsers. "
            "Install with: brew install ffmpeg"
        )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(count_reps_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000)
