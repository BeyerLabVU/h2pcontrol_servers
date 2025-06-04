from PySide6.QtWidgets import QPushButton, QSpinBox, QColorDialog, QWidget
from PySide6.QtGui import QColor, QPalette, QPen
from PySide6.QtCore import Signal, Qt
import pyqtgraph as pg

from base_settings_panel import BaseSettingsPanel

class PlotAppearanceSettingsPanel(BaseSettingsPanel):
    """
    A settings panel for controlling plot appearance (color and line thickness).
    Emits signals when settings are changed.
    """
    color_changed = Signal(QColor)
    thickness_changed = Signal(int)

    def __init__(self, title: str, initial_color: QColor, initial_thickness: int, priority: int = 0, parent: QWidget = None):
        """
        Initializes the PlotAppearanceSettingsPanel.

        Args:
            title (str): The title for the QGroupBox.
            initial_color (QColor): The initial color for the plot line.
            initial_thickness (int): The initial thickness for the plot line.
            parent (QWidget, optional): The parent widget. Defaults to None.
        """
        super().__init__(title, parent)

        self._current_color = initial_color
        self._current_thickness = initial_thickness

        # Color setting
        self.color_button = QPushButton()
        self._update_color_button_appearance(self._current_color)
        self.color_button.clicked.connect(self._show_color_dialog)
        self.add_setting_row("Line Color:", self.color_button)

        # Thickness setting
        self.thickness_spinbox = QSpinBox()
        self.thickness_spinbox.setRange(1, 20)  # Sensible range for line thickness
        self.thickness_spinbox.setValue(self._current_thickness)
        self.thickness_spinbox.valueChanged.connect(self._on_thickness_changed)
        self.add_setting_row("Line Thickness (px):", self.thickness_spinbox)

    def _update_color_button_appearance(self, color: QColor) -> None:
        """Updates the color button's text and background color."""
        self.color_button.setText(color.name())
        palette = self.color_button.palette()
        # Set text color for contrast
        palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.black if color.lightnessF() > 0.5 else Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.Button, color)
        self.color_button.setPalette(palette)
        self.color_button.setAutoFillBackground(True) # Important for palette changes to take effect

    def _show_color_dialog(self) -> None:
        """Opens a QColorDialog to select a new color and emits color_changed if valid."""
        new_color = QColorDialog.getColor(self._current_color, self, "Select Line Color")
        if new_color.isValid():
            self._current_color = new_color
            self._update_color_button_appearance(new_color)
            self.color_changed.emit(new_color)

    def _on_thickness_changed(self, thickness: int) -> None:
        """Updates current thickness and emits thickness_changed."""
        self._current_thickness = thickness
        self.thickness_changed.emit(thickness)

    def get_current_pen(self) -> QPen:
        """Returns a pyqtgraph Pen object based on current settings."""
        return pg.mkPen(color=self._current_color, width=self._current_thickness)