#!/usr/bin/env python3
"""Download a small Open Images V7 calibration set.

The quantization example expects a local pickle with this shape:
    {"data": [RGB uint8 image arrays], "target": [[label strings or IDs]]}

This script builds that file from public Open Images validation metadata and
public image objects. The pickle is generated data and is intentionally not
tracked in git.
"""

import argparse
import csv
import pickle
import urllib.request
from pathlib import Path

import cv2
import numpy as np


OPEN_IMAGES_VALIDATION_CSV = (
    "https://storage.googleapis.com/openimages/2018_04/validation/"
    "validation-images-with-rotation.csv"
)
OPEN_IMAGES_IMAGE_BASE_URL = "https://open-images-dataset.s3.amazonaws.com/validation"


def iter_validation_image_ids(limit: int):
    with urllib.request.urlopen(OPEN_IMAGES_VALIDATION_CSV, timeout=60) as response:
        text = response.read().decode("utf-8")

    for row in csv.DictReader(text.splitlines()):
        image_id = row.get("ImageID", "").strip()
        title = row.get("Title", "").strip()
        if image_id:
            yield image_id, title
            limit -= 1
            if limit <= 0:
                return


def download_rgb_image(image_id: str) -> np.ndarray:
    url = f"{OPEN_IMAGES_IMAGE_BASE_URL}/{image_id}.jpg"
    with urllib.request.urlopen(url, timeout=60) as response:
        encoded = np.frombuffer(response.read(), dtype=np.uint8)

    bgr = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if bgr is None:
        raise RuntimeError(f"Failed to decode Open Images image: {image_id}")
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=50, help="Number of validation images to download.")
    parser.add_argument(
        "--output",
        default="openimages_v7_images_and_labels.pkl",
        help="Output pickle path.",
    )
    args = parser.parse_args()

    if args.samples <= 0:
        raise SystemExit("--samples must be positive")

    output = Path(args.output)
    if not output.is_absolute():
        output = Path(__file__).resolve().parent / output
    output.parent.mkdir(parents=True, exist_ok=True)

    print(f"Downloading {args.samples} Open Images calibration images...")
    images = []
    labels = []
    for index, (image_id, title) in enumerate(iter_validation_image_ids(args.samples), start=1):
        print(f"[{index}/{args.samples}] Downloading validation/{image_id}.jpg", flush=True)
        images.append(download_rgb_image(image_id))
        labels.append([title or image_id])

    payload = {"data": images, "target": labels}
    with output.open("wb") as file_obj:
        pickle.dump(payload, file_obj, protocol=pickle.HIGHEST_PROTOCOL)

    print(f"Wrote {len(images)} calibration images to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
