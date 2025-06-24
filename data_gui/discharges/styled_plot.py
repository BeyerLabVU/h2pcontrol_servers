import time
import logging
import pyqtgraph as pg
import numpy as np
from PySide6.QtGui import QFont, QCursor
from PySide6.QtWidgets import QVBoxLayout, QWidget
from PySide6.QtCore import QPointF, QTimer

from bottom_status_bar import BottomStatusBar

import si_prefix

# Set up logger for this module
logger = logging.getLogger(__name__)

# Performance optimization settings
CROSSHAIR_UPDATE_INTERVAL_MS = 20  # Throttle crosshair updates to 50 FPS
PLOT_REFRESH_INTERVAL_MS = 33      # ~30 FPS for plot updates
ENABLE_ANTIALIASING = True         # Enable antialiasing for smoother lines
ENABLE_OPENGL = True               # Use OpenGL acceleration if available

class DynamicSIAxis(pg.AxisItem):
    def __init__(self, orientation, **kwargs):
        super().__init__(orientation, **kwargs)
        self._scale = 1
        self._format = "{:.3f}"

    def set_si_scale(self, scale):
        self._scale = scale

    def tickStrings(self, values, scale, spacing):
        # Format tick labels using the current SI scale
        try:
            strings = []
            for v in values:
                scaled = v / self._scale
                txt = self._format.format(scaled)
                if "." in txt:
                    txt = txt.rstrip("0").rstrip(".")  # Drop trailing zeros/decimal point
                strings.append(txt)
            return strings
        except Exception:
            return [str(v) for v in values]


class StyledPlotWidget(QWidget):
    """A PlotWidget with a shared style (background, grid, axes, default pen)
    wrapped in a QWidget with QVBoxLayout. Now with fixed crosshair behavior.
    """

    UPDATE_INTERVAL_SEC = 0.02  # 20 ms throttle for crosshair updates

    def __init__(self, status_bar: BottomStatusBar, *args, background="#ffffff", grid_alpha=0.3, default_color="#0077bb", **kwargs):
        super().__init__(*args, **kwargs)
        self.main_window_status_bar = status_bar
        self.main_window_status_bar.update_status("Initialized by StyledPlotWidget")
        
        # Setup crosshair update timer for better performance
        self._crosshair_timer = QTimer()
        self._crosshair_timer.setSingleShot(True)
        self._crosshair_timer.timeout.connect(self._update_crosshair)
        self._pending_mouse_pos = None
        self._last_mouse_interaction_time = 0
        self._new_data_received = False  # Flag to track if new data has been received

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        # Use custom SI axes
        self.x_axis = DynamicSIAxis('bottom')
        self.y_axis = DynamicSIAxis('left')
        
        # Configure plot widget with performance optimizations
        if ENABLE_OPENGL:
            try:
                # Try to use OpenGL for hardware acceleration
                pg.setConfigOptions(useOpenGL=True, antialias=ENABLE_ANTIALIASING)
                logger.info("Using OpenGL acceleration for plotting")
            except Exception as e:
                logger.warning(f"Failed to enable OpenGL: {str(e)}")
        
        self.plot_widget = pg.PlotWidget(axisItems={'bottom': self.x_axis, 'left': self.y_axis})
        
        # Configure downsampling for better performance with large datasets
        plot_item = self.plot_widget.getPlotItem()
        plot_item.setDownsampling(auto=True, ds=2)  # ds=2 means downsample by factor of 2
        # Note: setClipToView is not used as it's not available in all PyQtGraph versions
        
        # Set default pen with antialiasing if enabled
        self._default_pen = pg.mkPen(color=default_color, width=2)

        self._x_label_base = "Time"
        self._x_unit_base = "s"
        self._y_label_base = "Voltage"
        self._y_unit_base = "V"
        self.x_axis.enableAutoSIPrefix(False)
        self.y_axis.enableAutoSIPrefix(False)

        self._configure(background, grid_alpha)

        self.layout.addWidget(self.plot_widget)

        self.crosshairpen = pg.mkPen(color="#636363", width=2)
        self.vLine = pg.InfiniteLine(angle=90, movable=False, pen=self.crosshairpen)
        self.hLine = pg.InfiniteLine(angle=0, movable=False, pen=self.crosshairpen)
        self.vLine.setVisible(False)
        self.hLine.setVisible(False)

        # Grab the ViewBox and add crosshairs there:
        self.plot_item = self.plot_widget.getPlotItem()
        self.vb = self.plot_item.vb
        self.vb.addItem(self.vLine, ignoreBounds=True)
        self.vb.addItem(self.hLine, ignoreBounds=True)

        # Attach sigMouseMoved to the ViewBox scene
        self.vb.scene().sigMouseMoved.connect(self.mouseMoved)

        # For storing actual data traces
        self.plot_data_items = []
        self._trace_id_map = {}
        self._data_buffers = {}  # node_id -> {'x': np.array, 'y': np.array}

        # Single timer for updating all plots
        self._plot_update_timer = QTimer()
        self._plot_update_timer.timeout.connect(self.update_all_plots)
        self._plot_update_timer.start(PLOT_REFRESH_INTERVAL_MS)

        # Connect view range change to dynamic axis label/tick update
        self.plot_item.sigRangeChanged.connect(self._update_axis_labels_and_ticks)
        self._update_axis_labels_and_ticks()  # Do an initial labeling

        # Screen saver
        self.screen_saver_trace()

        # Cross hair setting
        self.crosshair_trace_idx = None

    def screen_saver_trace(self):
        t = np.linspace(0, 10e-6, 1000)
        y = 0.1 * np.exp(-t / 3e-6) * np.sin(2 * np.pi * 1e6 * t)
        if not hasattr(self, '_screen_saver_item') or not self._screen_saver_item:
            self._screen_saver_item = self.plot_widget.plot(t, y, pen=self._default_pen, name="Screen Saver Trace")
        else:
            self._screen_saver_item.setData(t, y)
        self._screen_saver_item.setVisible(True)

    def setup_traces(self, num_channels: int, node_ids=None):
        """
        Set up plot traces for the specified number of channels.
        
        This method creates plot items for each channel with performance optimizations:
        - Downsampling for large datasets
        - Clipping to view for better performance
        - Antialiasing for smoother lines
        
        Args:
            num_channels (int): Number of channels to create
            node_ids (list, optional): List of node IDs to associate with each channel
        """
        logger.info(f"Setting up {num_channels} plot traces")
        
        # Hide screen saver if it exists
        if hasattr(self, '_screen_saver_item') and self._screen_saver_item:
            self._screen_saver_item.setVisible(False)

        # Remove existing plot items
        for item in self.plot_data_items:
            self.plot_widget.removeItem(item)
        self.plot_data_items = []
        self._trace_id_map = {}  # node_id -> plot_item

        # Create new plot items with performance optimizations
        colors = ['#0077bb', '#ff0000', '#00ff00', '#ff00ff', '#00ffff', '#ffff00']
        for i in range(num_channels):
            pen_color = colors[i % len(colors)]
            pen = pg.mkPen(color=pen_color, width=2)
            
            # Create plot item with optimizations
            plot_item = self.plot_widget.plot(pen=pen, name=f"Channel {i+1}", 
                                             antialias=ENABLE_ANTIALIASING)
            
            # Enable downsampling for better performance with large datasets
            if hasattr(plot_item, 'setDownsampling'):
                plot_item.setDownsampling(auto=True, ds=2)  # ds=2 means downsample by factor of 2
            
            # Set node ID and add to collections
            node_id = node_ids[i] if node_ids and i < len(node_ids) else f"plot_trace_{i}"
            plot_item.node_id = node_id
            plot_item.setVisible(True)
            self.plot_data_items.append(plot_item)
            self._trace_id_map[node_id] = plot_item
            
        logger.debug(f"Created {len(self.plot_data_items)} plot items")

    def set_trace_visibility(self, node_id, visible: bool):
        """Show or hide a trace by node_id."""
        if hasattr(self, '_trace_id_map') and node_id in self._trace_id_map:
            self._trace_id_map[node_id].setVisible(visible)
            self.refresh_crosshair()
        else:
            print(f"Warning: Tried to set visibility for unknown trace '{node_id}'")

    def update_trace_data(self, node_id: str, x_data, y_data):
        if node_id not in self._trace_id_map:
            # Create a new plot item for this node_id if it doesn't exist
            colors = ['#0077bb', '#ff0000', '#00ff00', '#ff00ff', '#00ffff', '#ffff00']
            color_index = len(self._trace_id_map) % len(colors)
            pen = pg.mkPen(color=colors[color_index], width=2)
            plot_item = self.plot_widget.plot(pen=pen, name=f"Channel {len(self._trace_id_map) + 1}", 
                                             antialias=ENABLE_ANTIALIASING)
            if hasattr(plot_item, 'setDownsampling'):
                plot_item.setDownsampling(auto=True, ds=2)
            plot_item.node_id = node_id
            plot_item.setVisible(True)
            self.plot_data_items.append(plot_item)
            self._trace_id_map[node_id] = plot_item
            logger.info(f"Created new plot item for node_id {node_id}")

        if node_id not in self._data_buffers:
            self._data_buffers[node_id] = {'x': np.array([]), 'y': np.array([])}
        
        self._data_buffers[node_id]['x'] = np.append(self._data_buffers[node_id]['x'], x_data)
        self._data_buffers[node_id]['y'] = np.append(self._data_buffers[node_id]['y'], y_data)

        # Trim buffer
        buffer_size = 10000  # Or get from somewhere else
        if len(self._data_buffers[node_id]['x']) > buffer_size:
            excess = len(self._data_buffers[node_id]['x']) - buffer_size
            self._data_buffers[node_id]['x'] = self._data_buffers[node_id]['x'][excess:]
            self._data_buffers[node_id]['y'] = self._data_buffers[node_id]['y'][excess:]

    def update_all_plots(self):
        for node_id, plot_item in self._trace_id_map.items():
            if node_id in self._data_buffers and plot_item.isVisible():
                buffers = self._data_buffers[node_id]
                plot_item.setData(buffers['x'], buffers['y'])
        self.data_updated()

    def clear_all_traces(self):
        for item in self.plot_data_items:
            self.plot_widget.removeItem(item)
        self.plot_data_items = []
        self._trace_id_map = {}
        if hasattr(self, '_screen_saver_item') and self._screen_saver_item:
            self._screen_saver_item.setVisible(True)
        else:
            self.screen_saver_trace()

    def _configure(self, background, grid_alpha):
        self.plot_widget.setBackground(background)
        self.plot_widget.showGrid(x=True, y=True, alpha=grid_alpha)

        font = QFont("Times", 10)
        for axis_name in ("bottom", "left"):
            axis = self.plot_widget.getAxis(axis_name)
            axis.setTickFont(font)
            axis.setLabel(font=font)

    def plot(self, *args, pen=None, **kwargs):
        if pen is None:
            pen = self._default_pen
        plot_item = self.plot_item.plot(*args, pen=pen, **kwargs)
        self.refresh_crosshair()
        return plot_item

    def data_updated(self):
        """
        To be called when underlying data has changed, to ensure the crosshair
        is updated even if the mouse is stationary.
        """
        self._new_data_received = True
        self.refresh_crosshair()

    def refresh_crosshair(self, use_data_position=False):
        """
        Refresh the crosshair position based on the current mouse position or data.
        
        This method is called when the plot data is updated to ensure the
        crosshair position is updated to reflect the new data. If new data has been
        received, it positions the crosshair at the last data point of the selected
        trace and forces an immediate update ONLY if there has been no recent mouse
        interaction. Otherwise, it uses the mouse position if there has been recent
        interaction, maintaining the last position if no interaction.
        It uses a timer-based approach to throttle updates for better performance.
        """
        if not self.plot_widget.isVisible() or not self.plot_widget.scene():
            return
            
        # Get current mouse position in scene coordinates
        global_mouse_pos = QCursor.pos()
        widget_mouse_pos = self.plot_widget.mapFromGlobal(global_mouse_pos)
        scene_mouse_pos = self.plot_widget.mapToScene(widget_mouse_pos)
        self._pending_mouse_pos = scene_mouse_pos
        
        # Only use data position if explicitly requested
        if use_data_position:
            # Get visible data items to find the last point of the selected trace
            items = self.plot_item.listDataItems()
            visible_items = [item for item in items if item.isVisible() and 
                             item.getData() is not None and 
                             item.getData()[0] is not None and 
                             len(item.getData()[0]) > 0]
            
            if visible_items:
                # Select the appropriate trace for crosshair tracking
                if self.crosshair_trace_idx is not None and 0 <= self.crosshair_trace_idx < len(visible_items):
                    idx = self.crosshair_trace_idx
                else:
                    idx = 0
                    
                # Get data from the selected trace
                item = visible_items[idx]
                x_data, _ = item.getData()
                
                if x_data is not None and len(x_data) > 0:
                    # Use the last data point
                    last_x = x_data[-1]
                    # Map data coordinates to scene coordinates
                    view_pos = self.vb.mapViewToScene(QPointF(last_x, 0))
                    self._pending_mouse_pos = view_pos
                else:
                    # Keep current position if no data
                    pass
            else:
                # Keep current position if no visible items
                pass
            
            # Reset the flag after processing
            if self._new_data_received:
                self._new_data_received = False
        
        # Schedule an update via the timer to prevent multiple updates within the refresh period
        if self._new_data_received or not self._crosshair_timer.isActive():
            if self._crosshair_timer.isActive():
                self._crosshair_timer.stop()  # Stop any pending timer to force immediate update
            self._crosshair_timer.start(0)  # Start with 0ms to trigger immediate update for new data
        else:
            self._crosshair_timer.start(CROSSHAIR_UPDATE_INTERVAL_MS)

    def mouseMoved(self, scene_pos: QPointF):
        """
        Called on every mouse-move over the ViewBox's scene.
        
        This method uses a timer-based throttling approach for better performance.
        Instead of updating the crosshair on every mouse move event, it schedules
        an update to occur after a short delay, which reduces CPU usage while
        maintaining responsive UI.
        
        Args:
            scene_pos (QPointF): The position of the mouse in scene coordinates
        """
        # Store the current mouse position for the next update
        self._pending_mouse_pos = scene_pos
        # Update the last mouse interaction time
        self._last_mouse_interaction_time = time.time() * 1000  # Convert to milliseconds
        
        # If the timer is not already running, start it
        if not self._crosshair_timer.isActive():
            self._crosshair_timer.start(CROSSHAIR_UPDATE_INTERVAL_MS)
    
    def _update_crosshair(self):
        """
        Update the crosshair position and status bar coordinates.
        
        This method is called by the crosshair timer to update the crosshair
        position and status bar coordinates based on the current mouse position.
        It uses binary search for efficient data lookup and linear interpolation
        for accurate cursor position.
        """
        if self._pending_mouse_pos is None:
            return
            
        scene_pos = self._pending_mouse_pos
        
        # Check if the mouse is inside the ViewBox bounding rect
        if not self.vb.sceneBoundingRect().contains(scene_pos):
            # Mouse is outside the plot area
            self.vLine.setVisible(False)
            self.hLine.setVisible(False)
            if self.main_window_status_bar:
                self.main_window_status_bar.clear_coordinates()
            return

        # Map from scene -> data coordinates via the ViewBox
        view_mouse_pos = self.vb.mapSceneToView(scene_pos)
        x_mouse = view_mouse_pos.x()
        y_display = view_mouse_pos.y()

        # Move and show vertical crosshair line
        self.vLine.setPos(x_mouse)
        self.vLine.setVisible(True)

        # Get visible data items for interpolation
        items = self.plot_item.listDataItems()
        visible_items = [item for item in items if item.isVisible() and 
                         item.getData() is not None and 
                         item.getData()[0] is not None and 
                         len(item.getData()[0]) > 0]
        
        # Skip interpolation if no visible items
        if not visible_items:
            if self.main_window_status_bar:
                self.main_window_status_bar.update_coordinates(x_mouse, y_display)
            self.hLine.setPos(y_display)
            self.hLine.setVisible(True)
            return
            
        # Select the appropriate trace for crosshair tracking
        if self.crosshair_trace_idx is not None and 0 <= self.crosshair_trace_idx < len(visible_items):
            idx = self.crosshair_trace_idx
        else:
            idx = 0
            
        # Get data from the selected trace
        item = visible_items[idx]
        x_data, y_data = item.getData()
        
        # Skip interpolation if no data
        if x_data is None or len(x_data) == 0:
            if self.main_window_status_bar:
                self.main_window_status_bar.update_coordinates(x_mouse, y_display)
            self.hLine.setPos(y_display)
            self.hLine.setVisible(True)
            return
            
        # Use binary search to find the closest data point (more efficient)
        idx = np.searchsorted(x_data, x_mouse)
        
        # Interpolate y value
        y_interp = None
        if idx <= 0:
            y_interp = y_data[0]
        elif idx >= len(x_data):
            y_interp = y_data[-1]
        else:
            # Linear interpolation between adjacent points
            x0, x1 = x_data[idx - 1], x_data[idx]
            y0, y1 = y_data[idx - 1], y_data[idx]
            y_interp = y0 + (y1 - y0) * (x_mouse - x0) / (x1 - x0)

        # Update status bar and horizontal crosshair
        if self.main_window_status_bar:
            if (y_interp is not None) and (x_mouse >= x_data[0] and x_mouse <= x_data[-1]):
                self.main_window_status_bar.update_coordinates(x_mouse, y_interp)
                self.hLine.setPos(y_interp * self.y_axis.scale)
            else:
                self.main_window_status_bar.update_coordinates(x_mouse, y_display)
                self.hLine.setPos(y_display)
                
        self.hLine.setVisible(True)

    def get_visible_trace_indices(self):
        """Return indices of currently visible traces."""
        return [i for i, item in enumerate(self.plot_data_items) if item.isVisible()]

    def _update_axis_labels_and_ticks(self):
        plot_item = self.plot_item
        view_range = plot_item.viewRange()
        x_range = view_range[0]
        y_range = view_range[1]

        x_span = abs(x_range[1] - x_range[0])
        y_span = abs(y_range[1] - y_range[0])

        x_str = si_prefix.si_format(x_span, precision=3)
        y_str = si_prefix.si_format(y_span, precision=3)

        def extract_prefix(s):
            parts = s.strip().split(' ')
            if len(parts) == 2:
                return parts[1]
            return ''

        x_prefix = extract_prefix(x_str)
        y_prefix = extract_prefix(y_str)

        def get_factor(prefix):
            if prefix:
                try:
                    return si_prefix.si_parse("1" + prefix)
                except Exception:
                    return 1
            return 1

        x_factor = get_factor(x_prefix)
        y_factor = get_factor(y_prefix)

        x_label = f"{self._x_label_base} [{x_prefix}{self._x_unit_base}]"
        y_label = f"{self._y_label_base} [{y_prefix}{self._y_unit_base}]"
        plot_item.setLabel("bottom", x_label)
        plot_item.setLabel("left", y_label)

        self.x_axis.set_si_scale(x_factor)
        self.y_axis.set_si_scale(y_factor)
