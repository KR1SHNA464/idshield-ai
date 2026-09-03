"""Download the pinned OpenCV Zoo face models and verify their checksums."""

from __future__ import annotations

import argparse
import hashlib
import os
import urllib.request
from pathlib import Path


MODELS = {
    "face_detection_yunet_2023mar.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/refs/heads/main/models/"
        "face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    ),
    "face_recognition_sface_2021dec.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/refs/heads/main/models/"
        "face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as model_file:
        for chunk in iter(lambda: model_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for filename, (url, expected) in MODELS.items():
        target = output / filename
        if target.exists() and sha256(target) == expected:
            print(f"Verified {filename}")
            continue
        temporary = target.with_suffix(target.suffix + ".part")
        print(f"Downloading {filename} from the official OpenCV Zoo release...")
        urllib.request.urlretrieve(url, temporary)
        actual = sha256(temporary)
        if actual != expected:
            temporary.unlink(missing_ok=True)
            raise RuntimeError(
                f"Checksum mismatch for {filename}: expected {expected}, received {actual}"
            )
        os.replace(temporary, target)
        print(f"Verified {filename}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent)
    download(parser.parse_args().output.resolve())
