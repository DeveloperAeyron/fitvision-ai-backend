from __future__ import annotations

import os
import shutil
import tempfile
import urllib.request
import zipfile

# The provided .tflite files are raw networks without the embedded TFLite
# metadata (NormalizationOptions, output names) that MediaPipe's Tasks API
# requires. Since they share the stock BlazePose-full architecture, this script
# grafts the metadata from the official pose_landmarker bundle onto them and
# repackages the result as a .task bundle MediaPipe can load.

DETECTOR_SRC = "weights/pose_person_detector_f16.tflite"
LANDMARK_SRC = "weights/pose_landmark_detector_full_f16_inf.tflite"
OUTPUT_TASK = "weights/pose_landmarker_custom.task"
OFFICIAL_TASK_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_full/float16/latest/pose_landmarker_full.task"
)

# member name inside the bundle -> our source weights
_MEMBERS = {
    "pose_detector.tflite": DETECTOR_SRC,
    "pose_landmarks_detector.tflite": LANDMARK_SRC,
}


def _graft_metadata(official_bytes, our_path, dst_path):
    from mediapipe.tasks.python.metadata import metadata as mdata

    tmp = tempfile.mktemp(suffix=".tflite")
    with open(tmp, "wb") as f:
        f.write(official_bytes)
    meta_buf = mdata.MetadataDisplayer.with_model_file(tmp).get_metadata_buffer()
    os.remove(tmp)

    shutil.copy(our_path, dst_path)
    populator = mdata.MetadataPopulator.with_model_file(dst_path)
    populator.load_metadata_buffer(meta_buf)
    populator.populate()


def build(official_task_path=None, output_task=OUTPUT_TASK):
    if official_task_path is None:
        official_task_path = tempfile.mktemp(suffix=".task")
        urllib.request.urlretrieve(OFFICIAL_TASK_URL, official_task_path)

    official = zipfile.ZipFile(official_task_path)
    work = tempfile.mkdtemp()
    members = {}
    for official_name, our_path in _MEMBERS.items():
        dst = os.path.join(work, official_name)
        _graft_metadata(official.read(official_name), our_path, dst)
        members[official_name] = dst

    with zipfile.ZipFile(output_task, "w", zipfile.ZIP_STORED) as bundle:
        for member, path in members.items():
            bundle.write(path, member)
    shutil.rmtree(work)
    return output_task


if __name__ == "__main__":
    print("built", build())
