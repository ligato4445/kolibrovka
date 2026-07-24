from ultralytics import SAM
import cv2
import numpy as np
from pathlib import Path
import argparse

# ==============================
# Настройки
# ==============================
base_dir = Path(__file__).resolve().parent.parent

# Пути к ресурсам
MODEL_PATH = base_dir / "models" / "mobile_sam.pt"
OUTPUT_DIR = base_dir / "data" / "segment_photo_mask"
OUTPUT_IMAGE_PATH = OUTPUT_DIR / "result_cat.jpg"
OUTPUT_MASK_PATH = OUTPUT_DIR / "mask_cat.png"
IMAGE_PATH = base_dir / "data" / "photo" / "cat5.jpg"

WINDOW_NAME = "MobileSAM - ROI and Points"
DISPLAY_WIDTH = 1200
DISPLAY_HEIGHT = 800

# ==============================
# Загрузка изображения
# ==============================
image = cv2.imread(str(IMAGE_PATH))
if image is None:
    raise FileNotFoundError(str(IMAGE_PATH))
image_h, image_w = image.shape[:2]

# ==============================
# Масштаб отображения
# ==============================
scale = min(DISPLAY_WIDTH / image_w, DISPLAY_HEIGHT / image_h)
display_w = int(image_w * scale)
display_h = int(image_h * scale)

def image_to_display(point):
    x, y = point
    return (int(x * scale), int(y * scale))

def display_to_image(x, y):
    return (int(x / scale), int(y / scale))

# ==============================
# Переменные
# ==============================
display_image = image.copy()
roi = None
drawing_roi = False
roi_start = None
current_mouse_pos = (0, 0)
positive_points = []
negative_points = []
model = SAM(str(MODEL_PATH))

# ==============================
# Отрисовка
# ==============================
def redraw():
    global display_image
    display_image = image.copy()
    if roi is not None:
        x1, y1, x2, y2 = roi
        cv2.rectangle(display_image, (x1, y1), (x2, y2), (0,255,255), 2)
    for p in positive_points:
        cv2.circle(display_image, p, 7, (0,255,0), -1)
    for p in negative_points:
        cv2.circle(display_image, p, 7, (0,0,255), -1)
    if drawing_roi and roi_start:
        x0,y0 = roi_start
        x1,y1 = current_mouse_pos
        cv2.rectangle(display_image, (x0,y0), (x1,y1), (255,255,0), 2)

# ==============================
# Mouse callback
# ==============================
def mouse_callback(event,x,y,flags,param):
    global drawing_roi, roi_start, roi, current_mouse_pos
    x,y = display_to_image(x,y)
    current_mouse_pos = (x,y)
    if event == cv2.EVENT_LBUTTONDOWN:
        if roi is None and not drawing_roi:
            drawing_roi = True
            roi_start = (x,y)
        else:
            positive_points.append((x,y))
        redraw()
    elif event == cv2.EVENT_MOUSEMOVE:
        if drawing_roi:
            redraw()
    elif event == cv2.EVENT_LBUTTONUP:
        if drawing_roi:
            x0,y0 = roi_start
            roi = [min(x0,x), min(y0,y), max(x0,x), max(y0,y)]
            drawing_roi = False
            roi_start = None
            redraw()
    elif event == cv2.EVENT_RBUTTONDOWN:
        negative_points.append((x,y))
        redraw()

# ==============================
# Segmentation
# ==============================
def run_segmentation():
    if roi is None:
        raise Exception("Сначала выберите ROI")
    x1,y1,x2,y2 = roi
    bbox = [x1, y1, x2, y2]
    points = positive_points + negative_points
    labels = [1]*len(positive_points) + [0]*len(negative_points)
    results = model.predict(source=image, bboxes=[bbox], points=[points], labels=[labels], conf=0.25, imgsz=1024)
    for r in results:
        annotated = r.plot()
        cv2.imwrite(str(OUTPUT_IMAGE_PATH), annotated)
        if r.masks is not None:
            masks = r.masks.data.cpu().numpy()
            binary_mask = (np.any(masks > 0.5, axis=0).astype(np.uint8) * 255)
            cv2.imwrite(str(OUTPUT_MASK_PATH), binary_mask)
            print("Маска сохранена:", str(OUTPUT_MASK_PATH))
        cv2.imshow(WINDOW_NAME, cv2.resize(annotated, (display_w, display_h)))

# ==============================
# Запуск окна
# ==============================
cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
cv2.resizeWindow(WINDOW_NAME, display_w, display_h)
cv2.setMouseCallback(WINDOW_NAME, mouse_callback)
redraw()
while True:
    shown = cv2.resize(display_image, (display_w, display_h))
    cv2.imshow(WINDOW_NAME, shown)
    key = cv2.waitKey(20) & 0xff
    if key == ord('q'):
        break
    elif key == ord('r'):
        roi = None
        drawing_roi = False
        roi_start = None
        positive_points.clear()
        negative_points.clear()
        redraw()
    elif key == ord('s'):
        try:
            run_segmentation()
        except Exception as e:
            print("Ошибка:", e)
cv2.destroyAllWindows()