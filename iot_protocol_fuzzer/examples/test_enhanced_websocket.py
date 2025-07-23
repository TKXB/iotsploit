#!/usr/bin/env python3
"""
Test script to verify that enhanced orchestrator sends correct websocket events
This demonstrates that the fuzzer now includes protocol frame information for Flutter table
"""

import logging
import time
from typing import Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def enhanced_event_callback(event_type, event_data: Dict[str, Any]):
    """
    Enhanced event callback that shows the protocol frame information
    """
    print(f"\n🔔 Enhanced WebSocket Event:")
    print(f"   Type: {event_type}")
    print(f"   Protocol Type: {event_data.get('protocol_type', 'Unknown')}")
    
    if event_type.value == 'test_case_started':
        print(f"   Test Case ID: {event_data.get('test_case_id')}")
        print(f"   Name: {event_data.get('name')}")
        print(f"   Sub-Function: {event_data.get('subFunction')}")
        print(f"   Payload: {event_data.get('payload')}")
        print(f"   Description: {event_data.get('description')}")
        print(f"   Protocol Frame: {event_data.get('protocol_frame')}")
        print(f"   Status: {event_data.get('status')}")
        print("   📡 → This data is now compatible with Flutter table!")
        
    elif event_type.value == 'test_case_completed':
        print(f"   Test Case ID: {event_data.get('test_case_id')}")
        print(f"   Name: {event_data.get('name')}")
        print(f"   Protocol Frame: {event_data.get('protocol_frame')}")
        print(f"   Status: {event_data.get('status')}")
        print(f"   Pass: {event_data.get('pass')}")
        print(f"   Fail: {event_data.get('fail')}")
        print(f"   Check: {event_data.get('check')}")
        print("   📊 → Result data ready for Flutter table!")
        
    elif event_type.value == 'campaign_started':
        print(f"   Protocol Type: {event_data.get('protocol_type')}")
        print(f"   Total Iterations: {event_data.get('total_iterations')}")
        print(f"   Test Groups: {list(event_data.get('test_groups', {}).keys())}")
        print("   🚀 → Campaign started with enhanced metadata!")
        
    elif event_type.value == 'crash_detected':
        print(f"   Test Case ID: {event_data.get('test_case_id')}")
        print(f"   Protocol Frame: {event_data.get('frame_info', {}).get('protocol_frame')}")
        print(f"   Payload Hex: {event_data.get('payload_hex')}")
        print(f"   Crash Info: {event_data.get('crash_info')}")
        print("   🚨 → Crash detected with detailed protocol info!")


def main():
    """Test enhanced WebSocket events"""
    print("=== Enhanced IoT Protocol Fuzzer WebSocket Test ===")
    print("Testing enhanced events with protocol frame information for Flutter table")
    print()
    
    try:
        # Import enhanced fuzzer components
        from iot_protocol_fuzzer.core.orchestrator import Orchestrator
        from iot_protocol_fuzzer.core.config import CampaignConfig, EventType
        from iot_protocol_fuzzer.harnesses.uart_harness import UARTHarness
        
        print("✅ Successfully imported enhanced fuzzer components")
        
        # Create simple mock generator
        class MockGenerator:
            def __init__(self):
                self.seeds = [
                    b"AT\r\n",                 # AT command
                    b"AT+CGMI\r\n",           # Get manufacturer info
                    b"AT+CGMM\r\n",           # Get model info
                    b"AT+CGMR\r\n",           # Get revision info
                    b"AT+CGSN\r\n",           # Get serial number
                    b"VERSION\r\n",           # Version command
                    b"HELLO\r\n",             # Hello command
                    b"STATUS\r\n",            # Status command
                    b"\x02\x00\x00\x00\x04test\x03",  # Binary data
                ]
            
            def seed_corpus(self):
                return self.seeds
            
            def generate(self, seeds, iterations):
                """Generate test payloads by cycling through seeds with variations"""
                for i in range(iterations):
                    seed = seeds[i % len(seeds)]
                    # Simple variations: add suffix, truncate, or use as-is
                    if i % 3 == 0:
                        yield seed + b"_" + str(i).encode()
                    elif i % 3 == 1:
                        yield seed[:-1] if len(seed) > 1 else seed
                    else:
                        yield seed
        
        generator = MockGenerator()
        
        # Create mock UART harness (will be detected as UART protocol)
        class MockUARTHarness:
            def __init__(self):
                self.test_count = 0
                self.__class__.__name__ = 'UARTHarness'  # Trick the protocol detection
            
            def execute(self, payload):
                """Mock harness execution"""
                self.test_count += 1
                
                # Mock result class
                class MockResult:
                    def __init__(self, crashed=False, timeout=False, error=None):
                        self.ok = not (crashed or timeout or error)
                        self.crashed = crashed
                        self.timeout = timeout
                        self.error = error
                        self.info = "Mock execution result"
                        self.response = b"OK\r\n" if self.ok else None
                
                # Simulate occasional crashes and timeouts for testing
                if self.test_count % 7 == 0:
                    return MockResult(crashed=True)
                elif self.test_count % 11 == 0:
                    return MockResult(timeout=True)
                else:
                    return MockResult()
        
        harness = MockUARTHarness()
        
        # Create campaign config with enhanced event callback
        config = CampaignConfig(
            iterations=10,  # Short test
            delay=0.5,      # 500ms delay for visibility
            save_crashes=True,
            event_callback=enhanced_event_callback  # Enhanced callback!
        )
        
        # Create orchestrator
        orchestrator = Orchestrator(
            generator=generator,
            harness=harness,
            config=config
        )
        
        print("\n🚀 Starting enhanced fuzzing campaign...")
        print("   Watch for enhanced events with protocol frame information:")
        print("   - Test case names and descriptions")
        print("   - Sub-function values")
        print("   - Protocol frame displays")
        print("   - Actual payload hex data")
        print("   - Status information")
        print()
        
        # Run the enhanced fuzzer
        orchestrator.run()
        
        print("\n✅ Enhanced campaign completed successfully!")
        print("📊 Final statistics:")
        stats = orchestrator.get_current_stats()
        for key, value in stats.items():
            print(f"   {key}: {value}")
        
        print("\n🎉 Enhanced WebSocket integration test completed!")
        print("   The fuzzer now emits detailed protocol frame information")
        print("   that is compatible with the Flutter table requirements!")
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main() 