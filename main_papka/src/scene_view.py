"""
Оптимизированный 3D вьювер G-code.
Решение 2: конвертация всех LINE_STRIP в GL_LINES + один VBO.
"""

import numpy as np
from PyQt5.QtWidgets import QOpenGLWidget
from PyQt5.QtCore import Qt, QTimer
from OpenGL.GL import *
from OpenGL.GLU import *

from camera_math import OrbitCamera


class SceneView(QOpenGLWidget):

    def __init__(self, parent=None, on_camera_changed=None):
        super().__init__(parent)
        self.setMinimumSize(800, 600)
        self.setWindowTitle("G-code 3D Viewer")
        self.on_camera_changed = on_camera_changed

        self.camera = OrbitCamera()

        # Исходные сегменты (LINE_STRIP)
        self.segments = []

        # VBO для линий модели (GL_LINES)
        self.vbo = None
        self.line_vertex_count = 0  # количество вершин (точек * 2 на линию)

        # VBO для сетки (кэшируется один раз)
        self.grid_vbo = None
        self.grid_vbo_axes = None
        self.grid_point_count = 0
        self.axes_point_count = 0

        # LOD: диапазон отображаемых слоёв
        self.visible_layer_range = None  # (min_z, max_z) или None = все

        # Цвет отрисовки
        self.line_color = (0.0, 1.0, 1.0)  # cyan
        self.line_width = 1.5

        # Взаимодействие с мышью
        self._last_mouse_pos = None
        self._mouse_button = None

    # ------------------------------------------------------------------
    # Загрузка данных
    # ------------------------------------------------------------------

    def load_layers(self, layers, visible_layer_range=None):
        """
        Загружает слои из парсера.

        layers: список слоёв, каждый слой — список сегментов (np.ndarray Nx3)
        visible_layer_range: (min_z, max_z) — показать только слои в диапазоне
        """
        self.visible_layer_range = visible_layer_range
        self.segments = []

        for layer in layers:
            if len(layer) == 0:
                continue

            # Определяем Z слоя по первой точке первого сегмента
            layer_z = layer[0][0, 2] if layer[0].shape[1] >= 3 else 0.0

            # Фильтрация по диапазону (LOD)
            if self.visible_layer_range is not None:
                min_z, max_z = self.visible_layer_range
                if layer_z < min_z or layer_z > max_z:
                    continue

            for segment in layer:
                if len(segment) >= 2:
                    self.segments.append(segment.astype(np.float32))

        if self.segments:
            all_pts = np.vstack(self.segments)
            min_pt = np.min(all_pts, axis=0)
            max_pt = np.max(all_pts, axis=0)
            center = (min_pt + max_pt) / 2.0
            size = np.linalg.norm(max_pt - min_pt)

            self.camera.target = center
            self.camera.distance = max(size * 1.5, 10.0)
            self._notify_camera_changed()

            # Создаём VBO после того как виджет инициализирован
            QTimer.singleShot(0, self._create_vbo)

    def set_visible_layers(self, min_z=None, max_z=None):
        """Обновить диапазон видимых слоёв без полной перезагрузки."""
        if min_z is not None or max_z is not None:
            self.visible_layer_range = (
                min_z if min_z is not None else -1e9,
                max_z if max_z is not None else 1e9
            )
        else:
            self.visible_layer_range = None
        self._create_vbo()

    # ------------------------------------------------------------------
    # Создание VBO (конвертация LINE_STRIP → GL_LINES)
    # ------------------------------------------------------------------

    def _create_vbo(self):
        """Конвертирует все сегменты в GL_LINES и создаёт единый VBO."""
        if not self.segments:
            if self.vbo is not None:
                glDeleteBuffers(1, [self.vbo])
                self.vbo = None
            self.line_vertex_count = 0
            self.update()
            return

        # Конвертация: каждый сегмент [P0, P1, P2, ..., Pn]
        # превращается в пары: (P0,P1), (P1,P2), ..., (Pn-1,Pn)
        line_pairs = []
        for seg in self.segments:
            # seg[:-1] — все точки кроме последней (начало линии)
            # seg[1:]  — все точки кроме первой  (конец линии)
            starts = seg[:-1]
            ends = seg[1:]
            # Чередуем: [start0, end0, start1, end1, ...]
            interleaved = np.empty((starts.shape[0] * 2, starts.shape[1]),
                                   dtype=np.float32)
            interleaved[0::2] = starts
            interleaved[1::2] = ends
            line_pairs.append(interleaved)

        if not line_pairs:
            return

        line_data = np.vstack(line_pairs)
        self.line_vertex_count = line_data.shape[0]

        if self.vbo is not None:
            glDeleteBuffers(1, [self.vbo])

        self.vbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        glBufferData(GL_ARRAY_BUFFER, line_data.nbytes, line_data, GL_STATIC_DRAW)
        glBindBuffer(GL_ARRAY_BUFFER, 0)

        print(f"VBO создан: {self.line_vertex_count} вершин "
              f"({self.line_vertex_count // 2} линий) из {len(self.segments)} сегментов")
        self.update()

    # ------------------------------------------------------------------
    # OpenGL инициализация
    # ------------------------------------------------------------------

    def initializeGL(self):
        glClearColor(0.1, 0.1, 0.12, 1.0)
        glEnable(GL_DEPTH_TEST)

        # ВАЖНО: отключаем сглаживание линий — главный тормоз
        # glEnable(GL_LINE_SMOOTH)  ← было, теперь выключено
        # glHint(GL_LINE_SMOOTH_HINT, GL_NICEST)

        # Создаём кэшированные VBO для сетки и осей
        self._create_grid_vbo()
        self._create_axes_vbo()

    def resizeGL(self, w, h):
        if h == 0:
            h = 1
        glViewport(0, 0, w, h)

    # ------------------------------------------------------------------
    # Кэшированные VBO для сетки и осей
    # ------------------------------------------------------------------

    def _create_grid_vbo(self):
        """Создаёт VBO для сетки один раз."""
        size = 200.0
        step = 20.0
        lines = []
        for i in np.arange(-size, size + step, step):
            lines.extend([i, -size, 0.0, i, size, 0.0])
            lines.extend([-size, i, 0.0, size, i, 0.0])

        grid_data = np.array(lines, dtype=np.float32)
        self.grid_point_count = len(grid_data) // 3

        if self.grid_vbo is not None:
            glDeleteBuffers(1, [self.grid_vbo])

        self.grid_vbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.grid_vbo)
        glBufferData(GL_ARRAY_BUFFER, grid_data.nbytes, grid_data, GL_STATIC_DRAW)
        glBindBuffer(GL_ARRAY_BUFFER, 0)

    def _create_axes_vbo(self):
        """Создаёт VBO для осей координат."""
        axis_len = 50.0
        axes_data = np.array([
            # X — красный
            0.0, 0.0, 0.0, 1.0, 0.0, 0.0,
            axis_len, 0.0, 0.0, 1.0, 0.0, 0.0,
            # Y — зелёный
            0.0, 0.0, 0.0, 0.0, 1.0, 0.0,
            0.0, axis_len, 0.0, 0.0, 1.0, 0.0,
            # Z — синий
            0.0, 0.0, 0.0, 0.0, 0.0, 1.0,
            0.0, 0.0, axis_len, 0.0, 0.0, 1.0,
        ], dtype=np.float32)

        self.axes_point_count = len(axes_data) // 6  # 6 вершин (3 линии * 2 точки)

        if self.grid_vbo_axes is not None:
            glDeleteBuffers(1, [self.grid_vbo_axes])

        self.grid_vbo_axes = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.grid_vbo_axes)
        glBufferData(GL_ARRAY_BUFFER, axes_data.nbytes, axes_data, GL_STATIC_DRAW)
        glBindBuffer(GL_ARRAY_BUFFER, 0)

    # ------------------------------------------------------------------
    # Рендеринг
    # ------------------------------------------------------------------

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        w, h = self.width(), self.height()
        aspect = w / h if h > 0 else 1.0

        # Настройка проекции
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        proj = self.camera.projection_matrix(aspect)
        glMultMatrixf(proj.T.flatten())

        # Настройка вида
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        view = self.camera.view_matrix()
        glMultMatrixf(view.T.flatten())

        # Рисуем вспомогательные элементы
        self._draw_axes()
        self._draw_grid()

        # Рисуем модель
        self._draw_gcode()

    def _draw_axes(self):
        """Рисует оси координат из кэшированного VBO."""
        if self.grid_vbo_axes is None:
            return

        glLineWidth(2.0)
        glBindBuffer(GL_ARRAY_BUFFER, self.grid_vbo_axes)
        glEnableClientState(GL_VERTEX_ARRAY)
        glEnableClientState(GL_COLOR_ARRAY)
        glVertexPointer(3, GL_FLOAT, 24, None)      # stride = 6 * 4 = 24 байта
        glColorPointer(3, GL_FLOAT, 24, None)       # цвет сразу после позиции
        glDrawArrays(GL_LINES, 0, self.axes_point_count)
        glDisableClientState(GL_COLOR_ARRAY)
        glDisableClientState(GL_VERTEX_ARRAY)
        glBindBuffer(GL_ARRAY_BUFFER, 0)

    def _draw_grid(self):
        """Рисует сетку из кэшированного VBO."""
        if self.grid_vbo is None:
            return

        glColor3f(0.25, 0.25, 0.25)
        glLineWidth(1.0)

        glBindBuffer(GL_ARRAY_BUFFER, self.grid_vbo)
        glEnableClientState(GL_VERTEX_ARRAY)
        glVertexPointer(3, GL_FLOAT, 0, None)
        glDrawArrays(GL_LINES, 0, self.grid_point_count)
        glDisableClientState(GL_VERTEX_ARRAY)
        glBindBuffer(GL_ARRAY_BUFFER, 0)

    def _draw_gcode(self):
        """
        Рендерит модель. ОДИН вызов glDrawArrays для всех линий.
        """
        if self.vbo is None or self.line_vertex_count == 0:
            return

        r, g, b = self.line_color
        glColor3f(r, g, b)
        glLineWidth(self.line_width)

        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        glEnableClientState(GL_VERTEX_ARRAY)
        glVertexPointer(3, GL_FLOAT, 0, None)

        # ГЛАВНАЯ ОПТИМИЗАЦИЯ: один draw call вместо тысяч
        glDrawArrays(GL_LINES, 0, self.line_vertex_count)

        glDisableClientState(GL_VERTEX_ARRAY)
        glBindBuffer(GL_ARRAY_BUFFER, 0)

    # ------------------------------------------------------------------
    # Обработка мыши
    # ------------------------------------------------------------------

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
        elif self._mouse_button == Qt.MiddleButton:
            self.camera.pan(dx, dy)

        self.update()
        self._notify_camera_changed()

    def mouseReleaseEvent(self, event):
        self._last_mouse_pos = None
        self._mouse_button = None

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        self.camera.zoom(delta / 500.0)
        self.update()
        self._notify_camera_changed()

    # ------------------------------------------------------------------
    # API для получения/установки состояния камеры
    # ------------------------------------------------------------------

    def get_view_matrix(self) -> np.ndarray:
        return self.camera.view_matrix()

    def get_projection_matrix(self) -> np.ndarray:
        aspect = self.width() / self.height() if self.height() > 0 else 1.0
        return self.camera.projection_matrix(aspect)

    def get_camera_state(self) -> dict:
        return self.camera.get_state()

    def set_camera_state(self, state: dict):
        self.camera.set_state(state)
        self.update()

    def _notify_camera_changed(self):
        if self.on_camera_changed is not None:
            self.on_camera_changed()