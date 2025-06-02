from PySide6 import QtWidgets
import pyqtgraph as pg
from pyqtgraph.dockarea import DockArea, Dock
import sys
# Attempt to import qdarkstyle
try:
    import qdarkstyle
except ImportError:
    qdarkstyle = None
    print("qdarkstyle not installed. Run: pip install qdarkstyle")

app = QtWidgets.QApplication(sys.argv)
win = QtWidgets.QMainWindow()

area = DockArea()
win.setCentralWidget(area)
win.resize(500, 400) # Increased size slightly

d1 = Dock("Dock 1 - Test")
d1.addWidget(QtWidgets.QLabel("Content for Dock 1. Try double-clicking title."))
area.addDock(d1, 'left')
print(f"Minimal test: d1.area after addDock: {d1.area}")

d2 = Dock("Dock 2 - Test")
d2.addWidget(QtWidgets.QPushButton("Button in Dock 2"))
area.addDock(d2, 'right', d1) # Add relative to d1
print(f"Minimal test: d2.area after addDock: {d2.area}")

# Apply qdarkstyle if available
if qdarkstyle:
    app.setStyleSheet(qdarkstyle.load_stylesheet())


win.show()
print(f"pyqtgraph version: {pg.__version__}") # Print pyqtgraph version
sys.exit(app.exec())