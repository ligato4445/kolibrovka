"""
camera_view.py
Окно калибровки: отображает фото детали и накладывает на него
спроецированную 3D-модель G-code.
"""

import numpy as np
import os
from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPainter, QImage, QPen, QColor, QPolygonF
from PyQt5.QtCore import Qt, QPointF

from camera_math import world_to_screen, look_at, perspective_projection


class CameraView(QWidget):
    """
    Виджет для наложения 3D-проекции на 2D-фотографию.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 300)

        self.image = None
        self.image_width = 800
        self.image_height = 600

        # Данные для отрисовки
        self.segments = []  # List[np.ndarray] shape (N, 3)

        # Параметры камеры (по умолчанию)
        self.camera_target = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        self.camera_distance = 300.0
        self.camera_azimuth = np.deg2rad(45.0)
        self.camera_elevation = np.deg2rad(30.0)
        self.camera_fov = 45.0
        self.camera_up = np.array([0.0, 0.0, 1.0], dtype=np.float32)  # Z-up

        self._load_or_generate_image()

    def _load_or_generate_image(self):
        """Загружает calibration_photo.jpg или создаёт заглушку."""
        img_path = "photo/test1.PNG"
        if os.path.exists(img_path):
            self.image = QImage(img_path)
            if self.image.isNull():
                print("⚠️ Не удалось загрузить изображение, использую заглушку.")
                self._generate_dummy_image()
        else:
            print("⚠️ calibration_photo.jpg не найден, генерирую заглушку...")
            self._generate_dummy_image()

        self.image_width = self.image.width()
        self.image_height = self.image.height()
        # Подстраиваем размер виджета под изображение (с максимальными пределами)
        self.resize(self.image_width, self.image_height)

    def _generate_dummy_image(self):
        """Создаёт тестовое изображение с сеткой и 'деталью'."""
        self.image = QImage(800, 600, QImage.Format_RGB32)
        self.image.fill(Qt.white)

        # Рисуем сетку
        from PyQt5.QtGui import QPainter
        painter = QPainter(self.image)
        painter.setPen(QPen(QColor(200, 200, 200), 1))
        for x in range(0, 800, 50):
            painter.drawLine(x, 0, x, 600)
        for y in range(0, 600, 50):
            painter.drawLine(0, y, 800, y)

        # Рисуем "фото" детали (синий квадрат)
        painter.setPen(QPen(QColor(0, 0, 255), 3))
        painter.setBrush(QColor(0, 0, 255, 50))
        painter.drawRect(300, 200, 200, 200)

        painter.drawText(350, 300, "CALIBRATION PHOTO")
        painter.end()

    def load_layers(self, layers):
        """Загружает слои G-code."""
        self.segments = []
        for layer in layers:
            for segment in layer:
                if len(segment) >= 2:
                    self.segments.append(segment.astype(np.float32))
        self.update()

    def set_camera_state(self, state: dict):
        """Обновляет параметры камеры извне (например, из SceneView)."""
        self.camera_target = np.array(state.get("target", [0, 0, 0]), dtype=np.float32)
        self.camera_distance = float(state.get("distance", 300.0))
        self.camera_azimuth = float(state.get("azimuth", np.deg2rad(45.0)))
        self.camera_elevation = float(state.get("elevation", np.deg2rad(30.0)))
        self.camera_fov = float(state.get("fov", 45.0))
        self.update()

    def _get_eye_position(self) -> np.ndarray:
        """Вычисляет позицию камеры (eye) на основе сферических координат."""
        ce = np.cos(self.camera_elevation)
        return self.camera_target + self.camera_distance * np.array([
            ce * np.sin(self.camera_azimuth),
            ce * np.cos(self.camera_azimuth),
            np.sin(self.camera_elevation),
        ], dtype=np.float32)

    def paintEvent(self, event):
        """Отрисовка фото и наложение проекции."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 1. Рисуем фоновое изображение, масштабируя его под размер виджета
        rect = self.rect()
        scaled_image = self.image.scaled(rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)

        # Центрируем изображение в виджете
        x_offset = (rect.width() - scaled_image.width()) / 2
        y_offset = (rect.height() - scaled_image.height()) / 2
        painter.drawImage(int(x_offset), int(y_offset), scaled_image)

        if not self.segments:
            painter.end()
            return

        # 2. Вычисляем матрицы
        eye = self._get_eye_position()
        view = look_at(eye, self.camera_target, self.camera_up)

        # Aspect ratio должен соответствовать изображению!
        aspect = self.image_width / self.image_height
        proj = perspective_projection(self.camera_fov, aspect, 0.1, 5000.0)

        # 3. Проецируем точки
        # ВАЖНО: viewport задаём в координатах ИСХОДНОГО изображения,
        # а не виджета. Масштабирование применим позже.
        viewport = (0, 0, self.image_width, self.image_height)

        # Коэффициенты масштабирования для перехода от координат изображения к координатам виджета
        scale_x = scaled_image.width() / self.image_width
        scale_y = scaled_image.height() / self.image_height

        # 4. Рисуем линии
        pen = QPen(QColor(0, 200, 0), 3)  # Ярко-зелёный для контраста с фото
        painter.setPen(pen)

        for segment in self.segments:
            # Проецируем весь сегмент сразу
            screen_pts = world_to_screen(segment, view, proj, viewport)

            # Фильтруем точки, которые находятся за камерой (depth < 0)
            valid_mask = screen_pts[:, 2] >= 0
            valid_pts = screen_pts[valid_mask]

            if len(valid_pts) < 2:
                continue

            # Масштабируем координаты под размер виджета и смещаем
            # ИНВЕРТИРУЕМ Y, так как в OpenGL Y вверх, а в Qt Y вниз
            qt_points = [
                QPointF(
                    float(pt[0] * scale_x + x_offset),
                    float((self.image_height - pt[1]) * scale_y + y_offset)  # <-- Инверсия Y
                )
                for pt in valid_pts
            ]

            # Рисуем ломаную линию
            painter.drawPolyline(QPolygonF(qt_points))

        painter.end()