from __future__ import annotations

import os
import shutil
import subprocess
import tempfile


def transcode_for_web(input_path: str) -> str:
    """Re-encode OpenCV mp4v output to H.264 for browser playback."""
    if shutil.which("ffmpeg") is None:
        return input_path

    out_fd, output_path = tempfile.mkstemp(suffix=".mp4")
    os.close(out_fd)

    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                input_path,
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-an",
                output_path,
            ],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        os.remove(output_path)
        return input_path

    return output_path
