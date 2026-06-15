"""
scene_view.py
Интерактивное 3D-окно на PyQt5 + PyOpenGL с оптимизацией VBO.
"""

import numpy as np
from PyQt5.QtWidgets import QOpenGLWidget
from PyQt5.QtCore import Qt
from OpenGL.GL import *
from OpenGL.GLU import *

from camera_math import OrbitCamera


class SceneView(QOpenGLWidget):
    """
    3D-окно для просмотра G-code модели с оптимизацией VBO.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(800, 600)
        self.setWindowTitle("G-code 3D Viewer")

        self.camera = OrbitCamera(
            target=(0.0, 0.0, 0.0),
            distance=300.0,
            azimuth=45.0,
            elevation=30.0,
            fov=45.0,
            near=0.1,
            far=5000.0
        )

        # Данные для отрисовки
        self.segments = []  # List[np.ndarray] shape (N, 3)

        # VBO (Vertex Buffer Object)
        self.vbo = None
        self.segment_counts = []  # Количество точек в каждом сегменте
        self.segment_offsets = []  # Смещение в VBO для каждого сегмента

        # Для управления мышью
        self._last_mouse_pos = None
        self._mouse_button = None

    def load_layers(self, layers):
        """
        Загружает слои из парсера. VBO создаётся отложено,
        когда OpenGL контекст уже готов.
        """
        self.segments = []
        for layer in layers:
            for segment in layer:
                if len(segment) >= 2:
                    self.segments.append(segment.astype(np.float32))

        # Автоцентрирование камеры
        if self.segments:
            all_pts = np.vstack(self.segments)
            min_pt = np.min(all_pts, axis=0)
            max_pt = np.max(all_pts, axis=0)
            center = (min_pt + max_pt) / 2.0
            size = np.linalg.norm(max_pt - min_pt)

            self.camera.target = center
            self.camera.distance = max(size * 1.5, 10.0)

            # ОТЛАГАЕМ создание VBO до момента, когда контекст OpenGL будет создан
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(0, self._create_vbo)

    def _create_vbo(self):
        """Создаёт VBO из всех сегментов (вызывается только при активном контексте)."""
        if not self.segments:
            return

        # Если VBO уже был создан ранее, удаляем его из видеопамяati
        if self.vbo is not None:
            glDeleteBuffers(1, [self.vbo])

        # Объединяем все сегменты в один плоский массив
        all_points = np.vstack(self.segments)

        # Создаём и заполняем VBO
        self.vbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        glBufferData(GL_ARRAY_BUFFER, all_points.nbytes, all_points, GL_STATIC_DRAW)
        glBindBuffer(GL_ARRAY_BUFFER, 0)

        # Запоминаем размеры и смещения для каждого сегмента
        self.segment_counts = [len(seg) for seg in self.segments]
        offset = 0
        self.segment_offsets = []
        for count in self.segment_counts:
            self.segment_offsets.append(offset)
            offset += count

        print(f"✅ VBO создан: {len(self.segments)} сегментов, {len(all_points)} точек")
        self.update()  # Запрашиваем перерисовку

    def initializeGL(self):
        """Инициализация OpenGL."""
        glClearColor(0.0, 0.0, 0.0, 1.0)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LINE_SMOOTH)
        glHint(GL_LINE_SMOOTH_HINT, GL_NICEST)

    def resizeGL(self, w, h):
        """Изменение размера окна."""
        if h == 0:
            h = 1
        glViewport(0, 0, w, h)

    def paintGL(self):
        """Отрисовка кадра."""
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        w, h = self.width(), self.height()
        aspect = w / h if h > 0 else 1.0

        # Матрица проекции
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        proj = self.camera.projection_matrix(aspect)
        glMultMatrixf(proj.T.flatten())

        # Матрица вида
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        view = self.camera.view_matrix()
        glMultMatrixf(view.T.flatten())

        # Рисуем оси и сетку
        self._draw_axes()
        self._draw_grid()

        # Рисуем G-code из VBO
        self._draw_gcode_vbo()

    def _draw_axes(self):
        """Рисуем оси координат."""
        glLineWidth(2.0)
        glBegin(GL_LINES)

        glColor3f(1.0, 0.0, 0.0)
        glVertex3f(0.0, 0.0, 0.0)
        glVertex3f(50.0, 0.0, 0.0)

        glColor3f(0.0, 1.0, 0.0)
        glVertex3f(0.0, 0.0, 0.0)
        glVertex3f(0.0, 50.0, 0.0)

        glColor3f(0.0, 0.0, 1.0)
        glVertex3f(0.0, 0.0, 0.0)
        glVertex3f(0.0, 0.0, 50.0)

        glEnd()

    def _draw_grid(self):
        """Рисуем сетку на плоскости XY."""
        glColor3f(0.2, 0.2, 0.2)
        glLineWidth(1.0)
        glBegin(GL_LINES)

        size = 200.0
        step = 20.0
        for i in np.arange(-size, size + step, step):
            glVertex3f(i, -size, 0.0)
            glVertex3f(i, size, 0.0)
            glVertex3f(-size, i, 0.0)
            glVertex3f(size, i, 0.0)

        glEnd()

    def _draw_gcode_vbo(self):
        """Рисуем G-code из VBO (оптимизированная версия)."""
        if self.vbo is None or not self.segments:
            return

        glColor3f(0.0, 1.0, 1.0)
        glLineWidth(5)

        # Привязываем VBO
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        glEnableClientState(GL_VERTEX_ARRAY)
        glVertexPointer(3, GL_FLOAT, 0, None)

        # Рисуем каждый сегмент отдельным вызовом
        # (можно оптимизировать дальше через glMultiDrawArrays, но это уже даст 50-100x)
        for i, count in enumerate(self.segment_counts):
            offset = self.segment_offsets[i]
            glDrawArrays(GL_LINE_STRIP, offset, count)

        # Отключаем
        glDisableClientState(GL_VERTEX_ARRAY)
        glBindBuffer(GL_ARRAY_BUFFER, 0)

    # ============================================================
    # Управление мышью
    # ============================================================

    def mousePressEvent(self, event):
        self._last_mouse_pos = event.pos()
        self._mouse_button = event.button()

    def mouseMoveEvent(self, event):
        if self._last_mouse_pos is None:
            return

        dx = event.x() - self._last_mouse_pos.x()
        dy = event.y() - self._last_mouse_pos.y()
        self._last_mouse_pos = event.pos()

        if self._mouse_button == Qt.LeftButton:
            self.camera.rotate(dx, dy)
        elif self._mouse_button == Qt.RightButton:
            self.camera.pan(dx, dy)

        self.update()

    def mouseReleaseEvent(self, event):
        self._last_mouse_pos = None
        self._mouse_button = None

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        self.camera.zoom(delta / 120.0)
        self.update()

    # ============================================================
    # Доступ к матрицам
    # ============================================================

    def get_view_matrix(self) -> np.ndarray:
        return self.camera.view_matrix()

    def get_projection_matrix(self) -> np.ndarray:
        aspect = self.width() / self.height() if self.height() > 0 else 1.0
        return self.camera.projection_matrix(aspect)

    def get_camera_state(self) -> dict:
        return {
            "target": self.camera.target.tolist(),
            "distance": float(self.camera.distance),
            "azimuth": float(self.camera.azimuth),
            "elevation": float(self.camera.elevation),
            "fov": float(self.camera.fov)
        }

    def set_camera_state(self, state: dict):
        self.camera.target = np.array(state.get("target", [0, 0, 0]))
        self.camera.distance = state.get("distance", 300.0)
        self.camera.azimuth = state.get("azimuth", 45.0)
        self.camera.elevation = state.get("elevation", 30.0)
        self.camera.fov = state.get("fov", 45.0)
        self.update()