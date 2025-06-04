import serial
import time


class SCPIClient:
    def __init__(self, port, baudrate, timeout):
        self.ser = serial.Serial(port, baudrate, timeout=timeout)
        time.sleep(2)

    def send(self, cmd: str) -> str:
        self.ser.reset_input_buffer()
        self.ser.write((cmd.strip() + "\n").encode("ascii"))
        return self.ser.readline().decode("ascii", errors="ignore").strip()

    def close(self):
        if self.ser.is_open:
            self.ser.close()
