from PySide6.QtWidgets import QStatusBar, QLabel
from PySide6.QtGui import QFont
from si_prefix import si_format

class BottomStatusBar(QStatusBar):
    """A custom status bar for the main window using fixed-width font and SI prefixes."""
    def __init__(self):
        super().__init__()

        # Set monospace font
        fixed_font = QFont("Courier New", 10)
        fixed_font.setStyleHint(QFont.Monospace)

        # Left-justified label: general status
        self.left_label = QLabel("Initialized")
        self.left_label.setFont(fixed_font)
        self.addWidget(self.left_label)

        # Right-justified widget: coordinates
        self.right_label = QLabel("Right Text")
        self.right_label.setFont(fixed_font)
        self.addPermanentWidget(self.right_label)

    def update_status(self, message: str):
        self.left_label.setText(message)

    def update_coordinates(self, x: float, y: float):
        formatted_x = si_format(x, precision=3) + 's'
        formatted_y = si_format(y, precision=3) + 'V'
        formatted_text = f"t ={formatted_x:>12}, V(t) ={formatted_y:>12}"
        self.right_label.setText(formatted_text)

    def clear_coordinates(self):
        formatted_x = " ------- s"
        formatted_y = " ------- V"
        formatted_text = f"t ={formatted_x:>12}, V(t) ={formatted_y:>12}"
        self.right_label.setText(formatted_text)
