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

    def __init__(self, title: str, parent: QWidget = None):
        """
        Initializes the BaseSettingsPanel.

        Args:
            title (str): The title for the QGroupBox.
            parent (QWidget, optional): The parent widget. Defaults to None.
        """
        super().__init__(title, parent)

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
        """
        Adds a new row with a label and a control widget to the settings panel.

        Args:
            label_text (str): The text for the label.
            control_widget (QWidget): The widget for the control.
        """
        label = QLabel(label_text)
        self._form_layout.addRow(label, control_widget)

    def add_separator(self) -> None:
        """
        Adds a horizontal separator line to the layout.
        The separator spans both columns of the form layout.
        """
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        # Add a bit of vertical margin for the separator for better visual separation
        separator.setStyleSheet("QFrame { margin-top: 5px; margin-bottom: 5px; }")
        self._form_layout.addRow(separator)  # In QFormLayout, addRow(QWidget) spans both columns

    # Example placeholder methods for subclasses to implement:
    # def get_settings(self) -> dict:
    #     """
    #     Subclasses should implement this method to retrieve all current
    #     settings from their respective controls as a dictionary.
    #     """
    #     raise NotImplementedError("Subclasses must implement get_settings()")

    # def set_settings(self, settings: dict) -> None:
    #     """
    #     Subclasses should implement this method to apply settings
    #     from a dictionary to their respective controls.
    #     """
    #     raise NotImplementedError("Subclasses must implement set_settings()")