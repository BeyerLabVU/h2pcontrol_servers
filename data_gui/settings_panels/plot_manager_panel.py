from PySide6.QtWidgets import (
    QPushButton, QListWidget, QListWidgetItem, QHBoxLayout,
    QWidget, QColorDialog, QLabel, QMessageBox, QLineEdit,
    QMenu, QInputDialog
)
from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtGui import QColor

from .base_settings_panel import BaseSettingsPanel

# Add tol_colors import
try:
    from tol_colors import tol_cset
except ImportError:
    tol_cset = None

# Constants for QListWidgetItem data roles
# These are used as arguments to item.data() and item.setData()
# Qt.UserRole is often used as a starting point for custom roles (e.g., Qt.UserRole + N)
# but for simplicity and direct replacement of existing integer literals, we define them directly.
NODE_ID_ROLE = 101
VISIBILITY_ROLE = 102
COLOR_ROLE = 103

class PlotManagerPanel(BaseSettingsPanel):
    """
    Control panel for managing PlotNode instances.
    Allows users to create, destroy, and modify plot nodes dynamically.
    """
    # Attribute overrides for BaseSettingsPanel
    PRIORITY = 100
    TITLE = "Plot Traces Manager"
    ERASABLE = True

    # Define signals
    create_plot_node_signal = Signal(str, str)  # color, node_id
    destroy_plot_node_signal = Signal(str)     # node_id
    clear_all_plot_nodes_signal = Signal()
    edit_plot_node_signal = Signal(str)        # node_id
    rename_plot_node_signal = Signal(str, str)  # old_node_id, new_node_id
    trace_order_changed_signal = Signal(list)  # List of node_ids in new order
    trace_visibility_changed_signal = Signal(str, bool)  # node_id, visible
    trace_color_changed_signal = Signal(str, str)  # node_id, new_color
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.trace_counter = 0

        # Use tol-colors 'muted' scheme if available, else fallback
        if tol_cset is not None:
            self.available_colors = [QColor(c).name() for c in tol_cset('muted')]
        else:
            self.available_colors = [
                '#0077bb', '#ff0000', '#00ff00', '#ff00ff', 
                '#00ffff', '#ffff00', '#ff8000', '#8000ff',
                '#80ff00', '#ff0080', '#0080ff', '#80ffff'
            ]
        
        self.setup_ui()
        
        # self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)  # Already set above
        self.adjustSize()

    def setup_ui(self):
        """Set up the user interface components."""
        # List widget to show current plot nodes
        self.plot_nodes_list = QListWidget()
        self.plot_nodes_list.setMaximumHeight(120)
        self.plot_nodes_list.setMinimumHeight(80)
        self.plot_nodes_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.plot_nodes_list.setToolTip("Tip: Use Page Up / Page Down to reorder traces. F2: Rename, F1: Edit, V: Toggle visibility.")
        self.plot_nodes_list.customContextMenuRequested.connect(self.show_context_menu)
        self.plot_nodes_list.installEventFilter(self)
        self.add_setting_row("Active Traces:", self.plot_nodes_list)
        
        # Buttons for managing plot nodes
        buttons_widget = QWidget()
        buttons_layout = QHBoxLayout(buttons_widget)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        
        self.add_trace_btn = QPushButton("Add Trace")
        self.add_trace_btn.clicked.connect(self.add_new_trace)
        
        self.remove_trace_btn = QPushButton("Remove")
        self.remove_trace_btn.clicked.connect(self.remove_selected_trace)
        self.remove_trace_btn.setEnabled(False)
        
        buttons_layout.addWidget(self.add_trace_btn)
        buttons_layout.addWidget(self.remove_trace_btn)
        self.add_setting_row("", buttons_widget)
        
        self.add_separator()
        
        # Color selection for new traces
        color_widget = QWidget()
        color_layout = QHBoxLayout(color_widget)
        color_layout.setContentsMargins(0, 0, 0, 0)

        self.color_preview = QLabel("    ")
        self.color_preview.setStyleSheet("background-color: #0077bb; border: 1px solid black;")
        self.selected_color = "#0077bb"

        self.color_btn = QPushButton("Choose Color")
        self.color_btn.clicked.connect(self.choose_color)

        color_layout.addWidget(self.color_preview)
        color_layout.addWidget(self.color_btn)
        self.add_setting_row("New Trace Color:", color_widget)

        # Name entry for new trace (on its own row)
        self.name_entry = QLineEdit()
        self.name_entry.setPlaceholderText("Trace name (optional)")
        self.add_setting_row("New Trace Name:", self.name_entry)
        
        self.add_separator()
        
        # Clear all button
        self.clear_all_btn = QPushButton("Clear All Traces")
        self.clear_all_btn.clicked.connect(self.clear_all_traces)
        self.clear_all_btn.setStyleSheet("QPushButton { background-color: #ff4444; color: white; }")
        self.add_setting_row("", self.clear_all_btn)
        
        # Connect list selection change
        self.plot_nodes_list.itemSelectionChanged.connect(self.on_selection_changed)

    @Slot()
    def add_new_trace(self):
        """Add a new plot trace."""
        # Get name from entry, fallback to default if empty or duplicate
        name = self.name_entry.text().strip()
        if name and any(self.plot_nodes_list.item(i).data(NODE_ID_ROLE) == name for i in range(self.plot_nodes_list.count())):
            QMessageBox.warning(
                self,
                "Duplicate Trace Name",
                f"A trace named '{name}' already exists. Please choose a different name."
            )
            return

        node_id = name if name else f"plot_trace_{self.trace_counter}"
        self.trace_counter += 1

        # Use selected color or pick next available color from tol-colors
        color = self.selected_color
        current_count = self.plot_nodes_list.count()
        if not color or color == "#000000":
            color = self.available_colors[current_count % len(self.available_colors)]

        self.create_plot_node_signal.emit(color, node_id)
        self.add_trace_to_list(node_id, color)
        print(f"Requested creation of trace: {node_id} with color {color}")

        # Optionally clear the name entry after adding
        self.name_entry.clear()

        # --- Set color to next in sequence after adding a trace ---
        next_index = (current_count + 1) % len(self.available_colors)
        next_color = self.available_colors[next_index]
        self.selected_color = next_color
        self.color_preview.setStyleSheet(f"background-color: {self.selected_color}; border: 1px solid black;")

    @Slot()
    def remove_selected_trace(self):
        """Remove the currently selected plot trace."""
        current_item = self.plot_nodes_list.currentItem()
        if not current_item:
            return
        
        node_id = current_item.data(NODE_ID_ROLE)  # Stored node ID
        
        # Confirm deletion
        reply = QMessageBox.question(
            self,
            "Remove Trace",
            f"Are you sure you want to remove trace '{node_id}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Emit signal to destroy the plot node
            self.destroy_plot_node_signal.emit(node_id)
            
            # Remove from list
            row = self.plot_nodes_list.row(current_item)
            self.plot_nodes_list.takeItem(row)
            
            print(f"Requested removal of trace: {node_id}")

    @Slot()
    def clear_all_traces(self):
        """Remove all plot traces."""
        if self.plot_nodes_list.count() == 0:
            return
        
        # Confirm deletion
        reply = QMessageBox.question(
            self,
            "Clear All Traces",
            "Are you sure you want to remove all traces?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Emit signal to clear all plot nodes
            self.clear_all_plot_nodes_signal.emit()
            
            # Clear the list
            self.plot_nodes_list.clear()
            
            print("Requested removal of all traces")

    @Slot()
    def choose_color(self):
        """Open color dialog to choose trace color."""
        color = QColorDialog.getColor(QColor(self.selected_color), self, "Choose Trace Color")
        if color.isValid():
            self.selected_color = color.name()
            self.color_preview.setStyleSheet(f"background-color: {self.selected_color}; border: 1px solid black;")

    @Slot()
    def on_selection_changed(self):
        """Handle list selection changes."""
        has_selection = bool(self.plot_nodes_list.currentItem())
        self.remove_trace_btn.setEnabled(has_selection)

    def add_trace_to_list(self, node_id: str, color: str, visible: bool = True):
        """Add a trace to the display list."""
        item = QListWidgetItem() # Create item first
        item.setData(NODE_ID_ROLE, node_id)  # Store node ID for reference
        item.setData(VISIBILITY_ROLE, visible)  # Store visibility state
        item.setData(COLOR_ROLE, color)    # Store original color string
        
        color_label = "●"  # Bullet point
        item.setText(f"{color_label} {node_id}")

        try:
            # 1. Set Font Style
            font = item.font()
            font.setItalic(not visible) # Italic if not visible
            item.setFont(font)

            # 2. Set Color
            item_color_qobject = QColor() # Default to an invalid QColor

            if visible:
                if color: # Ensure color string is not None or empty
                    item_color_qobject = QColor(color)
                if not item_color_qobject.isValid(): # Fallback if original color string is bad or empty
                    item_color_qobject = QColor("#0077bb") 
            else: # Not visible
                item_color_qobject = QColor('#888888')
            
            item.setForeground(item_color_qobject)

        except Exception:
            # Silently pass if styling fails, to avoid crashing UI.
            # Consider logging this in a real application.
            pass
        
        self.plot_nodes_list.addItem(item)

    def remove_trace_from_list(self, node_id: str):
        """Remove a trace from the display list by node_id."""
        for i in range(self.plot_nodes_list.count()):
            item = self.plot_nodes_list.item(i)
            if item and item.data(NODE_ID_ROLE) == node_id:
                self.plot_nodes_list.takeItem(i)
                break

    def sync_with_plot_nodes(self, plot_nodes_dict):
        """Synchronize the list display with actual plot nodes."""
        self.plot_nodes_list.clear()
        for node_id, plot_node in plot_nodes_dict.items():
            color = getattr(plot_node, 'trace_color', '#0077bb')
            visible = getattr(plot_node, 'visible', True)
            self.add_trace_to_list(node_id, color, visible)
        
        # Update trace counter to avoid conflicts
        if plot_nodes_dict:
            # Extract numbers from existing node IDs to set counter appropriately
            max_num = 0
            for node_id in plot_nodes_dict.keys():
                if node_id.startswith('plot_trace_'):
                    try:
                        num = int(node_id.split('_')[-1])
                        max_num = max(max_num, num)
                    except ValueError:
                        pass
            self.trace_counter = max_num + 1

    def show_context_menu(self, pos):
        item = self.plot_nodes_list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self.plot_nodes_list)
        edit_action = menu.addAction("Edit Node (F1)")
        rename_action = menu.addAction("Rename Trace (F2)")
        
        # Add visibility toggle action
        current_visible = item.data(VISIBILITY_ROLE)
        visibility_text = "Hide Trace (V)" if current_visible else "Show Trace (V)"
        visibility_action = menu.addAction(visibility_text)
        
        # Add color change action
        change_color_action = menu.addAction("Change Color (C)")
        
        action = menu.exec_(self.plot_nodes_list.mapToGlobal(pos))
        if action == rename_action:
            self.rename_trace(item)
        elif action == edit_action:
            node_id = item.data(NODE_ID_ROLE)
            self.edit_plot_node_signal.emit(node_id)
        elif action == visibility_action:
            self.toggle_trace_visibility(item)
        elif action == change_color_action:
            self.change_trace_color(item)

    def eventFilter(self, obj, event):
        if obj is self.plot_nodes_list and event.type() == 6:  # 6 == QEvent.KeyPress
            key = event.key()
            if key == Qt.Key.Key_F2:
                current_item = self.plot_nodes_list.currentItem()
                if current_item:
                    self.rename_trace(current_item)
                    return True
            elif key == Qt.Key.Key_F1:
                current_item = self.plot_nodes_list.currentItem()
                if current_item:
                    node_id = current_item.data(NODE_ID_ROLE)
                    self.edit_plot_node_signal.emit(node_id)
                    return True
            elif key == Qt.Key.Key_PageUp:
                current_row = self.plot_nodes_list.currentRow()
                if current_row > 0:
                    item = self.plot_nodes_list.takeItem(current_row)
                    self.plot_nodes_list.insertItem(current_row - 1, item)
                    self.plot_nodes_list.setCurrentItem(item)
                    self.emit_trace_order_changed()
                return True
            elif key == Qt.Key.Key_PageDown:
                current_row = self.plot_nodes_list.currentRow()
                if 0 <= current_row < self.plot_nodes_list.count() - 1:
                    item = self.plot_nodes_list.takeItem(current_row)
                    self.plot_nodes_list.insertItem(current_row + 1, item)
                    self.plot_nodes_list.setCurrentItem(item)
                    self.emit_trace_order_changed()
                return True
            elif key == Qt.Key.Key_Delete or key == Qt.Key.Key_Backspace:
                current_item = self.plot_nodes_list.currentItem()
                if current_item:
                    self.remove_selected_trace()
                    return True
            elif key == Qt.Key.Key_V:
                current_item = self.plot_nodes_list.currentItem()
                if current_item:
                    self.toggle_trace_visibility(current_item)
                    return True
            elif key == Qt.Key.Key_C:
                current_item = self.plot_nodes_list.currentItem()
                if current_item:
                    self.change_trace_color(current_item)
                    return True
        return super().eventFilter(obj, event)

    def emit_trace_order_changed(self):
        """Emit the new order of trace node IDs for z-ordering in the plot widget."""
        if hasattr(self, 'trace_order_changed_signal'):
            order = [self.plot_nodes_list.item(i).data(NODE_ID_ROLE) for i in range(self.plot_nodes_list.count())]
            self.trace_order_changed_signal.emit(order)

    def rename_trace(self, item):
        old_id = item.data(NODE_ID_ROLE)
        # Use QLineEdit.EchoMode.Normal for echo mode
        from PySide6.QtWidgets import QLineEdit
        new_id, ok = QInputDialog.getText(self, "Rename Trace", "Enter new trace name:", QLineEdit.EchoMode.Normal, old_id)
        if ok:
            new_id = new_id.strip()
            if not new_id:
                QMessageBox.warning(self, "Invalid Name", "Trace name cannot be empty.")
                return
            # Check for duplicates
            for i in range(self.plot_nodes_list.count()):
                if i == self.plot_nodes_list.row(item):
                    continue
                if self.plot_nodes_list.item(i).data(NODE_ID_ROLE) == new_id:
                    QMessageBox.warning(self, "Duplicate Name", f"A trace named '{new_id}' already exists.")
                    return
            # Update item
            item.setData(NODE_ID_ROLE, new_id) # Store the new_id as the ID
            color_label = "●"
            item.setText(f"{color_label} {new_id}") # Update display text
            # Emit signal to propagate the rename to MainWindow
            self.rename_plot_node_signal.emit(old_id, new_id)

    def change_trace_color(self, item):
        """Change the color of a trace."""
        node_id = item.data(NODE_ID_ROLE)
        current_color = item.data(COLOR_ROLE)
        
        # Open color dialog
        color = QColorDialog.getColor(QColor(current_color), self, "Choose Trace Color")
        if color.isValid():
            new_color = color.name()
            
            # Update item data
            item.setData(COLOR_ROLE, new_color)
            
            # Update item appearance
            if item.data(VISIBILITY_ROLE):  # Only update color if trace is visible
                item.setForeground(color)
            
            # Emit signal to update the actual trace color
            self.trace_color_changed_signal.emit(node_id, new_color)
            print(f"Changed color for trace {node_id} to {new_color}")
    
    def toggle_trace_visibility(self, item):
        """Toggle the visibility of a trace."""
        node_id = item.data(NODE_ID_ROLE)
        current_is_visible = item.data(VISIBILITY_ROLE) # Current visibility state from data
        original_color_str = item.data(COLOR_ROLE) # Retrieve stored original color string

        new_is_visible = not current_is_visible # Calculate new state
        item.setData(VISIBILITY_ROLE, new_is_visible) # Store the new state
        
        color_label = "●" # Ensure we use the same prefix

        try:
            # 1. Set Font Style
            font = item.font()
            font.setItalic(not new_is_visible) # Italic if item is now hidden
            item.setFont(font)

            # 2. Set Color
            text_color_qobject = QColor() # Default to an invalid QColor

            if new_is_visible:
                if original_color_str: # Check if there's an original color string
                    text_color_qobject = QColor(original_color_str)
                    print(f"Toggling visibility for {node_id} to visible with color {original_color_str}")
                
                # Fallback if original_color_str was None, empty, or an invalid color format
                if not text_color_qobject.isValid():
                    text_color_qobject = QColor("#0077bb") # Default to blue
            else: # Item is now hidden
                text_color_qobject = QColor('#888888') # Grey out
                print(f"Toggling visibility for {node_id} to hidden, setting color to grey")
            
            item.setForeground(text_color_qobject)

        except Exception:
            # Silently pass if styling fails.
            # Consider logging this.
            pass
        
        # Explicitly re-set the text to ensure it's correct.
        item.setText(f"{color_label} {node_id}")
        
        self.trace_visibility_changed_signal.emit(node_id, new_is_visible)
