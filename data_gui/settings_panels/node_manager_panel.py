from PySide6.QtWidgets import (
    QPushButton, QListWidget, QListWidgetItem, QHBoxLayout,
    QWidget, QLabel, QMessageBox, QMenu, QInputDialog
)
from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtGui import QColor

from .base_settings_panel import BaseSettingsPanel

# Constants for QListWidgetItem data roles
NODE_ID_ROLE = 101
NODE_TYPE_ROLE = 102

class NodeManagerPanel(BaseSettingsPanel):
    """
    Control panel for managing Node instances.
    Allows users to browse existing nodes and open the node editor.
    """
    # Attribute overrides for BaseSettingsPanel
    PRIORITY = 90  # Just below PlotManagerPanel (100)
    TITLE = "Node Manager"
    ERASABLE = True

    # Define signals
    edit_node_signal = Signal(str)  # node_id
    
    def __init__(self, pipeline_graph, parent=None):
        super().__init__(parent)
        self.pipeline_graph = pipeline_graph
        self.setup_ui()
        
        self.adjustSize()

    def setup_ui(self):
        """Set up the user interface components."""
        # List widget to show current nodes
        self.nodes_list = QListWidget()
        self.nodes_list.setMaximumHeight(120)
        self.nodes_list.setMinimumHeight(80)
        self.nodes_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.nodes_list.setToolTip("Tip: Double-click to edit a node. F1: Edit node.")
        self.nodes_list.customContextMenuRequested.connect(self.show_context_menu)
        self.nodes_list.itemDoubleClicked.connect(self.edit_selected_node)
        self.nodes_list.installEventFilter(self)
        self.add_setting_row("Available Nodes:", self.nodes_list)
        
        # Buttons for managing nodes
        buttons_widget = QWidget()
        buttons_layout = QHBoxLayout(buttons_widget)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        
        self.edit_node_btn = QPushButton("Edit Node")
        self.edit_node_btn.clicked.connect(self.edit_selected_node)
        self.edit_node_btn.setEnabled(False)
        
        buttons_layout.addWidget(self.edit_node_btn)
        self.add_setting_row("", buttons_widget)
        
        self.add_separator()
        
        # Connect list selection change
        self.nodes_list.itemSelectionChanged.connect(self.on_selection_changed)
        
        # Initial sync with pipeline graph
        self.sync_with_pipeline_graph()

    @Slot()
    def edit_selected_node(self):
        """Edit the currently selected node."""
        current_item = self.nodes_list.currentItem()
        if not current_item:
            return
        
        node_id = current_item.data(NODE_ID_ROLE)
        self.edit_node_signal.emit(node_id)

    @Slot()
    def on_selection_changed(self):
        """Handle list selection changes."""
        has_selection = bool(self.nodes_list.currentItem())
        self.edit_node_btn.setEnabled(has_selection)

    def add_node_to_list(self, node_id: str, node_type: str):
        """Add a node to the display list."""
        item = QListWidgetItem()
        item.setData(NODE_ID_ROLE, node_id)
        item.setData(NODE_TYPE_ROLE, node_type)
        
        # Set display text with node type in parentheses
        item.setText(f"{node_id} ({node_type})")
        
        # Set color based on node type
        if "plot" in node_type.lower():
            item.setForeground(QColor("#0077bb"))  # Blue for plot nodes
        elif "catchment" in node_type.lower():
            item.setForeground(QColor("#009988"))  # Teal for catchment nodes
        elif "discharge" in node_type.lower():
            item.setForeground(QColor("#ee7733"))  # Orange for discharge nodes
        elif "operator" in node_type.lower():
            item.setForeground(QColor("#cc3311"))  # Red for operator nodes
        
        self.nodes_list.addItem(item)

    def sync_with_pipeline_graph(self):
        """Synchronize the list display with actual nodes in the pipeline graph."""
        self.nodes_list.clear()
        for node_id, node in self.pipeline_graph.nodes.items():
            node_type = getattr(node, 'node_type', 'unknown')
            self.add_node_to_list(node_id, node_type)

    def show_context_menu(self, pos):
        """Show context menu for node list items."""
        item = self.nodes_list.itemAt(pos)
        if not item:
            return
        
        menu = QMenu(self.nodes_list)
        edit_action = menu.addAction("Edit Node (F1)")
        
        action = menu.exec_(self.nodes_list.mapToGlobal(pos))
        if action == edit_action:
            node_id = item.data(NODE_ID_ROLE)
            self.edit_node_signal.emit(node_id)

    def eventFilter(self, obj, event):
        """Handle key press events for the nodes list."""
        if obj is self.nodes_list and event.type() == 6:  # 6 == QEvent.KeyPress
            key = event.key()
            if key == Qt.Key.Key_F1:
                current_item = self.nodes_list.currentItem()
                if current_item:
                    node_id = current_item.data(NODE_ID_ROLE)
                    self.edit_node_signal.emit(node_id)
                    return True
            elif key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
                current_item = self.nodes_list.currentItem()
                if current_item:
                    self.edit_selected_node()
                    return True
        return super().eventFilter(obj, event)
