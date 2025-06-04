from PySide6.QtWidgets import QPushButton, QStyle, QComboBox
from PySide6.QtCore import Slot, Signal

from .base_settings_panel import BaseSettingsPanel

class RunStopPanel(BaseSettingsPanel):
    """
    Main control panel for controling the status of the whole GUI
        - run / stop oscilloscope trace acquisition
    """
    # Attribute overrides for BaseSettingsPanel
    PRIORITY = 100  # Higher priority to appear at the bottom of the control panel
    TITLE = "Run/Stop Control"
    ERASABLE = False  # This panel should not be erasable; it is essential for operation

    # Define signals as class attributes
    start_data_signal = Signal(str) # Emit the selected stream name
    stop_data_signal  = Signal()
    stream_selected_signal = Signal(str) # Emits the name of the selected stream

    def __init__(self, parent=None, available_streams=None):
        super().__init__(parent)
        self.available_streams = available_streams if available_streams else []
        self.add_runstop_button()
        self.add_stream_selector()

    def add_stream_selector(self):
        self.stream_combo_box = QComboBox()
        if self.available_streams:
            self.stream_combo_box.addItems(self.available_streams)
        else:
            self.stream_combo_box.addItem("No streams available")
            self.stream_combo_box.setEnabled(False)
        
        self.stream_combo_box.currentTextChanged.connect(self.on_stream_selected)
        self.add_setting_row("Data Stream", self.stream_combo_box)
        self.on_stream_selected(self.stream_combo_box.currentText())  # Emit initial selection

    def update_available_streams(self, stream_names):
        self.available_streams = stream_names
        current_selection = self.stream_combo_box.currentText()
        self.stream_combo_box.clear()
        if self.available_streams:
            self.stream_combo_box.addItems(self.available_streams)
            if current_selection in self.available_streams:
                self.stream_combo_box.setCurrentText(current_selection)
            self.stream_combo_box.setEnabled(True)
            if self.stream_combo_box.count() > 0: # Emit signal if there are streams
                 self.on_stream_selected(self.stream_combo_box.currentText()) # Emit for initial selection
        else:
            self.stream_combo_box.addItem("No streams available")
            self.stream_combo_box.setEnabled(False)

    @Slot(str)
    def on_stream_selected(self, stream_name: str):
        if stream_name and stream_name != "No streams available":
            self.stream_selected_signal.emit(stream_name)
            print(f"Stream selected: {stream_name}")
            # Enable run/stop button only if a valid stream is selected
            self.run_stop_btn.setEnabled(True)
        else:
            self.run_stop_btn.setEnabled(False)

    def add_runstop_button(self):
        self.run_stop_btn = QPushButton("Start")
        self.run_stop_btn.setCheckable(True)
        self.play_icon = self.style().standardIcon(QStyle.SP_MediaPlay)
        self.stop_icon = self.style().standardIcon(QStyle.SP_MediaStop)
        self.run_stop_btn.setIcon(self.play_icon)
        self.run_stop_btn.setShortcut("F5")
        self.run_stop_btn.toggled.connect(self.on_run_stop)
        self.add_setting_row("Run/Stop", self.run_stop_btn)        
        # Initially disable run/stop button until a stream is selected
        self.run_stop_btn.setEnabled(False) 

    @Slot(bool)
    def on_run_stop(self, checked: bool):
        selected_stream = self.stream_combo_box.currentText()
        if not selected_stream or selected_stream == "No streams available":
            print("No data stream selected.")
            self.run_stop_btn.setChecked(False) # Revert button state
            return

        if checked:
            # User clicked “Start”
            self.run_stop_btn.setText("Stop")
            self.run_stop_btn.setIcon(self.stop_icon)
            self.start_data_acquisition(selected_stream)
        else:
            # User clicked “Stop”
            self.run_stop_btn.setText("Start")
            self.run_stop_btn.setIcon(self.play_icon)
            self.stop_data_acquisition()

    def start_data_acquisition(self, stream_name: str):
        self.start_data_signal.emit(stream_name)
        print(f">>> Acquisition started for {stream_name}.")

    def stop_data_acquisition(self):
        self.stop_data_signal.emit()
        print("|X| Acquisition stopped.")
