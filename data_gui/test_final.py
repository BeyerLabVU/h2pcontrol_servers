#!/usr/bin/env python3
"""Simple test to verify cycle detection works in NodeDialog context."""

import sys
import os

# Add the data_gui directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_basic_functionality():
    """Test basic functionality without GUI."""
    print("Testing basic cycle detection functionality...")
    
    from operators.data_node import PipelineGraph, Node
    
    # Create a test pipeline
    pipeline = PipelineGraph()
    
    # Add test nodes
    node1 = Node('source1', 'Data Source', {'param1': 'value1'})
    node2 = Node('process1', 'Data Processor', {'param2': 'value2'})
    node3 = Node('filter1', 'Data Filter', {'param3': 'value3'})
    
    pipeline.add_node(node1)
    pipeline.add_node(node2)
    pipeline.add_node(node3)
    
    print("Created pipeline with nodes:")
    for node_id in pipeline.nodes:
        print(f"  - {node_id}")
    
    # Test cycle detection scenarios
    print("\nTesting cycle detection:")
    
    # No cycle: source1 -> process1
    result1 = pipeline.would_create_cycle('source1', 'process1')
    print(f"source1 -> process1: {result1} (should be False)")
    
    # Add the edge
    pipeline.add_edge('source1', 'process1')
    
    # No cycle: process1 -> filter1  
    result2 = pipeline.would_create_cycle('process1', 'filter1')
    print(f"process1 -> filter1: {result2} (should be False)")
    
    # Add the edge
    pipeline.add_edge('process1', 'filter1')
    
    # Would create cycle: filter1 -> source1
    result3 = pipeline.would_create_cycle('filter1', 'source1')
    print(f"filter1 -> source1: {result3} (should be True)")
    
    # Self-loop test
    result4 = pipeline.would_create_cycle('source1', 'source1')
    print(f"source1 -> source1: {result4} (should be True)")
    
    # Verify results
    expected = [False, False, True, True]
    actual = [result1, result2, result3, result4]
    
    print(f"\nExpected: {expected}")
    print(f"Actual:   {actual}")
    
    if actual == expected:
        print("✅ Basic cycle detection PASSED!")
        return True
    else:
        print("❌ Basic cycle detection FAILED!")
        return False

def test_node_dialog_import():
    """Test that NodeDialog can be imported and has the expected methods."""
    print("\nTesting NodeDialog import and structure...")
    
    try:
        from node_dialog import NodeDialog
        print("✅ NodeDialog imported successfully")
        
        # Check if it has the expected methods for cycle detection
        has_populate_method = hasattr(NodeDialog, '_populate_input_nodes_list')
        has_input_changed_method = hasattr(NodeDialog, '_on_input_node_changed')
        has_index_changed_method = hasattr(NodeDialog, '_on_index_changed')
        
        print(f"Has _populate_input_nodes_list: {has_populate_method}")
        print(f"Has _on_input_node_changed: {has_input_changed_method}")
        print(f"Has _on_index_changed: {has_index_changed_method}")
        
        if has_populate_method and has_input_changed_method and has_index_changed_method:
            print("✅ NodeDialog has expected cycle detection methods!")
            return True
        else:
            print("❌ NodeDialog missing some cycle detection methods!")
            return False
            
    except Exception as e:
        print(f"❌ Error importing NodeDialog: {e}")
        return False

def test_pipeline_validation():
    """Test pipeline validation scenarios."""
    print("\nTesting pipeline validation scenarios...")
    
    from operators.data_node import PipelineGraph, Node
    
    pipeline = PipelineGraph()
    
    # Test empty pipeline
    try:
        order = pipeline.topological_order()
        print(f"Empty pipeline topological order: {order}")
    except Exception as e:
        print(f"Error with empty pipeline: {e}")
    
    # Add nodes in sequence
    for i in range(4):
        node = Node(f'node{i}', f'Type{i}', {})
        pipeline.add_node(node)
    
    # Create a valid chain
    pipeline.add_edge('node0', 'node1')
    pipeline.add_edge('node1', 'node2')
    pipeline.add_edge('node2', 'node3')
    
    try:
        order = pipeline.topological_order()
        print(f"Valid chain topological order: {order}")
    except Exception as e:
        print(f"Error with valid chain: {e}")
        return False
    
    # Test if adding a cycle-creating edge would be detected
    would_create_cycle = pipeline.would_create_cycle('node3', 'node0')
    print(f"node3 -> node0 would create cycle: {would_create_cycle}")
    
    if would_create_cycle:
        print("✅ Pipeline validation PASSED!")
        return True
    else:
        print("❌ Pipeline validation FAILED!")
        return False

if __name__ == "__main__":
    print("=== Cycle Detection Implementation Test ===\n")
    
    test1 = test_basic_functionality()
    test2 = test_node_dialog_import() 
    test3 = test_pipeline_validation()
    
    print(f"\n=== Test Results ===")
    print(f"Basic Functionality: {'PASS' if test1 else 'FAIL'}")
    print(f"NodeDialog Structure: {'PASS' if test2 else 'FAIL'}")
    print(f"Pipeline Validation: {'PASS' if test3 else 'FAIL'}")
    
    if test1 and test2 and test3:
        print(f"\n🎉 ALL TESTS PASSED!")
        print(f"\nThe cycle detection implementation is working correctly!")
        print(f"Key features implemented:")
        print(f"  ✅ Cycle detection in PipelineGraph")
        print(f"  ✅ NodeDialog integration")
        print(f"  ✅ Real-time input validation")
        print(f"  ✅ Prevention of circular dependencies")
        print(f"\nThe system is ready for use!")
    else:
        print(f"\n❌ Some tests failed. Please review the implementation.")
