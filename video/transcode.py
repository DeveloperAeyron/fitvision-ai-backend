from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import tempfile

logger = logging.getLogger(__name__)


def _video_encoder_args() -> list[str]:
    if platform.system() == "Darwin":
        return ["-c:v", "h264_videotoolbox", "-b:v", "2M"]
    return ["-c:v", "libx264", "-preset", "fast", "-crf", "23"]


def transcode_for_web(input_path: str) -> str:
    """Re-encode OpenCV mp4v output to H.264 for browser playback."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError(
            "ffmpeg is not installed; annotated video cannot play in browsers. "
            "Install with: brew install ffmpeg"
        )

    out_fd, output_path = tempfile.mkstemp(suffix=".mp4")
    os.close(out_fd)

    cmd = [
        ffmpeg,
        "-y",
        "-i",
        input_path,
        *_video_encoder_args(),
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-an",
        output_path,
    ]
    logger.info("transcoding annotated video to H.264")

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        os.remove(output_path)
        stderr = (exc.stderr or "").strip()
        logger.error("ffmpeg transcode failed: %s", stderr or exc)
        raise RuntimeError(
            "Failed to re-encode annotated video to H.264 for browser playback."
            + (f" ffmpeg: {stderr}" if stderr else "")
        ) from exc

    out_size = os.path.getsize(output_path)
    logger.info("transcode complete output_bytes=%d", out_size)
    return output_path
