"""Parse extrusion moves from G-code into printable layer polylines."""

import re
import math
import numpy as np

TRAVEL_THRESHOLD = 0.0

# Типы экструзии для сохранения (включая поддержки)
WANTED_TYPES = {
    "Outer wall",
    "Inner wall",
    "Solid infill",
    "Top solid infill",
    "Internal solid infill",
    "Bottom solid infill",
    "Gap infill",
    "Sparse infill",  # заполнение дна и внутренних слоёв
    "Support",        # поддержки
    "Support interface",
}


def approximate_arc(x0, y0, x1, y1, i, j, ccw, arc_length_threshold=1.0):
    """
    Аппроксимация дуги G2/G3 с адаптивным количеством точек.
    """
    cx = x0 + i
    cy = y0 + j
    r = math.sqrt(i**2 + j**2)
    if r < 1e-6:
        return [[x1, y1]]

    start_angle = math.atan2(y0 - cy, x0 - cx)
    end_angle = math.atan2(y1 - cy, x1 - cx)

    if ccw:
        if end_angle <= start_angle:
            end_angle += 2 * math.pi
    else:
        if end_angle >= start_angle:
            end_angle -= 2 * math.pi

    # Длина дуги
    angle_diff = abs(end_angle - start_angle)
    arc_length = r * angle_diff

    # Адаптивное количество точек (примерно 1 точка на 0.5мм)
    num_points = max(8, int(arc_length / arc_length_threshold))
    num_points = min(num_points, 128)  # ограничение

    points = []
    for k in range(1, num_points + 1):
        t = k / num_points
        angle = start_angle + (end_angle - start_angle) * t
        px = cx + r * math.cos(angle)
        py = cy + r * math.sin(angle)
        points.append([px, py])

    return points


def split_gcode_commands(line):
    """Разбивает строку на отдельные G-code команды."""
    commands = []
    # Разделяем по G0, G1, G2, G3, M82, M83, G92 и т.д.
    pattern = r'((?:G[0123]|M[0-9]+|G9[012])[^G]*?(?=(?:G[0123]|M[0-9]+|G9[012])|$))'
    matches = re.findall(pattern, line)
    if matches:
        commands = [m.strip() for m in matches if m.strip()]
    else:
        commands = [line] if line.strip() else []
    return commands


def parse_gcode_layers(gcode_path, max_layers=None, types_to_keep=None):
    """
    Парсит G-code и возвращает список слоёв.
    """
    if types_to_keep is None:
        types_to_keep = WANTED_TYPES

    layers = {}

    x = y = z = 0.0
    prev_x = prev_y = 0.0
    prev_e = 0.0
    current_z = None
    current_segment = []
    current_type = None

    absolute_extrusion = True

    param_re = re.compile(r'([XYZEFIJPR])(-?\d*\.?\d+)')

    with open(gcode_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue

            # Извлекаем комментарий
            comment = ""
            if ";" in line:
                comment = line[line.index(";") + 1:].strip()
                line = line[:line.index(";")].strip()

            # Определяем тип экструзии
            if comment.startswith("TYPE:"):
                current_type = comment[5:].strip()

            if not line:
                continue

            # Разбиваем строку на отдельные команды
            commands = split_gcode_commands(line)

            for cmd in commands:
                cmd = cmd.strip()
                if not cmd:
                    continue

                # G92 — сброс экструдера
                if cmd.startswith("G92"):
                    params = {p: float(v) for p, v in param_re.findall(cmd)}
                    if "E" in params:
                        prev_e = params["E"]
                    continue

                # M82 / M83
                if "M82" in cmd:
                    absolute_extrusion = True
                    prev_e = 0.0
                    continue
                if "M83" in cmd:
                    absolute_extrusion = False
                    continue

                # Обрабатываем G0, G1, G2, G3
                g_match = re.match(r'G([0123])\b', cmd)
                if not g_match:
                    continue

                g_code = int(g_match.group(1))

                params = {p: float(v) for p, v in param_re.findall(cmd)}

                # Сохраняем предыдущую позицию
                prev_x, prev_y = x, y

                # Обновляем координаты
                new_x = params.get("X", x)
                new_y = params.get("Y", y)
                new_z = params.get("Z", z)

                # Определяем экструзию
                has_extrusion = False
                if "E" in params:
                    e_val = params["E"]
                    if absolute_extrusion:
                        has_extrusion = (e_val > prev_e + 1e-6)
                    else:
                        has_extrusion = (e_val > 1e-6)
                    prev_e = e_val

                # Travel move (G0 или без экструзии)
                if g_code == 0 or not has_extrusion:
                    if current_segment:
                        last_pt = current_segment[-1]
                        dist = math.sqrt(
                            (new_x - last_pt[0])**2 + (new_y - last_pt[1])**2
                        )
                        if dist > TRAVEL_THRESHOLD:
                            if len(current_segment) > 1:
                                layers.setdefault(current_z, []).append(
                                    np.array(current_segment)
                                )
                            current_segment = []
                    x, y, z = new_x, new_y, new_z
                    continue

                # Фильтрация по типу
                if current_type not in types_to_keep:
                    if len(current_segment) > 1:
                        layers.setdefault(current_z, []).append(
                            np.array(current_segment)
                        )
                    current_segment = []
                    x, y, z = new_x, new_y, new_z
                    continue

                # Helical move (G2/G3 с Z и P)
                if g_code in (2, 3) and "Z" in params and "P" in params:
                    # Винтовое движение — добавляем только конечную точку
                    move_points = [[new_x, new_y, new_z]]
                # Обычная дуга G2/G3
                elif g_code in (2, 3) and "I" in params and "J" in params:
                    ccw = (g_code == 3)
                    arc_pts = approximate_arc(
                        prev_x, prev_y,
                        new_x, new_y,
                        params["I"], params["J"],
                        ccw,
                        arc_length_threshold=0.5
                    )
                    move_points = [[pt[0], pt[1], new_z] for pt in arc_pts]
                else:
                    move_points = [[new_x, new_y, new_z]]

                # Обновляем Z
                z_layer = round(new_z, 3)

                if current_z != z_layer:
                    if len(current_segment) > 1:
                        layers.setdefault(current_z, []).append(
                            np.array(current_segment)
                        )
                    current_z = z_layer
                    current_segment = []

                for pt in move_points:
                    current_segment.append(pt)

                x, y, z = new_x, new_y, new_z

    # Последний сегмент
    if len(current_segment) > 1:
        layers.setdefault(current_z, []).append(
            np.array(current_segment)
        )

    sorted_z = sorted(layers.keys())
    if max_layers is not None:
        sorted_z = sorted_z[:max_layers]

    return [layers[z] for z in sorted_z]