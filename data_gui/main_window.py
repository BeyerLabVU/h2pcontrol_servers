import sys
import signal
import time

from PySide6.QtWidgets import (
    QMainWindow,
    QStatusBar,
    QWidget,
    QApplication,
    QHBoxLayout,
)
from PySide6.QtGui import QColor, QAction

from styled_plot import StyledPlotWidget
from bottom_status_bar import BottomStatusBar
from control_panel import ControlPanel
from plot_settings_panel import PlotAppearanceSettingsPanel
from top_menu_bar import MenuBar

# Attempt to import qt_material for theming
try:
    import qt_material
except ImportError:
    qt_material = None

class MainWindow(QMainWindow):
    """Main application window for the oscilloscope GUI, with appearance customization."""
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Oscilloscope: Direct Trace View")
        self.setMinimumSize(1920 // 2, 1080 // 2)  # Prevent shrinking too small

        # ---- Status bar & Plot widget ----
        self.plot_status_bar = BottomStatusBar()
        self.plotwidget = StyledPlotWidget(self.plot_status_bar)

        # ---- Control panel (scroll area on the right) ----
        self.control_panel = ControlPanel()

        # ---- Central widget layout ----
        central_widget = QWidget()
        layout = QHBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.plotwidget, stretch=1)
        layout.addWidget(self.control_panel, stretch=0)
        self.setCentralWidget(central_widget)

        # Set our custom status bar
        self.setStatusBar(self.plot_status_bar)

        # ---- Build menus via MenuBar helper ----
        self.menu = MenuBar(self, self.plot_status_bar)

        # ---- Initialize appearance customization panels ----
        self._setup_plot_appearance_settings()

    def _setup_plot_appearance_settings(self):
        """Adds a Plot Appearance Settings panel to the ControlPanel."""
        initial_color = QColor("#0077bb")  # default trace color
        initial_thickness = 1

        self.plot_appearance_panel = PlotAppearanceSettingsPanel(
            title="Trace Plot Style",
            initial_color=initial_color,
            initial_thickness=initial_thickness,
            parent=self.control_panel
        )
        self.control_panel.add_panel(self.plot_appearance_panel)

        # Connect signals to update the plot pen
        self.plot_appearance_panel.color_changed.connect(self._update_trace_plot_pen)
        self.plot_appearance_panel.thickness_changed.connect(self._update_trace_plot_pen)

    def _update_trace_plot_pen(self, _=None):
        """Updates the pen of the trace plot based on the settings panel."""
        new_pen = self.plot_appearance_panel.get_current_pen()
        if hasattr(self, 'trace_line') and self.trace_line:
            self.trace_line.setPen(new_pen)
        else:
            # First time drawing: create a placeholder line
            self.trace_line = self.plotwidget.plot(pen=new_pen)

    def toggle_qt_material_dark_style(self, checked: bool) -> None:
        """Applies or removes the Qt-Material dark theme."""
        app = QApplication.instance()
        if app and qt_material:
            if checked:
                qt_material.apply_stylesheet(app, theme='dark_teal.xml')
            else:
                app.setStyleSheet("")  # Revert to default QStyle

            status_text = "enabled" if checked else "disabled"
            self.plot_status_bar.showMessage(f"Qt-Material (Dark) style {status_text}.")
