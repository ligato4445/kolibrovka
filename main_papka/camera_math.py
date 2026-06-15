"""
camera_math.py
Математика камеры: матрицы преобразований, проекция,
перевод мировых координат в экранные.

Все матрицы имеют размер 4x4 (однородные координаты).
Точки представляются как np.ndarray shape (N, 3) или (3,).
"""

import numpy as np


# ============================================================
# Базовые матрицы преобразований
# ============================================================

def translation_matrix(tx: float, ty: float, tz: float) -> np.ndarray:
    """Матрица переноса 4x4."""
    m = np.eye(4, dtype=np.float32)
    m[0, 3] = tx
    m[1, 3] = ty
    m[2, 3] = tz
    return m


def scale_matrix(sx: float, sy: float, sz: float) -> np.ndarray:
    """Матрица масштабирования 4x4."""
    m = np.eye(4, dtype=np.float32)
    m[0, 0] = sx
    m[1, 1] = sy
    m[2, 2] = sz
    return m


def rotation_matrix_x(angle_rad: float) -> np.ndarray:
    """Поворот вокруг оси X (в радианах)."""
    c, s = np.cos(angle_rad), np.sin(angle_rad)
    return np.array([
        [1, 0, 0, 0],
        [0, c, -s, 0],
        [0, s, c, 0],
        [0, 0, 0, 1],
    ], dtype=np.float32)


def rotation_matrix_y(angle_rad: float) -> np.ndarray:
    """Поворот вокруг оси Y (в радианах)."""
    c, s = np.cos(angle_rad), np.sin(angle_rad)
    return np.array([
        [c, 0, s, 0],
        [0, 1, 0, 0],
        [-s, 0, c, 0],
        [0, 0, 0, 1],
    ], dtype=np.float32)


def rotation_matrix_z(angle_rad: float) -> np.ndarray:
    """Поворот вокруг оси Z (в радианах)."""
    c, s = np.cos(angle_rad), np.sin(angle_rad)
    return np.array([
        [c, -s, 0, 0],
        [s, c, 0, 0],
        [0, 0, 1, 0],
        [0, 0, 0, 1],
    ], dtype=np.float32)


# ============================================================
# Камера
# ============================================================

def look_at(eye: np.ndarray, target: np.ndarray, up: np.ndarray) -> np.ndarray:
    """
    Создаёт view-матрицу 4x4 (аналог gluLookAt).

    eye    — позиция камеры (3,)
    target — точка, куда смотрит камера (3,)
    up     — вектор "вверх" (3,)

    Возвращает матрицу, которая переводит мир в пространство камеры.
    """
    eye = np.asarray(eye, dtype=np.float32)
    target = np.asarray(target, dtype=np.float32)
    up = np.asarray(up, dtype=np.float32)

    # Вектор "вперёд" от камеры к цели (ось -Z камеры)
    f = target - eye
    f = f / np.linalg.norm(f)

    # Правая ось (X камеры)
    s = np.cross(f, up)
    s_norm = np.linalg.norm(s)
    if s_norm < 1e-6:
        # f и up параллельны — выберем произвольный up
        s = np.cross(f, np.array([0.0, 1.0, 0.0]))
        s_norm = np.linalg.norm(s)
    s = s / s_norm

    # Истинный up (Y камеры)
    u = np.cross(s, f)

    m = np.eye(4, dtype=np.float32)
    m[0, 0:3] = s
    m[1, 0:3] = u
    m[2, 0:3] = -f
    m[0, 3] = -np.dot(s, eye)
    m[1, 3] = -np.dot(u, eye)
    m[2, 3] = np.dot(f, eye)
    return m


def perspective_projection(fov_deg: float, aspect: float,
                           near: float, far: float) -> np.ndarray:
    """
    Матрица перспективной проекции 4x4 (аналог gluPerspective).

    fov_deg — вертикальный угол обзора в градусах
    aspect  — отношение ширины к высоте (width / height)
    near    — ближняя плоскость отсечения (> 0)
    far     — дальняя плоскость отсечения
    """
    f = 1.0 / np.tan(np.deg2rad(fov_deg) / 2.0)
    m = np.zeros((4, 4), dtype=np.float32)
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = (2.0 * far * near) / (near - far)
    m[3, 2] = -1.0
    return m


# ============================================================
# Преобразования координат
# ============================================================

def world_to_clip(points: np.ndarray,
                  view: np.ndarray,
                  proj: np.ndarray) -> np.ndarray:
    """
    Переводит мировые координаты в однородные координаты отсечения (clip space).

    points — shape (N, 3)
    Возвращает shape (N, 4) — однородные координаты после MVP.
    """
    points = np.asarray(points, dtype=np.float32)
    n = points.shape[0]

    # В однородные координаты: [x, y, z, 1]
    p4 = np.hstack([points, np.ones((n, 1), dtype=np.float32)])

    # View → Camera space
    p4 = p4 @ view.T
    # Proj → Clip space
    p4 = p4 @ proj.T
    return p4


def world_to_screen(points: np.ndarray,
                    view: np.ndarray,
                    proj: np.ndarray,
                    viewport: tuple) -> np.ndarray:
    """
    Переводит мировые координаты в экранные пиксели.
    """
    vx, vy, vw, vh = viewport
    clip = world_to_clip(points, view, proj)

    # W-компонента после умножения на матрицы.
    # В OpenGL точки ПЕРЕД камерой имеют w > 0.
    w = clip[:, 3]
    ndc = np.zeros_like(clip[:, :3])

    # Точки строго перед камерой
    in_front = w > 1e-6
    ndc[in_front] = clip[in_front, :3] / w[in_front, np.newaxis]

    # NDC → экранные координаты
    screen = np.zeros((points.shape[0], 3), dtype=np.float32)
    screen[in_front, 0] = vx + (ndc[in_front, 0] * 0.5 + 0.5) * vw
    screen[in_front, 1] = vy + (ndc[in_front, 1] * 0.5 + 0.5) * vh
    screen[in_front, 2] = ndc[in_front, 2] * 0.5 + 0.5  # depth в [0, 1]

    # Точки за камерой (w <= 0) помечаем как невалидные (depth = -1)
    screen[~in_front, 2] = -1.0
    return screen


def apply_transform(points: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """
    Применяет матрицу 4x4 к массиву точек (N, 3).
    Возвращает (N, 3).
    """
    points = np.asarray(points, dtype=np.float32)
    n = points.shape[0]
    p4 = np.hstack([points, np.ones((n, 1), dtype=np.float32)])
    p4 = p4 @ matrix.T
    return p4[:, :3]


# ============================================================
# Орбитальная камера (для scene_view.py)
# ============================================================

class OrbitCamera:
    """
    Орбитальная камера для 3D-печати.
    Система координат: Z — вверх (как в G-code).

    - azimuth: вращение в плоскости XY вокруг оси Z
    - elevation: угол над плоскостью XY (0 = горизонт, 90° = строго сверху)
    """

    def __init__(self,
                 target=(0.0, 0.0, 0.0),
                 distance: float = 300.0,
                 azimuth: float = np.deg2rad(45.0),
                 elevation: float = np.deg2rad(30.0),
                 fov: float = 45.0,
                 near: float = 0.1,
                 far: float = 5000.0):
        self.target = np.array(target, dtype=np.float32)
        self.distance = float(distance)
        self.azimuth = float(azimuth)
        self.elevation = float(elevation)
        self.fov = float(fov)
        self.near = float(near)
        self.far = float(far)
        # Z — вверх (стандарт 3D-печати)
        self.up = np.array([0.0, 0.0, 1.0], dtype=np.float32)

    @property
    def eye(self) -> np.ndarray:
        """
        Позиция камеры в сферических координатах (Z-up).
        - azimuth вращает в плоскости XY
        - elevation поднимает над плоскостью XY
        """
        ce = np.cos(self.elevation)
        return self.target + self.distance * np.array([
            ce * np.sin(self.azimuth),  # X
            ce * np.cos(self.azimuth),  # Y
            np.sin(self.elevation),  # Z — вверх
        ], dtype=np.float32)

    def view_matrix(self) -> np.ndarray:
        return look_at(self.eye, self.target, self.up)

    def projection_matrix(self, aspect: float) -> np.ndarray:
        return perspective_projection(self.fov, aspect, self.near, self.far)

    def rotate(self, dx: float, dy: float, sensitivity: float = 0.005):
        """
        Вращение камеры.
        dx (влево/вправо) → azimuth → вращение вокруг оси Z
        dy (вверх/вниз) → elevation → наклон над плоскостью XY
        """
        self.azimuth += dx * sensitivity
        self.elevation += dy * sensitivity
        # Ограничим elevation, чтобы не перевернуть камеру
        lim = np.deg2rad(89.0)
        self.elevation = max(-lim, min(lim, self.elevation))

    def zoom(self, delta: float, factor: float = 0.1):
        self.distance *= (1.0 - delta * factor)
        self.distance = max(1.0, self.distance)

    def pan(self, dx: float, dy: float, sensitivity: float = 0.5):
        """
        Панорамирование: сдвигаем target в плоскости, перпендикулярной лучу зрения.
        """
        forward = self.target - self.eye
        forward = forward / (np.linalg.norm(forward) + 1e-8)

        # "Вправо" — перпендикулярно forward и up (Z)
        right = np.cross(forward, self.up)
        right_norm = np.linalg.norm(right)
        if right_norm > 1e-6:
            right /= right_norm
        else:
            right = np.array([1.0, 0.0, 0.0], dtype=np.float32)

        # "Вверх" камеры — перпендикулярно right и forward
        cam_up = np.cross(right, forward)

        scale = self.distance * sensitivity * 0.001
        self.target += (-right * dx + cam_up * dy) * scale