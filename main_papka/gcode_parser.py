"""Parse extrusion moves from G-code into printable layer polylines."""

import re
import numpy as np


TRAVEL_THRESHOLD = 3.0


def parse_gcode_layers(gcode_path, max_layers=None):
    """
    Парсит G-code и возвращает список слоев.

    Формат результата:

    [
        [
            segment_1,
            segment_2,
            ...
        ],
        ...
    ]

    segment:
        np.ndarray(N, 3)

    где каждая строка:
        [x, y, z]
    """

    layers = {}

    x = y = z = 0.0
    prev_e = 0.0

    current_z = None
    current_segment = []

    absolute_extrusion = True

    param_re = re.compile(r'([XYZEF])(-?\d*\.?\d+)')

    # --------------------------------------------------
    # Определяем режим экструзии
    # --------------------------------------------------

    with open(gcode_path, "r", encoding="utf-8") as f:
        for line in f:
            if "M82" in line:
                absolute_extrusion = True
                break
            elif "M83" in line:
                absolute_extrusion = False
                break

    # --------------------------------------------------
    # Основной проход
    # --------------------------------------------------

    with open(gcode_path, "r", encoding="utf-8") as f:

        for line in f:

            if ";" in line:
                line = line[:line.index(";")]

            line = line.strip()

            if not line:
                continue

            if not ("G0" in line or "G1" in line):
                continue

            params = {
                p: float(v)
                for p, v in param_re.findall(line)
            }

            if "X" in params:
                x = params["X"]

            if "Y" in params:
                y = params["Y"]

            if "Z" in params:
                z = params["Z"]

            has_extrusion = False

            if "E" in params:
                e_val = params["E"]

                if absolute_extrusion:
                    has_extrusion = (
                        e_val > prev_e and
                        e_val > 0
                    )
                else:
                    has_extrusion = (
                        e_val > 0
                    )

                prev_e = e_val

            # --------------------------------------------------
            # Экструзия
            # --------------------------------------------------

            if has_extrusion:

                z_layer = round(z, 2)

                if current_z != z_layer:

                    if len(current_segment) > 1:

                        layers.setdefault(
                            current_z,
                            []
                        ).append(
                            np.array(current_segment)
                        )

                    current_z = z_layer
                    current_segment = []

                current_segment.append(
                    [x, y, z]
                )

            # --------------------------------------------------
            # Travel move
            # --------------------------------------------------

            else:

                if current_segment:

                    last_pt = current_segment[-1]

                    dist = np.sqrt(
                        (x - last_pt[0]) ** 2 +
                        (y - last_pt[1]) ** 2
                    )

                    if dist > TRAVEL_THRESHOLD:

                        if len(current_segment) > 1:

                            layers.setdefault(
                                current_z,
                                []
                            ).append(
                                np.array(current_segment)
                            )

                        current_segment = []

    # --------------------------------------------------
    # Последний сегмент
    # --------------------------------------------------

    if len(current_segment) > 1:

        layers.setdefault(
            current_z,
            []
        ).append(
            np.array(current_segment)
        )

    sorted_z = sorted(layers.keys())

    if max_layers is not None:
        sorted_z = sorted_z[:max_layers]

    return [
        layers[z]
        for z in sorted_z
    ]
