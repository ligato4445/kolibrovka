"""
main.py
Главное приложение калибровки камеры.
Объединяет 3D-просмотр и наложение на фото в реальном времени.
Добавлено сохранение/загрузка параметров калибровки в JSON.
"""

import sys
import os
import json
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QSplitter, QVBoxLayout, QWidget,
    QLabel, QPushButton, QHBoxLayout, QMessageBox, QFileDialog
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence

from gcode_parser import parse_gcode_layers
from scene_view import SceneView
from camera_view import CameraView


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("G-code Camera Calibration Tool")
        self.resize(1600, 800)

        # Центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Панель управления (кнопки)
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

        # Сплиттер для двух окон
        self.splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(self.splitter)

        # Левая панель: 3D-вид
        self.scene_view = SceneView()
        self.scene_view.setMinimumWidth(600)
        self.splitter.addWidget(self.scene_view)

        # Правая панель: Вид с наложением на фото
        self.camera_view = CameraView()
        self.camera_view.setMinimumWidth(600)
        self.splitter.addWidget(self.camera_view)

        # Устанавливаем начальные пропорции сплиттера (50/50)
        self.splitter.setSizes([800, 800])

        # Связываем SceneView с MainWindow для синхронизации
        self.scene_view.main_window_ref = self

        # Подменяем методы мыши в SceneView для добавления синхронизации
        import types
        self.scene_view.mouseMoveEvent = types.MethodType(_patched_mouseMoveEvent, self.scene_view)
        self.scene_view.wheelEvent = types.MethodType(_patched_wheelEvent, self.scene_view)

        # Настраиваем горячие клавиши
        self._setup_shortcuts()

        # Пытаемся автоматически загрузить calibration.json при старте
        self._auto_load_calibration()

    def _setup_shortcuts(self):
        """Настраивает горячие клавиши."""
        from PyQt5.QtWidgets import QShortcut

        # Ctrl+S - сохранить
        shortcut_save = QShortcut(QKeySequence("Ctrl+S"), self)
        shortcut_save.activated.connect(self.save_calibration)

        # Ctrl+L - загрузить
        shortcut_load = QShortcut(QKeySequence("Ctrl+L"), self)
        shortcut_load.activated.connect(self.load_calibration)

    def update_camera_sync(self):
        """Синхронизирует камеру CameraView с текущим состоянием SceneView."""
        state = self.scene_view.get_camera_state()
        self.camera_view.set_camera_state(state)

    def save_calibration(self):
        """Сохраняет параметры калибровки в JSON."""
        state = self.scene_view.get_camera_state()

        # По умолчанию сохраняем в calibration.json в текущей папке
        default_path = "calibration.json"

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

                self.status_label.setText(f"✅ Saved: {os.path.basename(file_path)}")
                print(f"✅ Calibration saved to {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save:\n{str(e)}")

    def load_calibration(self):
        """Загружает параметры калибровки из JSON."""
        default_path = "calibration.json"

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

                # Применяем параметры к обоим видам
                self.scene_view.set_camera_state(state)
                self.camera_view.set_camera_state(state)

                self.status_label.setText(f"✅ Loaded: {os.path.basename(file_path)}")
                print(f"✅ Calibration loaded from {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load:\n{str(e)}")

    def _auto_load_calibration(self):
        """Автоматически загружает calibration.json, если он существует."""
        default_path = "calibration.json"
        if os.path.exists(default_path):
            try:
                with open(default_path, 'r', encoding='utf-8') as f:
                    state = json.load(f)

                self.scene_view.set_camera_state(state)
                self.camera_view.set_camera_state(state)

                self.status_label.setText(f"📂 Auto-loaded: {default_path}")
                print(f"📂 Auto-loaded calibration from {default_path}")
            except Exception as e:
                print(f"⚠️ Failed to auto-load calibration: {e}")


# Хак для синхронизации: добавим вызов sync в SceneView
def _patched_mouseMoveEvent(self, event):
    # Оригинальная логика
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
    # Вызываем синхронизацию, если главный окно существует
    if hasattr(self, 'main_window_ref'):
        self.main_window_ref.update_camera_sync()

def _patched_wheelEvent(self, event):
    delta = event.angleDelta().y()
    self.camera.zoom(delta / 500.0)
    self.update()
    if hasattr(self, 'main_window_ref'):
        self.main_window_ref.update_camera_sync()


def main():
    app = QApplication(sys.argv)

    # 1. Парсинг G-code
    gcode_path = "gcode/test1_inception_vertical.gcode"
    print(f"Парсинг G-code: {gcode_path} ...")

    if not os.path.exists(gcode_path):
        print("⚠️ Файл не найден, генерирую тестовый G-code...")
        with open(gcode_path, "w") as f:
            f.write("G28\n")
            for z in [0.2, 0.4, 0.6, 0.8, 1.0]:
                f.write(f"G1 Z{z}\n")
                for x in range(0, 100, 10):
                    f.write(f"G1 X{x} Y50 E1\n")
                    f.write(f"G1 X{x} Y60 E1\n")

    layers = parse_gcode_layers(gcode_path, max_layers=60)
    print(f"✅ Загружено слоев: {len(layers)}")

    # 2. Создание главного окна
    window = MainWindow()

    # 3. Загрузка данных в оба вида (отложенно, чтобы OpenGL контекст был создан)
    from PyQt5.QtCore import QTimer
    QTimer.singleShot(100, lambda: window.scene_view.load_layers(layers))
    QTimer.singleShot(100, lambda: window.camera_view.load_layers(layers))

    # 4. Начальная синхронизация
    QTimer.singleShot(200, window.update_camera_sync)

    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()