from PySide6.QtWidgets import QApplication, QStyleFactory
from PySide6.QtGui import QColor, QAction
from functools import partial

class SettingsMenu:
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
        self.style_actions: list[QAction] = []  # keep references alive
        for style in styles:
            style_action = QAction(f"&{style}")
            self.style_actions.append(style_action)
            style_action.triggered.connect(partial(self._change_style, style))
            self.appearance_menu.addAction(style_action)

        # Set the default appearance if available
        if self.default_appearance in styles:
            self._change_style(self.default_appearance)


class MenuBar:
    """
    Encapsulates all menu‐bar creation, now including:
      - File menu (Exit action)
      - Settings menu (with Appearance → style selector)
      - View menu (Qt-Material dark toggle)
    """
    def __init__(self, parent_window, status_bar):
        self.parent = parent_window
        self.status_bar = status_bar
        self._build_menus()

    def _build_menus(self):
        menubar = self.parent.menuBar()

        # ---- File Menu ----
        file_menu = menubar.addMenu("&File")
        exit_action = QAction("Exit", self.parent)
        exit_action.triggered.connect(QApplication.instance().quit)
        file_menu.addAction(exit_action)

        # ---- Settings Menu (with Appearance submenu) ----
        settings_menu = menubar.addMenu("&Settings")
        self.settings_menu = SettingsMenu(settings_menu)

        # ---- View Menu (Qt-Material toggle) ----
        view_menu = menubar.addMenu("&View")
        self.qt_material_dark_action = QAction("Enable Qt-Material (Dark)", self.parent)
        self.qt_material_dark_action.setCheckable(True)

        try:
            import qt_material
        except ImportError:
            qt_material = None

        if qt_material is None:
            self.qt_material_dark_action.setEnabled(False)
            self.qt_material_dark_action.setToolTip(
                "qt_material not installed. Run: pip install qt-material"
            )
        else:
            self.qt_material_dark_action.setToolTip("Toggle Qt-Material dark theme.")
            self.qt_material_dark_action.triggered.connect(
                self.parent.toggle_qt_material_dark_style
            )

        view_menu.addAction(self.qt_material_dark_action)

    def set_qt_material_checked(self, checked: bool):
        """
        In case the parent window wants to programmatically toggle the checkbox.
        """
        self.qt_material_dark_action.setChecked(checked)