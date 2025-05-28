from PySide6.QtWidgets import (
    QApplication, QStyleFactory,
)
from PySide6.QtGui import QAction
from functools import partial

class SettingsMenu():
    def __init__(self, menu) -> None:
        self.menu = menu

        self.default_appearance = "Windows"

        self.add_appearance_selector()

    def _style_names(self) -> list[str]:
        default = QApplication.style().objectName().lower()
        styles = QStyleFactory.keys()
        return sorted(styles, key=lambda s: s.lower() != default)
    
    def _change_style(self, style_name: str) -> None:
        QApplication.setStyle(QStyleFactory.create(style_name))

    def add_appearance_selector(self) -> None:
        self.appearance_menu = self.menu.addMenu("&Appearance")

        styles = self._style_names()
        self.style_actions = [] # Keep the actions around to escape the Python garbage collector
        for style in styles:
            style_action = QAction(f"&{style}")
            self.style_actions.append(style_action)
            style_action.triggered.connect(partial(self._change_style, style))
            self.appearance_menu.addAction(style_action)

        # Set the default appearance if possible
        if self.default_appearance in styles:
            self._change_style(self.default_appearance)
