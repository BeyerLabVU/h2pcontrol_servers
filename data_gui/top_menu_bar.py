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
    def __init__(self, parent_window, status_bar):
        self.parent = parent_window
        self.status_bar = status_bar
        self._build_menus()

    def _build_menus(self):
        self.menubar = self.parent.menuBar()
        self.menubar.setNativeMenuBar(True)

        # ---- File Menu ----
        file_menu = self.menubar.addMenu("&File")

        self.change_save_directory_action = QAction("Refresh Data Directory", self.parent)
        file_menu.addAction(self.change_save_directory_action)

        self.change_save_directory_action = QAction("Force Change Data Directory", self.parent)
        file_menu.addAction(self.change_save_directory_action)

        self.temp_duplicate_directory_action = QAction("Add Temp Duplicate Data Directory", self.parent)
        file_menu.addAction(self.temp_duplicate_directory_action)

        file_menu.addSeparator()

        self.save_config_action = QAction("Save Configuration", self.parent)
        file_menu.addAction(self.save_config_action)

        self.save_config_action = QAction("Save Nodes", self.parent)
        file_menu.addAction(self.save_config_action)

        file_menu.addSeparator()

        self.load_config_action = QAction("Load Configuration", self.parent)
        file_menu.addAction(self.load_config_action)

        self.load_config_action = QAction("Load Nodes", self.parent)
        file_menu.addAction(self.load_config_action)

        file_menu.addSeparator()

        file_menu.addSeparator()
        exit_action = QAction("Exit", self.parent)
        exit_action.triggered.connect(QApplication.instance().quit)
        file_menu.addAction(exit_action)

        # ---- Settings Menu (with Appearance submenu) ----
        settings_menu = self.menubar.addMenu("&Settings")
        self.settings_menu = SettingsMenu(settings_menu)

        # ---- View Menu (Qt-Material toggle) ----
        view_menu = self.menubar.addMenu("&View")
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
        self.qt_material_dark_action.setChecked(checked)