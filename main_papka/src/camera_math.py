import numpy as np

DEFAULT_AZIMUTH_RAD = np.deg2rad(45.0)
DEFAULT_ELEVATION_RAD = np.deg2rad(30.0)
DEFAULT_FOV_DEG = 45.0


def translation_matrix(tx: float, ty: float, tz: float) -> np.ndarray:
    m = np.eye(4, dtype=np.float32)
    m[0, 3] = tx
    m[1, 3] = ty
    m[2, 3] = tz
    return m


def scale_matrix(sx: float, sy: float, sz: float) -> np.ndarray:
    m = np.eye(4, dtype=np.float32)
    m[0, 0] = sx
    m[1, 1] = sy
    m[2, 2] = sz
    return m


def rotation_matrix_x(angle_rad: float) -> np.ndarray:
    c, s = np.cos(angle_rad), np.sin(angle_rad)
    return np.array([
        [1, 0, 0, 0],
        [0, c, -s, 0],
        [0, s, c, 0],
        [0, 0, 0, 1],
    ], dtype=np.float32)


def rotation_matrix_y(angle_rad: float) -> np.ndarray:
    c, s = np.cos(angle_rad), np.sin(angle_rad)
    return np.array([
        [c, 0, s, 0],
        [0, 1, 0, 0],
        [-s, 0, c, 0],
        [0, 0, 0, 1],
    ], dtype=np.float32)


def rotation_matrix_z(angle_rad: float) -> np.ndarray:
    c, s = np.cos(angle_rad), np.sin(angle_rad)
    return np.array([
        [c, -s, 0, 0],
        [s, c, 0, 0],
        [0, 0, 1, 0],
        [0, 0, 0, 1],
    ], dtype=np.float32)


def look_at(eye: np.ndarray, target: np.ndarray, up: np.ndarray) -> np.ndarray:
    eye = np.asarray(eye, dtype=np.float32)
    target = np.asarray(target, dtype=np.float32)
    up = np.asarray(up, dtype=np.float32)

    f = target - eye
    f = f / np.linalg.norm(f)

    s = np.cross(f, up)
    s_norm = np.linalg.norm(s)
    if s_norm < 1e-6:
        s = np.cross(f, np.array([0.0, 1.0, 0.0]))
        s_norm = np.linalg.norm(s)
    s = s / s_norm

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
    f = 1.0 / np.tan(np.deg2rad(fov_deg) / 2.0)
    m = np.zeros((4, 4), dtype=np.float32)
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = (2.0 * far * near) / (near - far)
    m[3, 2] = -1.0
    return m


def world_to_clip(points: np.ndarray,
                  view: np.ndarray,
                  proj: np.ndarray) -> np.ndarray:
    points = np.asarray(points, dtype=np.float32)
    n = points.shape[0]

    p4 = np.hstack([points, np.ones((n, 1), dtype=np.float32)])

    p4 = p4 @ view.T
    p4 = p4 @ proj.T
    return p4


def world_to_screen(points: np.ndarray,
                    view: np.ndarray,
                    proj: np.ndarray,
                    viewport: tuple) -> np.ndarray:
    vx, vy, vw, vh = viewport
    clip = world_to_clip(points, view, proj)

    w = clip[:, 3]
    ndc = np.zeros_like(clip[:, :3])

    in_front = w > 1e-6
    ndc[in_front] = clip[in_front, :3] / w[in_front, np.newaxis]

    screen = np.zeros((points.shape[0], 3), dtype=np.float32)
    screen[in_front, 0] = vx + (ndc[in_front, 0] * 0.5 + 0.5) * vw
    screen[in_front, 1] = vy + (ndc[in_front, 1] * 0.5 + 0.5) * vh
    screen[in_front, 2] = ndc[in_front, 2] * 0.5 + 0.5

    screen[~in_front, 2] = -1.0
    return screen


def apply_transform(points: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    points = np.asarray(points, dtype=np.float32)
    n = points.shape[0]
    p4 = np.hstack([points, np.ones((n, 1), dtype=np.float32)])
    p4 = p4 @ matrix.T
    return p4[:, :3]


class OrbitCamera:

    def __init__(self,
                 target=(0.0, 0.0, 0.0),
                 distance: float = 300.0,
                 azimuth: float = DEFAULT_AZIMUTH_RAD,
                 elevation: float = DEFAULT_ELEVATION_RAD,
                 fov: float = DEFAULT_FOV_DEG,
                 near: float = 0.1,
                 far: float = 5000.0):
        self.target = np.array(target, dtype=np.float32)
        self.distance = float(distance)
        self.azimuth = float(azimuth)
        self.elevation = float(elevation)
        self.fov = float(fov)
        self.near = float(near)
        self.far = float(far)
        self.up = np.array([0.0, 0.0, 1.0], dtype=np.float32)

    @property
    def eye(self) -> np.ndarray:
        ce = np.cos(self.elevation)
        return self.target + self.distance * np.array([
            ce * np.sin(self.azimuth),
            ce * np.cos(self.azimuth),
            np.sin(self.elevation),
        ], dtype=np.float32)

    def view_matrix(self) -> np.ndarray:
        return look_at(self.eye, self.target, self.up)

    def projection_matrix(self, aspect: float) -> np.ndarray:
        return perspective_projection(self.fov, aspect, self.near, self.far)

    def get_state(self) -> dict:
        return {
            "target": self.target.tolist(),
            "distance": float(self.distance),
            "azimuth": float(self.azimuth),
            "elevation": float(self.elevation),
            "fov": float(self.fov)
        }

    def set_state(self, state: dict):
        self.target = np.array(state.get("target", [0, 0, 0]), dtype=np.float32)
        self.distance = float(state.get("distance", 300.0))
        self.azimuth = float(state.get("azimuth", DEFAULT_AZIMUTH_RAD))
        self.elevation = float(state.get("elevation", DEFAULT_ELEVATION_RAD))
        self.fov = float(state.get("fov", DEFAULT_FOV_DEG))

    def rotate(self, dx: float, dy: float, sensitivity: float = 0.005):
        self.azimuth += dx * sensitivity
        self.elevation += dy * sensitivity
        lim = np.deg2rad(89.0)
        self.elevation = max(-lim, min(lim, self.elevation))

    def zoom(self, delta: float, factor: float = 0.1):
        self.distance *= (1.0 - delta * factor)
        self.distance = max(1.0, self.distance)

    def pan(self, dx: float, dy: float, sensitivity: float = 0.5):
        forward = self.target - self.eye
        forward = forward / (np.linalg.norm(forward) + 1e-8)

        right = np.cross(forward, self.up)
        right_norm = np.linalg.norm(right)
        if right_norm > 1e-6:
            right /= right_norm
        else:
            right = np.array([1.0, 0.0, 0.0], dtype=np.float32)

        cam_up = np.cross(right, forward)

        scale = self.distance * sensitivity * 0.001
        self.target += (-right * dx + cam_up * dy) * scale