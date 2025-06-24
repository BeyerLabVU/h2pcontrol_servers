import os
import json
import inspect
import importlib.util
import ast
from typing import List, Dict, Any, Optional

from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QSpinBox,
    QComboBox,
    QPlainTextEdit,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QFileDialog,
    QMessageBox,
    QListWidget,
    QListWidgetItem,
)
from PySide6.QtCore import Qt, Slot
from data_node import PipelineGraph

class NodeDialog(QDialog):
    """
    A QDialog that can operate in two modes:
      - mode="add":  create a brand‐new Node
      - mode="edit": pick an existing node via QSpinBox and edit its operator + params.

    In both modes, you can choose a Python file from the 'operators/' directory
    (via a QComboBox) and supply a JSON blob for "params".  On accept(), we store
    everything in self.result_data = { "id": ..., "operator_file": ..., "params": {...} }.
    """

    def __init__(self,
                 pipeline: 'PipelineGraph',
                 mode: str = "add",
                 parent=None):
        super().__init__(parent)
        if mode not in ("add", "edit"):
            raise ValueError("mode must be 'add' or 'edit'")
        self.pipeline = pipeline
        self.mode = mode
        self.setWindowModality(Qt.ApplicationModal) # type: ignore
        self.setMinimumWidth(400)
        self.setWindowTitle("Add Node" if mode == "add" else "Edit Node")

        # We'll store the final dictionary of values here:
        self.result_data: Dict[str, Any] = {}

        # BUILD UI
        main_layout = QVBoxLayout(self)
        self.node_index_label = QLabel("Select node index:")
        self.node_index_spin = QSpinBox()
        self.node_index_spin.setMinimum(0)
        self.node_index_spin.setSingleStep(1)
        self.node_index_spin.valueChanged.connect(self._on_index_changed)

        if self.mode == "edit":
            # Build a list of current node IDs
            self.node_ids: List[str] = list(self.pipeline.nodes.keys())
            n = len(self.node_ids)
            if n == 0:
                # If there are no nodes at all, then disable the dialog entirely:
                self.node_index_spin.setMaximum(0)
                msg = QLabel("<i>(No nodes exist yet.  Create one first.)</i>")
                msg.setEnabled(False)
                main_layout.addWidget(self.node_index_label)
                main_layout.addWidget(self.node_index_spin)
                main_layout.addWidget(msg)
                # We still build the rest of the fields, but gray them out:
            else:
                self.node_index_spin.setMaximum(n - 1)

            main_layout.addWidget(self.node_index_label)
            main_layout.addWidget(self.node_index_spin)
        else:
            # Hide in add mode:
            self.node_index_label.hide()
            self.node_index_spin.hide()

        # Node ID: either type a new one, or read‐only if editing
        self.id_label = QLabel("Node ID:")
        self.id_edit = QLineEdit()
        if self.mode == "edit":
            self.id_edit.setReadOnly(True)
        main_layout.addWidget(self.id_label)
        main_layout.addWidget(self.id_edit)

        # Choose an operator‐file from operators/ directory
        self.opfile_label = QLabel("Operator file:")
        self.opfile_combo = QComboBox()
        self._populate_operator_files()
        self.opfile_combo.currentIndexChanged.connect(self._on_operator_file_changed)

        # Also allow “Browse…” in case user wants to pick an external file
        self.browse_btn = QPushButton("Browse…")
        self.browse_btn.clicked.connect(self._on_browse)
        op_layout = QHBoxLayout()
        op_layout.addWidget(self.opfile_combo, stretch=1)
        op_layout.addWidget(self.browse_btn, stretch=0)
        main_layout.addWidget(self.opfile_label)
        main_layout.addLayout(op_layout)

        # Params (JSON) in a QPlainTextEdit
        self.params_label = QLabel("Params (JSON):")
        self.params_edit = QPlainTextEdit()
        self.params_edit.setPlaceholderText('e.g. { "window": 256, "thresh": 0.5 }')
        main_layout.addWidget(self.params_label)
        main_layout.addWidget(self.params_edit, stretch=1)

        # Input Nodes Selection
        self.inputs_label = QLabel("Input Nodes (select from list):")
        self.inputs_list = QListWidget()
        self.inputs_list.setSelectionMode(QListWidget.SingleSelection) # type: ignore
        self._set_input_node_checkboxes()

        # Connect the item changed signal to handle input node selection
        self.inputs_list.itemChanged.connect(self._on_input_node_changed)
        main_layout.addWidget(self.inputs_label)
        main_layout.addWidget(self.inputs_list, stretch=1) # Add some stretch

        # OK / Cancel buttons at bottom
        btn_layout = QHBoxLayout()
        self.ok_btn = QPushButton("OK")
        self.cancel_btn = QPushButton("Cancel")
        self.ok_btn.clicked.connect(self._on_accept)
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch(1)
        btn_layout.addWidget(self.ok_btn)
        btn_layout.addWidget(self.cancel_btn)
        main_layout.addLayout(btn_layout)

        # If in edit mode and there is at least one node, preload the fields from index=0
        if self.mode == "edit" and len(getattr(self, "node_ids", [])) > 0:
            self.node_index_spin.setValue(0)
            self._load_node_into_fields(0) # This will also populate inputs
        elif self.mode == "add":
            self._populate_input_nodes_list() # Populate for "add" mode

    def _populate_operator_files(self):
        self.opfile_combo.clear()
        operators_dir = os.path.join(os.getcwd(), "operators")
        try:
            files = [
                f for f in os.listdir(operators_dir)
                if f.endswith(".py") and os.path.isfile(os.path.join(operators_dir, f))
            ]
        except FileNotFoundError:
            files = []

        # Sort alphabetically
        files.sort()
        # If empty, put a placeholder "(no operators found)"
        if not files:
            self.opfile_combo.addItem("(no operators/ found)")
            self.opfile_combo.setEnabled(False)
        else:
            self.opfile_combo.setEnabled(True)
            for fname in files:
                self.opfile_combo.addItem(fname)
                
        # Auto-detect parameters for the first file if available
        if files and self.mode == "add":
            self._auto_detect_parameters(os.path.join(operators_dir, files[0]))

    def _populate_input_nodes_list(self, current_node_id_to_exclude: str = ""):
        self.inputs_list.clear()
        
        all_node_ids = list(self.pipeline.nodes.keys())
        
        available_input_ids = [
            nid for nid in all_node_ids 
            if nid != current_node_id_to_exclude
        ]
        
        if not available_input_ids:
            item = QListWidgetItem("(no other nodes available to connect)")
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable & ~Qt.ItemIsUserCheckable) # type: ignore # Make it unselectable
            self.inputs_list.addItem(item)
            self.inputs_list.setEnabled(False)
        else:
            self.inputs_list.setEnabled(True)
            for node_id_option in available_input_ids:
                item = QListWidgetItem(node_id_option)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable) # type: ignore
                item.setCheckState(Qt.Unchecked) # type: ignore
                
                # Check if connecting this node would create a cycle
                if current_node_id_to_exclude and self.pipeline.would_create_cycle(node_id_option, current_node_id_to_exclude):
                    # Gray out the item and make it unselectable
                    item.setFlags(item.flags() & ~Qt.ItemIsEnabled) # type: ignore
                    item.setText(f"{node_id_option} (would create cycle)")
                    item.setForeground(Qt.gray) # type: ignore
                
                self.inputs_list.addItem(item)

    def _auto_detect_parameters(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Analyze a Python file to detect parameters and generate a default JSON configuration.
        """
        if not os.path.exists(file_path):
            return None
            
        try:
            # Try to load the module and inspect it
            module_name = f"temp_module_{hash(file_path)}"
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                return None
                
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Look for Node subclasses
            from data_node import Node
            node_classes = [
                obj for name, obj in inspect.getmembers(module, inspect.isclass)
                if issubclass(obj, Node) and obj is not Node
            ]
            
            if not node_classes:
                # If no Node subclasses found, try to parse the file for __init__ parameters
                return self._parse_init_params(file_path)
                
            # Use the first Node subclass found
            node_class = node_classes[0]
            
            # Get the __init__ signature
            init_signature = inspect.signature(node_class.__init__)
            
            # Extract parameters (excluding self, node_id, node_type, loop)
            params = {}
            for param_name, param in init_signature.parameters.items():
                if param_name not in ['self', 'node_id', 'node_type', 'loop']:
                    # Get default value if available
                    if param.default is not param.empty:
                        params[param_name] = param.default
                    else:
                        # Use specific defaults for known parameters or based on annotation
                        if param_name == 'window':
                            params[param_name] = 256
                        elif param.annotation is not param.empty:
                            if param.annotation == int:
                                params[param_name] = 0
                            elif param.annotation == float:
                                params[param_name] = 0.0
                            elif param.annotation == bool:
                                params[param_name] = False
                            elif param.annotation == str:
                                params[param_name] = ""
                            elif param.annotation == list or param.annotation == List:
                                params[param_name] = []
                            elif param.annotation == dict or param.annotation == Dict:
                                params[param_name] = {}
                        else:
                            params[param_name] = None
            
            # Update the params text field
            if params:
                self.params_edit.setPlainText(json.dumps(params, indent=2))
                return params
                
        except Exception as e:
            print(f"Error auto-detecting parameters: {e}")
            
        return None
        
    def _parse_init_params(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Parse the Python file using AST to extract __init__ parameters.
        """
        try:
            with open(file_path, 'r') as f:
                tree = ast.parse(f.read())
                
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    # Look for __init__ method
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                            params = {}
                            for arg in item.args.args:
                                if arg.arg not in ['self', 'node_id', 'node_type', 'loop']:
                                    if arg.arg == 'window':
                                        params[arg.arg] = 256
                                    else:
                                        params[arg.arg] = None
                                    
                            # Look for default assignments in the method body
                            for stmt in item.body:
                                if isinstance(stmt, ast.Assign):
                                    if isinstance(stmt.targets[0], ast.Attribute):
                                        target = stmt.targets[0]
                                        if isinstance(target.value, ast.Name) and target.value.id == 'self':
                                            attr_name = target.attr
                                            if attr_name.startswith('_'):
                                                attr_name = attr_name[1:]  # Remove leading underscore
                                            
                                            # Try to get the value
                                            if isinstance(stmt.value, ast.Constant):
                                                params[attr_name] = stmt.value.value
                                            elif isinstance(stmt.value, ast.List):
                                                params[attr_name] = []
                                            elif isinstance(stmt.value, ast.Dict):
                                                params[attr_name] = {}
                                                
                            # Update the params text field
                            if params:
                                self.params_edit.setPlainText(json.dumps(params, indent=2))
                                return params
                                
        except Exception as e:
            print(f"Error parsing file for parameters: {e}")
            
        return None
    
    @Slot(int)
    def _on_operator_file_changed(self, index: int):
        """Handle operator file selection change."""
        if index < 0 or not self.opfile_combo.isEnabled():
            return
            
        file_name = self.opfile_combo.currentText()
        if file_name == "(no operators/ found)":
            return
            
        # Check if it's a relative path or absolute path
        if os.path.isabs(file_name):
            file_path = file_name
        else:
            file_path = os.path.join(os.getcwd(), "operators", file_name)
            
        # Auto-detect parameters
        self._auto_detect_parameters(file_path)

    @Slot()
    def _on_browse(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select operator‐file",
            os.path.join(os.getcwd(), "operators"),
            "Python files (*.py);;All files (*)"
        )
        if file_path:
            # If it's inside ./operators/, show only the filename; otherwise show the full path.
            base = os.path.basename(file_path)
            operators_dir = os.path.join(os.getcwd(), "operators")
            if file_path.startswith(operators_dir):
                self.opfile_combo.setEditable(True)
                self.opfile_combo.clear()
                self.opfile_combo.addItem(base)
            else:
                # external path: store full absolute path
                self.opfile_combo.setEditable(True)
                self.opfile_combo.clear()
                self.opfile_combo.addItem(file_path)
                
            # Auto-detect parameters for the selected file
            self._auto_detect_parameters(file_path)

    @Slot(int)
    def _on_index_changed(self, idx: int):
        self._load_node_into_fields(idx)
        
        # Refresh the input nodes list to update cycle detection for the new selected node
        if hasattr(self, 'node_ids') and idx < len(self.node_ids):
            current_node_id = self.node_ids[idx]
            self._populate_input_nodes_list(current_node_id_to_exclude=current_node_id)
            
            # Re-check the currently connected inputs for this node
            if current_node_id in self.pipeline.nodes:
                current_node = self.pipeline.nodes[current_node_id]
                current_inputs = getattr(current_node, 'inputs', [])
                
                for i in range(self.inputs_list.count()):
                    item = self.inputs_list.item(i)
                    if item and item.flags() & Qt.ItemIsEnabled:  # type: ignore # Only check enabled items
                        # Get the node ID from the item text
                        node_text = item.text()
                        if " (would create cycle)" in node_text:
                            node_text = node_text.replace(" (would create cycle)", "")
                        
                        if node_text.strip() in current_inputs:
                            item.setCheckState(Qt.Checked) # type: ignore
                        else:
                            item.setCheckState(Qt.Unchecked) # type: ignore
        self._set_input_node_checkboxes()

    def _load_node_into_fields(self, idx: int):
        try:
            node_id = self.node_ids[idx]
        except (AttributeError, IndexError):
            # This can happen if node_ids is not yet populated or idx is out of bounds.
            # Clear fields or set to a default state.
            self.id_edit.clear()
            self.opfile_combo.setCurrentIndex(-1) # Or clear if editable
            if self.opfile_combo.isEditable():
                self.opfile_combo.clearEditText()
            self.params_edit.clear()
            self._populate_input_nodes_list() # Populate with all nodes, as no specific node is being edited yet
            return

        node = self.pipeline.nodes[node_id]
        # 1) Node ID
        self.id_edit.setText(node.id)

        # Populate input nodes list, excluding the current node itself
        self._populate_input_nodes_list(current_node_id_to_exclude=node.id)
 
        # We assume node.params has a key "operator_file" pointing to either just filename or full path.
        opf = node.params.get("operator_file", "")
        if opf and self.opfile_combo.isEnabled():
            # if the file exactly matches one of the items in the combo, select it
            i = self.opfile_combo.findText(opf)
            if i >= 0:
                self.opfile_combo.setCurrentIndex(i)
            else:
                # put it in the editable line
                self.opfile_combo.setEditable(True)
                self.opfile_combo.clear()
                self.opfile_combo.addItem(opf)
        try:
            text = json.dumps(node.params, indent=2)
        except Exception:
            text = "{}"
        self.params_edit.setPlainText(text)

        # Temporarily disconnect signal to avoid triggering during setup
        self.inputs_list.itemChanged.disconnect(self._on_input_node_changed)
        
        current_inputs = getattr(node, 'inputs', []) # Assuming node.inputs is a list of input node IDs
        for i in range(self.inputs_list.count()):
            item = self.inputs_list.item(i)
            if item and item.flags() & Qt.ItemIsEnabled:  # type: ignore # Only check enabled items
                # Get the node ID from the item text (remove any suffix)
                node_text = item.text()
                if " (would create cycle)" in node_text:
                    node_text = node_text.replace(" (would create cycle)", "")
                
                if node_text.strip() in current_inputs:
                    item.setCheckState(Qt.Checked) # type: ignore
                else:
                    item.setCheckState(Qt.Unchecked) # type: ignore
        
        # Reconnect signal
        self.inputs_list.itemChanged.connect(self._on_input_node_changed)


    @Slot()
    def _on_accept(self):
        node_id = self.id_edit.text().strip()
        if not node_id:
            QMessageBox.warning(self, "Error", "Node ID cannot be empty.")
            return

        # 1) operator_file field
        opf = self.opfile_combo.currentText().strip()
        if not opf or opf == "(no operators/ found)":
            QMessageBox.warning(self, "Error", "Please choose a valid operator file.")
            return

        # 2) params JSON
        raw = self.params_edit.toPlainText().strip()
        if not raw:
            params_dict = {}
        else:
            try:
                params_dict = json.loads(raw)
                if not isinstance(params_dict, dict):
                    raise ValueError("params must be a JSON object")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Invalid JSON in params:\n{e}")
                return

        # 3) Selected Input Nodes
        selected_inputs = []
        if self.inputs_list.isEnabled(): # Only collect if the list is enabled
            for i in range(self.inputs_list.count()):
                item = self.inputs_list.item(i)
                if item.checkState() == Qt.Checked: # type: ignore
                    selected_inputs.append(item.text())
        
        # Now build result_data
        self.result_data["id"] = node_id
        self.result_data["operator_file"] = opf
        self.result_data["params"] = params_dict
        self.result_data["inputs"] = selected_inputs

        # If in edit mode, we should also pass back which index was chosen
        if self.mode == "edit":
            self.result_data["index"] = self.node_index_spin.value()

        self.accept()  # close dialog with QDialog.Accepted

    def get_results(self) -> Dict[str, Any]:
        return self.result_data

    @Slot(QListWidgetItem)
    def _on_input_node_changed(self, item: QListWidgetItem):
        if not item or not self.inputs_list.isEnabled():
            return
            
        # Get the node ID from the item text (remove any suffix like "(would create cycle)")
        node_text = item.text()
        if " (would create cycle)" in node_text:
            node_text = node_text.replace(" (would create cycle)", "")
        
        input_node_id = node_text.strip()
        
        # Get the current node ID we're editing
        current_node_id = self.id_edit.text().strip()
        if not current_node_id:
            return
        
        # Check if the item is being checked or unchecked
        is_checked = item.checkState() == Qt.Checked # type: ignore
        
        # If this item is being checked, uncheck all other items
        if is_checked:
            for i in range(self.inputs_list.count()):
                other_item = self.inputs_list.item(i)
                if other_item != item and other_item.checkState() == Qt.Checked: # type: ignore
                    other_item.setCheckState(Qt.Unchecked) # type: ignore
        
        try:
            if is_checked:
                # Add the edge from input_node to current_node
                if input_node_id in self.pipeline.nodes:
                    if self.mode == "edit" and current_node_id in self.pipeline.nodes:
                        # Check again for cycles before adding
                        if not self.pipeline.would_create_cycle(input_node_id, current_node_id):
                            self.pipeline.add_edge(input_node_id, current_node_id)
                            print(f"Added edge: {input_node_id} -> {current_node_id}")
                        else:
                            # This shouldn't happen if we grayed out correctly, but safety check
                            item.setCheckState(Qt.Unchecked) # type: ignore
                            QMessageBox.warning(self, "Cycle Detection", 
                                              f"Cannot connect {input_node_id} to {current_node_id}: would create a cycle")
                    elif self.mode == "add":
                        # In add mode, we don't update the pipeline until OK is pressed
                        # Just validate that this won't create a cycle when the node is added
                        print(f"Selected input {input_node_id} for new node {current_node_id}")
            else:
                # Remove the edge from input_node to current_node
                if self.mode == "edit" and input_node_id in self.pipeline.nodes and current_node_id in self.pipeline.nodes:
                    self.pipeline.remove_edge(input_node_id, current_node_id)
                    print(f"Removed edge: {input_node_id} -> {current_node_id}")
                elif self.mode == "add":
                    print(f"Deselected input {input_node_id} for new node {current_node_id}")
                    
        except Exception as e:
            print(f"Error updating pipeline connection: {e}")
            # Revert the checkbox state on error
            item.setCheckState(Qt.Unchecked if is_checked else Qt.Checked) # type: ignore

        # For both add and edit mode, we may want to enable/disable the OK button
        self.ok_btn.setEnabled(self._is_valid())

    def _is_valid(self):
        node_id = self.id_edit.text().strip()
        opf = self.opfile_combo.currentText().strip()
        raw = self.params_edit.toPlainText().strip()

        # Basic checks: Node ID and operator file must be non-empty
        if not node_id or not opf or opf == "(no operators/ found)":
            return False

        # Params JSON must be valid
        try:
            params_dict = json.loads(raw)
            if not isinstance(params_dict, dict):
                raise ValueError("params must be a JSON object")
        except Exception:
            return False        # Input nodes selection must be valid (if applicable)
        # Note: It's okay to have zero input nodes for source nodes
        if self.inputs_list.isEnabled():
            # Just validate that checked inputs are properly formatted
            for i in range(self.inputs_list.count()):
                item = self.inputs_list.item(i)
                if item.checkState() == Qt.Checked: # type: ignore
                    node_text = item.text()
                    if " (would create cycle)" in node_text:
                        # This shouldn't happen, but if it does, it's invalid
                        return False

        return True
    
    def _set_input_node_checkboxes(self):
        if self.mode != "edit" or not hasattr(self, "node_ids"):
            return

        idx = self.node_index_spin.value()
        if idx < 0 or idx >= len(self.node_ids):
            return

        current_node_id = self.node_ids[idx]
        node = self.pipeline.nodes.get(current_node_id)
        if not node:
            return

        current_inputs = getattr(node, 'inputs', [])

        for i in range(self.inputs_list.count()):
            item = self.inputs_list.item(i)
            if item and item.flags() & Qt.ItemIsEnabled: # type: ignore
                node_text = item.text()
                if node_text.strip() in current_inputs:
                    item.setCheckState(Qt.Checked) # type: ignore
                else:
                    item.setCheckState(Qt.Unchecked) # type: ignore
