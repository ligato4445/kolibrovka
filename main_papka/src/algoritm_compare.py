"""Standalone comparison between the rendered virtual part and the real segmentation mask.

This script uses the existing CameraView renderer from the project:
1. parses G-code into layers;
2. loads camera pose from JSON;
3. renders the virtual projection into a 2D mask;
4. optionally fills the rendered silhouette;
5. compares the virtual mask with the real segmentation mask.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
from PyQt5.QtWidgets import QApplication

from camera_view import CameraView
from gcode_parser import parse_gcode_layers


base_dir = Path(__file__).resolve().parent.parent

OUTPUT_DIR = base_dir / "data" / "segment_photo_mask"
OUTPUT_MASK_PATH = OUTPUT_DIR / "virtual_mask.png"
OUTPUT_OVERLAY_PATH = OUTPUT_DIR / "compare_overlay.png"
REAL_MASK_PATH = OUTPUT_DIR / "mask1.png"

CAMERA_PATH = base_dir / "data" / "calibration_file" / "calibration_golova_7.json"
GCODE_PATH = base_dir / "data" / "gcode" / "golova.gcode"
PHOTO_PATH = base_dir / "data" / "photo" / "cat5.jpg"

# How many parsed layers should be used for the virtual projection.
# Adjust this value if you want to render only a part of the model.
MAX_LAYERS = 200


def load_camera_state(json_path: Path) -> dict:
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_mask(mask_path: Path, target_shape: tuple[int, int] | None = None) -> np.ndarray:
    mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise FileNotFoundError(f"Mask not found: {mask_path}")
    if target_shape is not None and mask.shape[:2] != target_shape:
        mask = cv2.resize(mask, (target_shape[1], target_shape[0]), interpolation=cv2.INTER_NEAREST)
    return (mask > 0).astype(np.uint8)


def fill_mask_holes(mask: np.ndarray) -> np.ndarray:
    """Fill holes inside the projected silhouette."""
    mask_u8 = (mask > 0).astype(np.uint8) * 255
    contours, _ = cv2.findContours(mask_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filled = np.zeros_like(mask_u8)
    if contours:
        cv2.drawContours(filled, contours, -1, 255, thickness=cv2.FILLED)
    return (filled > 0).astype(np.uint8)


def compare_masks(real_mask: np.ndarray, virtual_mask: np.ndarray) -> dict:
    real_bin = (real_mask > 0).astype(np.uint8)
    virt_bin = (virtual_mask > 0).astype(np.uint8)

    intersection = np.logical_and(real_bin, virt_bin).sum()
    union = np.logical_or(real_bin, virt_bin).sum()
    real_area = real_bin.sum()
    virt_area = virt_bin.sum()

    iou = float(intersection / union) if union else 0.0
    coverage_real = float(intersection / real_area) if real_area else 0.0
    coverage_virtual = float(intersection / virt_area) if virt_area else 0.0

    real_contours, _ = cv2.findContours(real_bin * 255, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    virt_contours, _ = cv2.findContours(virt_bin * 255, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    contour_match_shape = None
    if real_contours and virt_contours:
        real_contour = max(real_contours, key=cv2.contourArea)
        virt_contour = max(virt_contours, key=cv2.contourArea)
        contour_match_shape = float(cv2.matchShapes(real_contour, virt_contour, cv2.CONTOURS_MATCH_I1, 0.0))

    return {
        "intersection_area": int(intersection),
        "union_area": int(union),
        "real_area": int(real_area),
        "virtual_area": int(virt_area),
        "iou": iou,
        "coverage_real": coverage_real,
        "coverage_virtual": coverage_virtual,
        "contour_match_shape": contour_match_shape,
    }


def build_virtual_mask() -> np.ndarray:
    layers = parse_gcode_layers(GCODE_PATH, max_layers=MAX_LAYERS)

    camera_view = CameraView(image_path=str(PHOTO_PATH))
    camera_view.load_layers(layers)
    camera_view.set_camera_state(load_camera_state(CAMERA_PATH))

    # This method already uses the project's renderer and projected geometry.
    virtual_mask = camera_view.get_virtual_model_mask(thickness=6, fill=True)

    # If the projection still contains holes, close them for area comparison.
    virtual_mask_u8 = (virtual_mask > 0).astype(np.uint8) * 255
    kernel = np.ones((7, 7), np.uint8)
    closed = cv2.morphologyEx(virtual_mask_u8, cv2.MORPH_CLOSE, kernel, iterations=1)
    closed = fill_mask_holes((closed > 0).astype(np.uint8))
    return closed


def make_overlay(real_mask: np.ndarray, virtual_mask: np.ndarray) -> np.ndarray:
    overlay = np.zeros((real_mask.shape[0], real_mask.shape[1], 3), dtype=np.uint8)
    overlay[real_mask > 0] = (0, 255, 0)
    overlay[virtual_mask > 0] = (0, 0, 255)
    overlap = np.logical_and(real_mask > 0, virtual_mask > 0)
    overlay[overlap] = (0, 255, 255)
    return overlay


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    app = QApplication([])

    real_mask = load_mask(REAL_MASK_PATH)
    virtual_mask = build_virtual_mask()

    if real_mask.shape != virtual_mask.shape:
        virtual_mask = cv2.resize(
            virtual_mask.astype(np.uint8),
            (real_mask.shape[1], real_mask.shape[0]),
            interpolation=cv2.INTER_NEAREST,
        )

    cv2.imwrite(str(OUTPUT_MASK_PATH), virtual_mask * 255)

    metrics = compare_masks(real_mask, virtual_mask)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))

    overlay = make_overlay(real_mask, virtual_mask)
    cv2.imwrite(str(OUTPUT_OVERLAY_PATH), overlay)

    cv2.namedWindow("comparison", cv2.WINDOW_NORMAL)
    cv2.imshow("comparison", overlay)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

    app.quit()


if __name__ == "__main__":
    main()
