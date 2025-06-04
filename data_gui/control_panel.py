from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QGroupBox, QStyle, QSizePolicy,
    QHBoxLayout, QLabel, QSpinBox, QComboBox, QPushButton, QCheckBox
)
from PySide6.QtCore import Qt

from settings_panels.base_settings_panel import BaseSettingsPanel

class ControlPanel(QScrollArea):
    """
    A QScrollArea containing the settings/control elements for the GUI.
    It encapsulates the creation of the form layout and its widgets.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)

        # Create the main content widget that will be scrolled
        self._content_widget = QWidget()
        # Use a QVBoxLayout to stack multiple settings panels vertically
        self._main_layout = QVBoxLayout(self._content_widget)
        self._main_layout.setAlignment(Qt.AlignmentFlag.AlignTop) # Panels stack from the top
        self._main_layout.setContentsMargins(5, 5, 5, 5) # Optional: margins for the overall panel area
        self._main_layout.setSpacing(10) # Spacing between panels

        # Set the content widget as the widget for the scroll area
        self.setWidget(self._content_widget)

        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.setMinimumWidth(BaseSettingsPanel.PANEL_FIXED_WIDTH + 30)  
        self.setMaximumWidth(BaseSettingsPanel.PANEL_FIXED_WIDTH + 30)

        self.control_panels = []

    def add_panel(self, panel: QGroupBox): # QGroupBox is parent of BaseSettingsPanel
        # Add the panel to the list
        self.control_panels.append(panel)
        # Sort panels by PRIORITY (higher comes first)
        self.control_panels.sort(key=lambda p: -getattr(p, "PRIORITY", 0))
        # Remove all widgets from layout
        while self._main_layout.count():
            child_item = self._main_layout.takeAt(0)
            if child_item and child_item.widget():
                child_item.widget().setParent(None)
        # Add widgets back in sorted order
        for p in self.control_panels:
            self._main_layout.addWidget(p)

    def clear_panels(self):
        # Remove only panels with ERASABLE=True
        remaining_panels = []
        for panel in self.control_panels:
            if getattr(panel, "ERASABLE", True):
                # Remove from layout if present
                panel.setParent(None)
                panel.deleteLater()
            else:
                remaining_panels.append(panel)
        self.control_panels = remaining_panels
        # Remove all widgets from layout and re-add remaining panels
        while self._main_layout.count():
            child_item = self._main_layout.takeAt(0)
        for p in self.control_panels:
            self._main_layout.addWidget(p)

