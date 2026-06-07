import sys
import csv
import os
from pathlib import Path

import numpy as np
import serial
import serial.tools.list_ports


def configure_qt_plugin_path() -> None:
    """Point Qt at the PySide6 platform plugins bundled in the active environment."""
    py_version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    project_root = Path(__file__).resolve().parent.parent
    candidate_roots = [
        Path(sys.prefix) / "lib" / py_version / "site-packages" / "PySide6" / "Qt" / "plugins",
        project_root / ".venv" / "lib" / py_version / "site-packages" / "PySide6" / "Qt" / "plugins",
        project_root / ".venv312_gui" / "lib" / py_version / "site-packages" / "PySide6" / "Qt" / "plugins",
    ]

    for plugin_root in candidate_roots:
        platforms_dir = plugin_root / "platforms"
        if platforms_dir.exists():
            os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", str(platforms_dir))
            os.environ.setdefault("QT_PLUGIN_PATH", str(plugin_root))
            break


configure_qt_plugin_path()

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QComboBox, QLabel, QFileDialog
)
from PySide6.QtCore import QTimer

import pyqtgraph as pg
try:
    import pyqtgraph.opengl as gl
except Exception:  # pragma: no cover - GUI dependency fallback
    gl = None


class BowSenseApp(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("BowTrack IMU Viewer")
        self.resize(1200, 800)

        self.serial_port = None
        self.recording = False
        self.csv_file = None
        self.csv_writer = None

        self.max_points = 500

        self.t_data = []
        self.ax_data = []
        self.ay_data = []
        self.az_data = []
        self.gx_data = []
        self.gy_data = []
        self.gz_data = []
        self.accel_mag_data = []

        self.accel_points = []
        self.current_vector = np.zeros((2, 3), dtype=np.float32)

        self.setup_ui()

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_serial)
        self.timer.start(20)

    def setup_ui(self):
        central = QWidget()
        layout = QVBoxLayout()

        control_layout = QHBoxLayout()

        self.port_box = QComboBox()
        self.refresh_ports()

        self.refresh_button = QPushButton("Refresh Ports")
        self.refresh_button.clicked.connect(self.refresh_ports)

        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.connect_serial)

        self.record_button = QPushButton("Start Recording")
        self.record_button.clicked.connect(self.toggle_recording)

        self.status_label = QLabel("Disconnected")

        control_layout.addWidget(QLabel("Serial Port:"))
        control_layout.addWidget(self.port_box)
        control_layout.addWidget(self.refresh_button)
        control_layout.addWidget(self.connect_button)
        control_layout.addWidget(self.record_button)
        control_layout.addWidget(self.status_label)

        layout.addLayout(control_layout)

        self.accel_plot = pg.PlotWidget(title="Acceleration")
        self.accel_plot.setLabel("left", "m/s²")
        self.accel_plot.setLabel("bottom", "samples")
        self.ax_curve = self.accel_plot.plot(pen="r", name="ax")
        self.ay_curve = self.accel_plot.plot(pen="g", name="ay")
        self.az_curve = self.accel_plot.plot(pen="b", name="az")
        self.mag_curve = self.accel_plot.plot(pen="w", name="|a|")

        self.gyro_plot = pg.PlotWidget(title="Gyroscope")
        self.gyro_plot.setLabel("left", "deg/s")
        self.gyro_plot.setLabel("bottom", "samples")
        self.gx_curve = self.gyro_plot.plot(pen="r", name="gx")
        self.gy_curve = self.gyro_plot.plot(pen="g", name="gy")
        self.gz_curve = self.gyro_plot.plot(pen="b", name="gz")

        if gl is not None:
            self.traj_plot = gl.GLViewWidget()
            self.traj_plot.setWindowTitle("Live 3D Acceleration View")
            self.traj_plot.setCameraPosition(distance=24, elevation=20, azimuth=35)

            grid = gl.GLGridItem()
            grid.scale(2, 2, 2)
            self.traj_plot.addItem(grid)

            self.traj_line = gl.GLLinePlotItem(
                pos=np.zeros((1, 3), dtype=np.float32),
                color=(0.95, 0.85, 0.2, 1.0),
                width=2.5,
                antialias=True,
            )
            self.vector_line = gl.GLLinePlotItem(
                pos=self.current_vector,
                color=(0.2, 0.9, 1.0, 1.0),
                width=4.0,
                antialias=True,
            )
            self.traj_plot.addItem(self.traj_line)
            self.traj_plot.addItem(self.vector_line)
            self.traj_label = QLabel("3D live view: acceleration vector and recent trail")
        else:
            self.traj_plot = pg.PlotWidget(title="3D view unavailable")
            self.traj_plot.setLabel("left", "az")
            self.traj_plot.setLabel("bottom", "ax")
            self.traj_curve = self.traj_plot.plot(pen="y", symbol="o", symbolSize=4)
            self.traj_label = QLabel("Install PyOpenGL for the live 3D graph. Falling back to ax/az view.")

        layout.addWidget(self.accel_plot)
        layout.addWidget(self.gyro_plot)
        layout.addWidget(self.traj_label)
        layout.addWidget(self.traj_plot)

        central.setLayout(layout)
        self.setCentralWidget(central)

    def refresh_ports(self):
        self.port_box.clear()
        ports = serial.tools.list_ports.comports()

        for port in ports:
            self.port_box.addItem(port.device)

    def connect_serial(self):
        port = self.port_box.currentText()

        if not port:
            self.status_label.setText("No port selected")
            return

        try:
            self.serial_port = serial.Serial(port, 115200, timeout=0.01)
            self.status_label.setText(f"Connected: {port} | waiting for IMU data")
        except Exception as e:
            self.status_label.setText(f"Error: {e}")

    def toggle_recording(self):
        if not self.recording:
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Save CSV",
                "bowsense_session.csv",
                "CSV Files (*.csv)"
            )

            if not path:
                return

            self.csv_file = open(path, "w", newline="")
            self.csv_writer = csv.writer(self.csv_file)

            self.csv_writer.writerow([
                "time_ms",
                "ax", "ay", "az",
                "accel_mag",
                "gx", "gy", "gz",
                "mx", "my", "mz",
                "view_x", "view_y", "view_z"
            ])

            self.recording = True
            self.record_button.setText("Stop Recording")
        else:
            self.recording = False
            self.record_button.setText("Start Recording")

            if self.csv_file:
                self.csv_file.close()
                self.csv_file = None

    def update_serial(self):
        if self.serial_port is None:
            return

        try:
            while self.serial_port.in_waiting:
                line = self.serial_port.readline().decode(errors="ignore").strip()

                if not line or line.startswith("time"):
                    continue

                parts = line.split(",")

                if len(parts) < 5:
                    continue

                time_ms = float(parts[0])
                ax = float(parts[1])
                ay = float(parts[2])
                az = float(parts[3])
                accel_mag = float(parts[4])

                gx = float(parts[5]) if len(parts) > 5 else 0.0
                gy = float(parts[6]) if len(parts) > 6 else 0.0
                gz = float(parts[7]) if len(parts) > 7 else 0.0

                mx = float(parts[8]) if len(parts) > 8 else 0.0
                my = float(parts[9]) if len(parts) > 9 else 0.0
                mz = float(parts[10]) if len(parts) > 10 else 0.0

                self.add_sample(time_ms, ax, ay, az, accel_mag, gx, gy, gz, mx, my, mz)
                self.status_label.setText(f"Connected: {self.serial_port.port} | live IMU data")

        except Exception as e:
            self.status_label.setText(f"Serial error: {e}")

    def add_sample(self, time_ms, ax, ay, az, accel_mag, gx, gy, gz, mx, my, mz):
        self.t_data.append(time_ms)
        self.ax_data.append(ax)
        self.ay_data.append(ay)
        self.az_data.append(az)
        self.accel_mag_data.append(accel_mag)
        self.gx_data.append(gx)
        self.gy_data.append(gy)
        self.gz_data.append(gz)

        if len(self.t_data) > self.max_points:
            self.t_data.pop(0)
            self.ax_data.pop(0)
            self.ay_data.pop(0)
            self.az_data.pop(0)
            self.accel_mag_data.pop(0)
            self.gx_data.pop(0)
            self.gy_data.pop(0)
            self.gz_data.pop(0)

        self.update_3d_view(ax, ay, az)

        self.ax_curve.setData(self.ax_data)
        self.ay_curve.setData(self.ay_data)
        self.az_curve.setData(self.az_data)
        self.mag_curve.setData(self.accel_mag_data)

        self.gx_curve.setData(self.gx_data)
        self.gy_curve.setData(self.gy_data)
        self.gz_curve.setData(self.gz_data)

        if self.recording and self.csv_writer:
            view_x, view_y, view_z = self.accel_points[-1] if self.accel_points else (0.0, 0.0, 0.0)
            self.csv_writer.writerow([
                time_ms,
                ax, ay, az,
                accel_mag,
                gx, gy, gz,
                mx, my, mz,
                view_x, view_y, view_z
            ])

    def update_3d_view(self, ax, ay, az):
        point = np.array([ax, ay, az], dtype=np.float32)
        self.accel_points.append(point)
        if len(self.accel_points) > self.max_points:
            self.accel_points.pop(0)

        self.current_vector = np.vstack([np.zeros(3, dtype=np.float32), point])

        if gl is not None:
            points = np.array(self.accel_points, dtype=np.float32)
            self.traj_line.setData(pos=points)
            self.vector_line.setData(pos=self.current_vector)
        else:
            points = np.array(self.accel_points, dtype=np.float32)
            self.traj_curve.setData(points[:, 0], points[:, 2])


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BowSenseApp()
    window.show()
    sys.exit(app.exec())
