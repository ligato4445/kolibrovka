import sys
import os
import json
import argparse
from dataclasses import dataclass
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QSplitter, QVBoxLayout, QWidget,
    QLabel, QPushButton, QHBoxLayout, QMessageBox, QFileDialog, QShortcut
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence

from gcode_parser import parse_gcode_layers
from scene_view import SceneView
from camera_view import CameraView


@dataclass
class AppConfig:
    gcode_path: Path
    image_path: Path
    calibration_path: Path
    max_layers: int = 500
    projection_opacity: float = 0.65


def parse_args(argv):
    base_dir = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="G-code camera calibration tool")
    parser.add_argument("--gcode", default=base_dir / "data" / "gcode" / "golova.gcode")
    parser.add_argument("--image", default=base_dir / "data" / "photo" / "golova1.jpg")
    parser.add_argument("--calibration", default=base_dir / "data" / "calibration_file" / "calibration.json")
    parser.add_argument("--max-layers", type=int, default=200)
    parser.add_argument("--projection-opacity", type=float, default=0.8)
    args = parser.parse_args(argv)
    return AppConfig(
        gcode_path=Path(args.gcode),
        image_path=Path(args.image),
        calibration_path=Path(args.calibration),
        max_layers=args.max_layers,
        projection_opacity=args.projection_opacity,
    )


class MainWindow(QMainWindow):
    def __init__(self, config: AppConfig):
        super().__init__()
        self.config = config
        self.setWindowTitle("G-code Camera Calibration Tool")
        self.resize(1600, 800)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        control_panel = QHBoxLayout()

        self.btn_save = QPushButton("💾 Save Calibration (Ctrl+S)")
        self.btn_save.clicked.connect(self.save_calibration)

        self.btn_load = QPushButton("📂 Load Calibration (Ctrl+L)")
        self.btn_load.clicked.connect(self.load_calibration)

        self.status_label = QLabel("Ready")

        control_panel.addWidget(self.btn_save)
        control_panel.addWidget(self.btn_load)
        control_panel.addStretch()
        control_panel.addWidget(self.status_label)

        layout.addLayout(control_panel)

        self.splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(self.splitter)

        self.scene_view = SceneView(on_camera_changed=self.update_camera_sync)
        self.scene_view.setMinimumWidth(600)
        self.splitter.addWidget(self.scene_view)

        self.camera_view = CameraView(
            image_path=str(self.config.image_path),
            projection_opacity=self.config.projection_opacity,
        )
        self.camera_view.setMinimumWidth(600)
        self.splitter.addWidget(self.camera_view)

        self.splitter.setSizes([800, 800])

        self._setup_shortcuts()

        self._auto_load_calibration()

    def _setup_shortcuts(self):
        shortcut_save = QShortcut(QKeySequence("Ctrl+S"), self)
        shortcut_save.activated.connect(self.save_calibration)

        shortcut_load = QShortcut(QKeySequence("Ctrl+L"), self)
        shortcut_load.activated.connect(self.load_calibration)

    def update_camera_sync(self):
        state = self.scene_view.get_camera_state()
        self.camera_view.set_camera_state(state)

    def save_calibration(self):
        state = self.scene_view.get_camera_state()

        default_path = str(self.config.calibration_path)

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Calibration",
            default_path,
            "JSON Files (*.json)"
        )

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(state, f, indent=2)

                self.status_label.setText(f"Saved: {os.path.basename(file_path)}")
                print(f"Calibration saved to {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save:\n{str(e)}")

    def load_calibration(self):
        default_path = str(self.config.calibration_path)

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Calibration",
            default_path,
            "JSON Files (*.json)"
        )

        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    state = json.load(f)

                self.scene_view.set_camera_state(state)
                self.camera_view.set_camera_state(state)

                self.status_label.setText(f"Loaded: {os.path.basename(file_path)}")
                print(f"Calibration loaded from {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load:\n{str(e)}")

    def _auto_load_calibration(self):
        default_path = str(self.config.calibration_path)
        if os.path.exists(default_path):
            try:
                with open(default_path, 'r', encoding='utf-8') as f:
                    state = json.load(f)

                self.scene_view.set_camera_state(state)
                self.camera_view.set_camera_state(state)

                self.status_label.setText(f"Auto-loaded: {default_path}")
                print(f"Auto-loaded calibration from {default_path}")
            except Exception as e:
                print(f"Failed to auto-load calibration: {e}")


def main():
    config = parse_args(sys.argv[1:])
    app = QApplication([sys.argv[0]])

    gcode_path = config.gcode_path
    print(f"Парсинг G-code: {gcode_path} ...")

    if not os.path.exists(gcode_path):
        print("Файл не найден, генерирую тестовый G-code...")
        gcode_path.parent.mkdir(parents=True, exist_ok=True)
        with open(gcode_path, "w") as f:
            f.write("G28\n")
            for z in [0.2, 0.4, 0.6, 0.8, 1.0]:
                f.write(f"G1 Z{z}\n")
                for x in range(0, 100, 10):
                    f.write(f"G1 X{x} Y50 E1\n")
                    f.write(f"G1 X{x} Y60 E1\n")

    layers = parse_gcode_layers(gcode_path, max_layers=config.max_layers)
    print(f"Загружено слоев: {len(layers)}")

    window = MainWindow(config)

    from PyQt5.QtCore import QTimer
    QTimer.singleShot(100, lambda: window.scene_view.load_layers(layers))
    QTimer.singleShot(100, lambda: window.camera_view.load_layers(layers))

    QTimer.singleShot(200, window.update_camera_sync)

    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
