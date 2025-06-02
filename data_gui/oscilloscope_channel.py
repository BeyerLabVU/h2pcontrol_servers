from PySide6.QtWidgets import (QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, 
                               QSpinBox, QComboBox, QPushButton, QCheckBox, 
                               QWidget, QDial, QColorDialog)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QWheelEvent
from base_settings_panel import BaseSettingsPanel # Changed from relative to absolute import

class SingleClickDial(QDial):
    def __init__(self, parent=None):
        super().__init__(parent)

    # Override the wheelEvent to customize the step size
    def wheelEvent(self, event: QWheelEvent):
        # Get the amount of scrolling in terms of "degrees"
        delta = event.angleDelta().y() / 8
        steps = delta / 15  # One step is 15 degrees
        
        # Adjust this value to control how much the dial moves per step
        step_size = 1
        
        # Calculate the new value by applying the step_size to steps
        self.setValue(self.value() + step_size * int(steps))

        # Accept the event so no further handling happens
        event.accept()

class OscilloscopeChannelControlPanel(BaseSettingsPanel): # Inherit from BaseSettingsPanel
    """A modular control panel for a single oscilloscope channel (vertical controls)."""
    # Signals to notify when an attribute changes
    colorChanged = Signal(tuple)
    enabledStateChanged = Signal(bool)
    displayStateChanged = Signal(bool)
    loggingStateChanged = Signal(bool)
    voltageScaleChanged = Signal(str)
    offsetChanged = Signal(int)

    def __init__(self, channel_idx=0, channel_name='Channel', color=(255, 255, 255), data_receiver=None, parent=None):
        super().__init__(title=channel_name, parent=parent) # Call BaseSettingsPanel constructor
        self.idx = channel_idx
        # self.name = channel_name # name is handled by BaseSettingsPanel title
        self._color = QColor(*color) # Store as QColor internally
        self.data_receiver = data_receiver

        # self.layout = QVBoxLayout() # Removed: BaseSettingsPanel manages its layout
        # self.setLayout(self.layout) # Removed

        # self.group = QGroupBox(self.name) # Removed: BaseSettingsPanel is the QGroupBox
        # self.group.setSizePolicy(self.sizePolicy()) # Removed
        # self.group_layout = QVBoxLayout() # Removed: Use self.add_setting_row with _form_layout
        # self.group.setLayout(self.group_layout) # Removed

        # Voltage scale selector
        self.voltage_scale_selector = QComboBox()
        if self.data_receiver is not None:
            vscales_values = self.data_receiver.valid_vscales_volts() 
            self.voltage_scale_selector.addItems([str(v) for v in vscales_values])
        self.voltage_scale_selector.currentTextChanged.connect(self._on_voltage_scale_changed)
        self.add_setting_row("Vertical Scale", self.voltage_scale_selector) # Use add_setting_row

        # Offset selector
        self.offset_selector = SingleClickDial() 
        self.offset_selector.setRange(-5, 5) 
        self.offset_selector.setValue(0)
        self.offset_selector.setNotchesVisible(True)
        self.offset_selector.valueChanged.connect(self._on_offset_changed)
        self.add_setting_row("Vertical Offset", self.offset_selector) # Use add_setting_row

        # Enable checkbox
        # self.enable_row = QHBoxLayout() # Removed
        # self.enable_row.addWidget(QLabel("Enable")) # Removed
        # self.enable_row.addStretch(1) # Removed
        self.enable_button = QCheckBox()
        self.enable_button.stateChanged.connect(self._on_enable_state_changed)
        # self.enable_row.addWidget(self.enable_button) # Removed
        self.add_setting_row("Enable", self.enable_button) # Use add_setting_row

        # Logging checkbox
        # self.logging_row = QHBoxLayout() # Removed
        # self.logging_row.addWidget(QLabel("Save Data")) # Removed
        # self.logging_row.addStretch(1) # Removed
        self.logging_button = QCheckBox()
        self.logging_button.stateChanged.connect(self._on_logging_state_changed)
        # self.logging_row.addWidget(self.logging_button) # Removed
        self.add_setting_row("Save Data", self.logging_button) # Use add_setting_row

        # Display checkbox
        # self.display_row = QHBoxLayout() # Removed
        # self.display_row.addWidget(QLabel("Show Trace")) # Removed
        # self.display_row.addStretch(1) # Removed
        self.display_button = QCheckBox()
        self.display_button.stateChanged.connect(self._on_display_state_changed)
        # self.display_row.addWidget(self.display_button) # Removed
        self.add_setting_row("Show Trace", self.display_button) # Use add_setting_row

        # Color display button
        self.color_button = QPushButton() 
        self.color_button.setFixedHeight(20)
        self.color_button.setText("") 
        self.color_button.setToolTip("Click to change trace color")
        self._update_color_button_style() 
        self.color_button.clicked.connect(self._show_color_dialog)
        self.add_setting_row("Trace Color", self.color_button) # Use add_setting_row

        # self.layout.addWidget(self.group) # Removed
        # self.layout.addStretch(1) # Removed

    def _update_color_button_style(self):
        """Updates the background color of the color button."""
        self.color_button.setStyleSheet(f"background-color: {self._color.name()}; border: 1px solid #333;")

    def _show_color_dialog(self):
        """Shows a QColorDialog to select a new color."""
        new_color = QColorDialog.getColor(self._color, self, "Select Trace Color")
        if new_color.isValid():
            self._color = new_color
            self._update_color_button_style()
            self.colorChanged.emit(self._color.getRgb()[:3]) # Emit RGB tuple (r, g, b)

    def _on_voltage_scale_changed(self, text_scale):
        if self.data_receiver:
            self.data_receiver.set_voltage_scale(self.idx, text_scale)
        self.voltageScaleChanged.emit(text_scale)

    def _on_offset_changed(self, value):
        if self.data_receiver:
            self.data_receiver.set_offset(self.idx, value)
        self.offsetChanged.emit(value)

    def _on_enable_state_changed(self, state):
        is_enabled = (state == Qt.CheckState.Checked.value)
        if self.data_receiver:
            self.data_receiver.set_enabled(self.idx, is_enabled)
        self.enabledStateChanged.emit(is_enabled)

    def _on_logging_state_changed(self, state):
        is_logging = (state == Qt.CheckState.Checked.value)
        if self.data_receiver:
            # Assuming method name, was update_save_data, changed to set_logging for consistency
            self.data_receiver.set_logging(self.idx, is_logging) 
        self.loggingStateChanged.emit(is_logging)

    def _on_display_state_changed(self, state):
        is_displaying = (state == Qt.CheckState.Checked.value)
        if self.data_receiver:
            # Assuming method name, was update_display, changed to set_display for consistency
            self.data_receiver.set_display(self.idx, is_displaying)
        self.displayStateChanged.emit(is_displaying)
