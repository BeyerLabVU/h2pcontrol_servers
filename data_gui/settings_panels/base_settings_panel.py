from PySide6.QtWidgets import QGroupBox, QFormLayout, QWidget, QLabel, QFrame
from PySide6.QtCore import Qt

class BaseSettingsPanel(QGroupBox):
    """
    A base class for creating standardized settings panels.
    Each panel is a QGroupBox with a two-column form layout 
    (labels on the left, controls on the right) and a fixed width.
    Subclasses are expected to call `add_setting_row` to populate themselves.
    """
    PANEL_FIXED_WIDTH = 300  # Default fixed width for all panels, adjust as needed

    # These attributes should be overridden as needed in subclasses:
    PRIORITY = 0  # Default priority for sorting panels, can be overridden`
    TITLE = "Settings Panel"  # Default title for the group box, can be overridden`
    ERASABLE = True  # Default to enabled, can be overridden

    def __init__(self, parent: QWidget = None):
        super().__init__(parent, title=self.TITLE)

        self.setFixedWidth(self.PANEL_FIXED_WIDTH)

        # Main layout for this group box
        self._form_layout = QFormLayout()
        # Styling for the QFormLayout
        self._form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._form_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._form_layout.setContentsMargins(10, 20, 10, 10)  # Top margin for groupbox title space
        self._form_layout.setHorizontalSpacing(10)        # Spacing between label and widget
        self._form_layout.setVerticalSpacing(7)           # Spacing between rows

        self.setLayout(self._form_layout)

    def add_setting_row(self, label_text: str, control_widget: QWidget) -> None:
        label = QLabel(label_text)
        self._form_layout.addRow(label, control_widget)

    def add_separator(self) -> None:
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        # Add a bit of vertical margin for the separator for better visual separation
        separator.setStyleSheet("QFrame { margin-top: 5px; margin-bottom: 5px; }")
        self._form_layout.addRow(separator) 