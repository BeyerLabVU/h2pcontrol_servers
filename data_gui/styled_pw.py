import pyqtgraph as pg
from PySide6.QtGui import QFont, QCursor
from PySide6.QtWidgets import QVBoxLayout, QWidget, QLabel
from PySide6.QtCore import Qt, QPointF
import numpy as np

class StyledPlotWidget(QWidget):
    """A PlotWidget with a shared style (background, grid, axes, default pen) wrapped in a QWidget with QVBoxLayout."""
    def __init__(self, *args, background="#ffffff", grid_alpha=0.3, default_color="#0077bb", **kwargs):
        super().__init__(*args, **kwargs)

        # Create the layout
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        # Create the PlotWidget
        self.plot_widget = pg.PlotWidget()
        self._default_pen = pg.mkPen(color=default_color, width=2)
        self._configure(background, grid_alpha)

        # Add the PlotWidget to the layout
        self.layout.addWidget(self.plot_widget)

        # Add the label below the plot
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignRight)
        self.layout.addWidget(self.label)

        # Crosshair lines
        self.crosshairpen = pg.mkPen(color="#636363", width=2)
        self.vLine = pg.InfiniteLine(angle=90, movable=False, pen=self.crosshairpen)
        self.hLine = pg.InfiniteLine(angle=0, movable=False, pen=self.crosshairpen)
        self.plot_widget.addItem(self.vLine, ignoreBounds=True)
        self.plot_widget.addItem(self.hLine, ignoreBounds=True)
        # Initially hide crosshairs until mouse enters plot or data is shown
        self.vLine.setVisible(False)
        self.hLine.setVisible(False)

        self.plot_widget.scene().sigMouseMoved.connect(self.mouseMoved)

    def _configure(self, background, grid_alpha):
        # Background
        # Ensure background is a string like "#FFFFFF" or a QColor
        self.plot_widget.setBackground(background)

        # Grid
        self.plot_widget.showGrid(x=True, y=True, alpha=grid_alpha)

        # Axis styling
        font = QFont("Times", 10)
        for axis_name in ("bottom", "left"):
            axis = self.plot_widget.getPlotItem().getAxis(axis_name)
            axis.setPen(pg.mkPen(color="#333333", width=1))
            axis.setTextPen(pg.mkPen(color="#333333"))
            axis.setStyle(tickFont=font) # Styles the tick labels
            # For axis titles (e.g., "X Axis", "Y Axis"), if set:
            # label_item = axis.label
            # if hasattr(label_item, 'item') and isinstance(label_item.item, pg.TextItem):
            #     label_item.item.setFont(font)
            # The original self.plot_widget.getAxis("...").label.setFont(font) might work if LabelItem delegates setFont.

    def plot(self, *args, pen=None, **kwargs):
        # Delegate to the PlotItem, using default pen if none provided
        if pen is None:
            pen = self._default_pen
        plot_item = self.plot_widget.getPlotItem().plot(*args, pen=pen, **kwargs)

        # Refresh the crosshair based on current mouse position after new plot item is added
        self.refresh_crosshair()
        return plot_item

    def refresh_crosshair(self):
        """
        Refreshes the crosshair position and label based on the current mouse position
        and the plot data. This should be called when plot data changes.
        """
        if not self.plot_widget.isVisible() or not self.plot_widget.scene():
            self.vLine.setVisible(False)
            self.hLine.setVisible(False)
            self.label.clear()
            return

        global_mouse_pos = QCursor.pos()
        widget_mouse_pos = self.plot_widget.mapFromGlobal(global_mouse_pos)
        scene_mouse_pos = self.plot_widget.mapToScene(widget_mouse_pos)

        self.mouseMoved(scene_mouse_pos)

    def mouseMoved(self, scene_pos: QPointF): # scene_pos is QPointF from sigMouseMoved or mapToScene
        # Convert scene position to local widget coordinates
        local_mouse_pos = self.plot_widget.mapFromScene(scene_pos)

        # Check if the mouse (mapped to local_mouse_pos) is within the plot widget's boundaries
        if self.plot_widget.rect().contains(local_mouse_pos):
            # Convert scene position to viewbox data coordinates
            view_mouse_pos = self.plot_widget.getPlotItem().vb.mapSceneToView(scene_pos)
            x_mouse = view_mouse_pos.x()

            # Retrieve data from the first data item
            items = self.plot_widget.getPlotItem().listDataItems()
            
            # Default state: crosshair at mouse, black label
            self.vLine.setPos(x_mouse)
            self.hLine.setPos(view_mouse_pos.y())
            self.vLine.setVisible(True)
            self.hLine.setVisible(True)
            current_label_text = f"x={x_mouse:.1f},  <span style='color: black'>y={view_mouse_pos.y():.1f}</span>"

            if items:
                data_item = items[0] # Assume crosshair for the first data item
                x_data = data_item.xData
                y_data = data_item.yData

                if x_data is not None and y_data is not None and len(x_data) > 0:
                    if len(x_data) == 1: # Single data point
                        y_plot = y_data[0]
                        self.hLine.setPos(y_plot)
                        current_label_text = f"x={x_mouse:.1f},  <span style='color: red'>y={y_plot:.1f}</span>"
                    
                    elif len(x_data) > 1: # More than one point, attempt interpolation.
                                          # Assumes x_data is ordered (required by np.interp).
                                          # "Regular spacing" is a stronger condition, also fine.
                        
                        x_first = x_data[0]
                        x_last = x_data[-1]

                        # Handle degenerate case where all x_data points are the same
                        if x_first == x_last:
                            # If x_mouse is at this common x_value, np.interp would return y_data[0].
                            # Original code did not show red label here. To maintain that:
                            if x_mouse == x_first: # Mouse is exactly on the identical x-points
                                # To match original behavior of not showing red label for this specific case:
                                pass # Default black label will be used.
                                # If red label was desired:
                                # y_interp = y_data[0] # or some other rule
                                # self.hLine.setPos(y_interp)
                                # current_label_text = f"x={x_mouse:.1f},  <span style='color: red'>y={y_interp:.1f}</span>"
                        elif x_first <= x_mouse <= x_last:
                            # x_mouse is within the data range, perform interpolation
                            y_interp = np.interp(x_mouse, x_data, y_data)
                            self.hLine.setPos(y_interp)
                            current_label_text = f"x={x_mouse:.1f},  <span style='color: red'>y={y_interp:.1f}</span>"
                        # else: x_mouse is outside the [x_first, x_last] range.
                        # The default label (black text, mouse y-coordinate) set earlier will be used.
            # else: no data items, or x_data/y_data is None or empty. Default label applies.
            
            self.label.setText(current_label_text)

        else:
            # Hide crosshair and clear label if mouse is not on the plot
            self.vLine.setVisible(False)
            self.hLine.setVisible(False)
            self.label.clear()