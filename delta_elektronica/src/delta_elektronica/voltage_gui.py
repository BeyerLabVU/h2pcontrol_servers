import sys
import serial
import time
from SCPIClient import SCPIClient
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QSpinBox,
    QLabel,
    QPlainTextEdit,
    QComboBox,
)
from PySide6.QtCore import Slot
import serial.tools.list_ports

BAUDRATE = 9600
TIMEOUT = 1  # seconds


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DAC Control GUI")
        self.client = None

        # Serial connection
        self.cmb_port = QComboBox()
        self.btn_connect = QPushButton("Connect")
        self.btn_connect.clicked.connect(self.on_connect)

        # Voltage control
        self.voltage_spin = QSpinBox()
        self.voltage_spin.setRange(0.0, 280.0)
        self.voltage_spin.setSingleStep(1)
        self.voltage_spin.setSuffix(" V")

        self.btn_set_voltage = QPushButton("Set Voltage")
        self.btn_set_voltage.setEnabled(False)
        self.btn_set_voltage.clicked.connect(self.on_set_voltage)

        # Logging
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)

        # Layout
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Port:"))
        top_layout.addWidget(self.cmb_port)
        top_layout.addWidget(self.btn_connect)

        control_layout = QHBoxLayout()
        control_layout.addWidget(QLabel("Voltage:"))
        control_layout.addWidget(self.voltage_spin)
        control_layout.addWidget(self.btn_set_voltage)

        layout = QVBoxLayout()
        layout.addLayout(top_layout)
        layout.addLayout(control_layout)
        layout.addWidget(self.log)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.refresh_ports()

    def refresh_ports(self):
        self.cmb_port.clear()
        ports = serial.tools.list_ports.comports()
        for p in ports:
            self.cmb_port.addItem(p.device)
        if not ports:
            self.cmb_port.addItem("<No ports>")

    def log_message(self, msg):
        self.log.appendPlainText(f"[{time.strftime('%H:%M:%S')}] {msg}")

    @Slot()
    def on_connect(self):
        port = self.cmb_port.currentText()
        if port in ("<No ports>", ""):
            return self.log_message("No port selected")
        try:
            self.log_message(f"Opening {port}...")
            self.client = SCPIClient(port, BAUDRATE, TIMEOUT)
            idn = self.client.send("*IDN?")
            self.log_message(f"Connected: {idn}")
            self.btn_set_voltage.setEnabled(True)
        except Exception as e:
            self.log_message(f"Connect error: {e}")

    @Slot()
    def on_set_voltage(self):
        if not self.client:
            return
        voltage = self.voltage_spin.value()
        cmd = f"SOURce:VOLTage {voltage}"
        self.log_message(f"Sending: {cmd}")
        resp = self.client.send(cmd)
        if resp:
            self.log_message(f"Response: {resp}")

    def closeEvent(self, event):
        if self.client:
            self.client.close()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.resize(500, 200)
    w.show()
    sys.exit(app.exec())
