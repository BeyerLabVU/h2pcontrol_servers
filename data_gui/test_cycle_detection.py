#!/usr/bin/env python3
"""Test script for cycle detection functionality."""

from operators.data_node import PipelineGraph, Node

def test_cycle_detection():
    """Test the cycle detection functionality."""
    print("Testing cycle detection functionality...")
    
    # Create a test pipeline
    pipeline = PipelineGraph()    # Add some test nodes
    node1 = Node('node1', 'Source Node', {})
    node2 = Node('node2', 'Process Node', {})
    node3 = Node('node3', 'Filter Node', {})

    pipeline.add_node(node1)
    pipeline.add_node(node2)
    pipeline.add_node(node3)

    # Test cycle detection
    print('Testing cycle detection:')
    result1 = pipeline.would_create_cycle("node1", "node2")
    print(f'Adding edge node1->node2: would create cycle = {result1}')

    # Add the edge
    pipeline.add_edge('node1', 'node2')
    result2 = pipeline.would_create_cycle("node2", "node3")
    print(f'After adding node1->node2, adding node2->node3: would create cycle = {result2}')

    # Add another edge
    pipeline.add_edge('node2', 'node3')
    result3 = pipeline.would_create_cycle("node3", "node1")
    print(f'After adding node2->node3, adding node3->node1: would create cycle = {result3}')

    # Test self-loop
    result4 = pipeline.would_create_cycle("node1", "node1")
    print(f'Self-loop node1->node1: would create cycle = {result4}')

    print('\nExpected results:')
    print('- First edge (node1->node2): False (no cycle)')
    print('- Second edge (node2->node3): False (no cycle)')
    print('- Third edge (node3->node1): True (creates cycle)')
    print('- Self-loop (node1->node1): True (creates cycle)')
    
    print('\nActual results:')
    print(f'- First edge: {result1}')
    print(f'- Second edge: {result2}')
    print(f'- Third edge: {result3}')
    print(f'- Self-loop: {result4}')
    
    # Verify expected results
    expected = [False, False, True, True]
    actual = [result1, result2, result3, result4]
    
    if actual == expected:
        print('\n✅ All cycle detection tests PASSED!')
        return True
    else:
        print('\n❌ Some cycle detection tests FAILED!')
        return False

def test_get_reachable_nodes():
    """Test the get_reachable_nodes functionality."""
    print("\nTesting get_reachable_nodes functionality...")
    
    # Create a test pipeline with multiple connections
    pipeline = PipelineGraph()    # Add nodes
    for i in range(5):
        node = Node(f'node{i}', f'Test Node {i}', {})
        pipeline.add_node(node)
    
    # Create a chain: node0 -> node1 -> node2 -> node3
    # And a branch: node1 -> node4
    pipeline.add_edge('node0', 'node1')
    pipeline.add_edge('node1', 'node2')
    pipeline.add_edge('node2', 'node3')
    pipeline.add_edge('node1', 'node4')
    
    # Test reachable nodes from node0
    reachable_from_0 = pipeline.get_reachable_nodes('node0')
    print(f'Reachable from node0: {sorted(reachable_from_0)}')
    
    # Test reachable nodes from node1
    reachable_from_1 = pipeline.get_reachable_nodes('node1')
    print(f'Reachable from node1: {sorted(reachable_from_1)}')
    
    # Test reachable nodes from node3 (should be empty)
    reachable_from_3 = pipeline.get_reachable_nodes('node3')
    print(f'Reachable from node3: {sorted(reachable_from_3)}')
    
    # Verify results
    expected_from_0 = {'node1', 'node2', 'node3', 'node4'}
    expected_from_1 = {'node2', 'node3', 'node4'}
    expected_from_3 = set()
    
    if (reachable_from_0 == expected_from_0 and 
        reachable_from_1 == expected_from_1 and 
        reachable_from_3 == expected_from_3):
        print('✅ All reachability tests PASSED!')
        return True
    else:
        print('❌ Some reachability tests FAILED!')
        return False

if __name__ == "__main__":
    test1_passed = test_cycle_detection()
    test2_passed = test_get_reachable_nodes()
    
    if test1_passed and test2_passed:
        print('\n🎉 All tests PASSED! The cycle detection implementation is working correctly.')
    else:
        print('\n⚠️ Some tests failed. Please check the implementation.')
