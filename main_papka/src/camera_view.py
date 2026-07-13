import os
import numpy as np
from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPainter, QImage, QPen, QColor, QPolygonF
from PyQt5.QtCore import Qt, QPointF

from camera_math import OrbitCamera, world_to_screen


class CameraView(QWidget):

    def __init__(self, image_path=None, projection_opacity=0.35, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 300)
        self.image_path = image_path
        self.projection_opacity = self._clamp_opacity(projection_opacity)
        self.projection_color = QColor(0, 220, 70)
        self.outline_color = QColor(0, 0, 0)
        self.projection_width = 5
        self.outline_width = 5


        self.image = None
        self.image_width = 800
        self.image_height = 600

        self.segments = []

        self.camera = OrbitCamera()

        self._load_or_generate_image()

    def _load_or_generate_image(self):
        img_path = self.image_path
        if img_path and os.path.exists(img_path):
            self.image = QImage(img_path)
            if self.image.isNull():
                print("Не удалось загрузить изображение, использую заглушку.")
                self._generate_dummy_image()
        else:
            print("calibration_photo.jpg не найден, генерирую заглушку...")
            self._generate_dummy_image()

        self.image_width = self.image.width()
        self.image_height = self.image.height()
        self.resize(self.image_width, self.image_height)

    def _generate_dummy_image(self):
        self.image = QImage(800, 600, QImage.Format_RGB32)
        self.image.fill(Qt.white)

        from PyQt5.QtGui import QPainter
        painter = QPainter(self.image)
        painter.setPen(QPen(QColor(200, 200, 200), 1))
        for x in range(0, 800, 50):
            painter.drawLine(x, 0, x, 600)
        for y in range(0, 600, 50):
            painter.drawLine(0, y, 800, y)

        painter.setPen(QPen(QColor(0, 0, 255), 3))
        painter.setBrush(QColor(0, 0, 255, 50))
        painter.drawRect(300, 200, 200, 200)

        painter.drawText(350, 300, "CALIBRATION PHOTO")
        painter.end()

    def load_layers(self, layers):
        self.segments = []
        for layer in layers:
            for segment in layer:
                if len(segment) >= 2:
                    self.segments.append(segment.astype(np.float32))
        self.update()

    def set_camera_state(self, state: dict):
        self.camera.set_state(state)
        self.update()

    def set_projection_opacity(self, opacity: float):
        self.projection_opacity = self._clamp_opacity(opacity)
        self.update()

    @staticmethod
    def _clamp_opacity(opacity: float) -> float:
        return max(0.0, min(1.0, float(opacity)))

    def _get_eye_position(self) -> np.ndarray:
        return self.camera.eye

    def _view_projection(self):
        aspect = self.image_width / self.image_height
        return (
            self.camera.view_matrix(),
            self.camera.projection_matrix(aspect),
            (0, 0, self.image_width, self.image_height),
        )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()
        scaled_image = self.image.scaled(rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)

        x_offset = (rect.width() - scaled_image.width()) / 2
        y_offset = (rect.height() - scaled_image.height()) / 2
        painter.drawImage(int(x_offset), int(y_offset), scaled_image)

        if not self.segments:
            painter.end()
            return

        view, proj, viewport = self._view_projection()

        scale_x = scaled_image.width() / self.image_width
        scale_y = scaled_image.height() / self.image_height

        outline_alpha = int(220 * self.projection_opacity)
        projection_alpha = int(255 * self.projection_opacity)

        outline_color = QColor(self.outline_color)
        outline_color.setAlpha(outline_alpha)
        outline_pen = QPen(outline_color, self.outline_width)
        outline_pen.setJoinStyle(Qt.RoundJoin)
        outline_pen.setCapStyle(Qt.RoundCap)

        projection_color = QColor(self.projection_color)
        projection_color.setAlpha(projection_alpha)
        projection_pen = QPen(projection_color, self.projection_width)
        projection_pen.setJoinStyle(Qt.RoundJoin)
        projection_pen.setCapStyle(Qt.RoundCap)

        for segment in self.segments:
            screen_pts = world_to_screen(segment, view, proj, viewport)

            valid_mask = screen_pts[:, 2] >= 0
            valid_pts = screen_pts[valid_mask]

            if len(valid_pts) < 2:
                continue

            qt_points = [
                QPointF(
                    float(pt[0] * scale_x + x_offset),
                    float((self.image_height - pt[1]) * scale_y + y_offset)
                )
                for pt in valid_pts
            ]

            painter.setPen(outline_pen)
            painter.drawPolyline(QPolygonF(qt_points))
            painter.setPen(projection_pen)
            painter.drawPolyline(QPolygonF(qt_points))

        painter.end()

    def get_projected_bbox(self, margin=30):
        if not self.segments:
            return None

        view, proj, viewport = self._view_projection()
        all_x = []
        all_y = []

        for segment in self.segments:
            screen_pts = world_to_screen(segment, view, proj, viewport)
            valid_pts = screen_pts[screen_pts[:, 2] >= 0]

            if len(valid_pts) == 0:
                continue

            all_x.extend(valid_pts[:, 0])
            all_y.extend(valid_pts[:, 1])

        if not all_x:
            return None

        xmin = max(0, int(min(all_x)) - margin)
        ymin = max(0, int(min(all_y)) - margin)
        xmax = min(self.image_width - 1, int(max(all_x)) + margin)
        ymax = min(self.image_height - 1, int(max(all_y)) + margin)
        return xmin, ymin, xmax, ymax

    def get_virtual_model_mask(self, thickness=4, fill=False):
        """Return a binary mask of the projected virtual model in image coordinates."""
        mask = np.zeros((self.image_height, self.image_width), dtype=np.uint8)
        if not self.segments:
            return mask

        view, proj, viewport = self._view_projection()

        canvas = QImage(self.image_width, self.image_height, QImage.Format_Grayscale8)
        canvas.fill(0)

        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(255, 255, 255), max(1, int(thickness))))

        for segment in self.segments:
            screen_pts = world_to_screen(segment, view, proj, viewport)
            valid_pts = screen_pts[screen_pts[:, 2] >= 0]
            if len(valid_pts) < 2:
                continue

            points = [
                QPointF(float(pt[0]), float(self.image_height - pt[1]))
                for pt in valid_pts
            ]
            painter.drawPolyline(QPolygonF(points))

            if fill and len(points) >= 3:
                painter.setBrush(QColor(255, 255, 255))
                painter.drawPolygon(QPolygonF(points))

        painter.end()

        ptr = canvas.bits()
        ptr.setsize(self.image_width * self.image_height)
        mask = np.frombuffer(ptr, dtype=np.uint8).reshape((self.image_height, self.image_width))
        return (mask > 0).astype(np.uint8)

    def get_virtual_model_search_bbox(self, margin=20, thickness=4):
        """Return bbox from the virtual model mask for MobileSAM search area."""
        mask = self.get_virtual_model_mask(thickness=thickness)
        ys, xs = np.where(mask > 0)
        if len(xs) == 0:
            return None

        xmin = max(0, int(xs.min()) - margin)
        ymin = max(0, int(ys.min()) - margin)
        xmax = min(self.image_width - 1, int(xs.max()) + margin)
        ymax = min(self.image_height - 1, int(ys.max()) + margin)
        return xmin, ymin, xmax, ymax
