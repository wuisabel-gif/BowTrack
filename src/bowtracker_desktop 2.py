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
    plugin_root = project_root / ".venv" / "lib" / py_version / "site-packages" / "PySide6" / "Qt" / "plugins"
    platforms_dir = plugin_root / "platforms"

    if platforms_dir.exists():
        os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", str(platforms_dir))
        os.environ.setdefault("QT_PLUGIN_PATH", str(plugin_root))


configure_qt_plugin_path()

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QComboBox, QLabel, QFileDialog
)
from PySide6.QtCore import QTimer

import pyqtgraph as pg


class BowSenseApp(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("BowSense IMU Trajectory Tracker")
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

        self.x_pos = 0.0
        self.y_pos = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.last_time = None

        self.traj_x = []
        self.traj_y = []

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

        self.gyro_plot = pg.PlotWidget(title="Gyroscope")
        self.gyro_plot.setLabel("left", "deg/s")
        self.gyro_plot.setLabel("bottom", "samples")
        self.gx_curve = self.gyro_plot.plot(pen="r", name="gx")
        self.gy_curve = self.gyro_plot.plot(pen="g", name="gy")
        self.gz_curve = self.gyro_plot.plot(pen="b", name="gz")

        self.traj_plot = pg.PlotWidget(title="Estimated Bow Trajectory")
        self.traj_plot.setLabel("left", "Y position estimate")
        self.traj_plot.setLabel("bottom", "X position estimate")
        self.traj_curve = self.traj_plot.plot(pen="y", symbol="o", symbolSize=4)

        layout.addWidget(self.accel_plot)
        layout.addWidget(self.gyro_plot)
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
            self.status_label.setText(f"Connected: {port}")
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
                "gx", "gy", "gz",
                "mx", "my", "mz",
                "x_est", "y_est"
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

                if len(parts) < 7:
                    continue

                time_ms = float(parts[0])
                ax = float(parts[1])
                ay = float(parts[2])
                az = float(parts[3])
                gx = float(parts[4])
                gy = float(parts[5])
                gz = float(parts[6])

                mx = float(parts[7]) if len(parts) > 7 else 0.0
                my = float(parts[8]) if len(parts) > 8 else 0.0
                mz = float(parts[9]) if len(parts) > 9 else 0.0

                self.add_sample(time_ms, ax, ay, az, gx, gy, gz, mx, my, mz)

        except Exception as e:
            self.status_label.setText(f"Serial error: {e}")

    def add_sample(self, time_ms, ax, ay, az, gx, gy, gz, mx, my, mz):
        self.t_data.append(time_ms)
        self.ax_data.append(ax)
        self.ay_data.append(ay)
        self.az_data.append(az)
        self.gx_data.append(gx)
        self.gy_data.append(gy)
        self.gz_data.append(gz)

        if len(self.t_data) > self.max_points:
            self.t_data.pop(0)
            self.ax_data.pop(0)
            self.ay_data.pop(0)
            self.az_data.pop(0)
            self.gx_data.pop(0)
            self.gy_data.pop(0)
            self.gz_data.pop(0)

        self.update_trajectory(time_ms, ax, ay)

        self.ax_curve.setData(self.ax_data)
        self.ay_curve.setData(self.ay_data)
        self.az_curve.setData(self.az_data)

        self.gx_curve.setData(self.gx_data)
        self.gy_curve.setData(self.gy_data)
        self.gz_curve.setData(self.gz_data)

        self.traj_curve.setData(self.traj_x, self.traj_y)

        if self.recording and self.csv_writer:
            self.csv_writer.writerow([
                time_ms,
                ax, ay, az,
                gx, gy, gz,
                mx, my, mz,
                self.x_pos, self.y_pos
            ])

    def update_trajectory(self, time_ms, ax, ay):
        if self.last_time is None:
            self.last_time = time_ms
            return

        dt = (time_ms - self.last_time) / 1000.0
        self.last_time = time_ms

        if dt <= 0 or dt > 0.2:
            return

        # Simple high-pass style deadband to reduce drift
        if abs(ax) < 0.15:
            ax = 0.0
        if abs(ay) < 0.15:
            ay = 0.0

        self.vx += ax * dt
        self.vy += ay * dt

        # Damping to prevent runaway drift
        self.vx *= 0.98
        self.vy *= 0.98

        self.x_pos += self.vx * dt
        self.y_pos += self.vy * dt

        self.traj_x.append(self.x_pos)
        self.traj_y.append(self.y_pos)

        if len(self.traj_x) > self.max_points:
            self.traj_x.pop(0)
            self.traj_y.pop(0)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BowSenseApp()
    window.show()
    sys.exit(app.exec())
