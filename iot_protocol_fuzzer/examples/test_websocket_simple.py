#!/usr/bin/env python3
"""
Simple WebSocket Integration Test - No External Dependencies
This test demonstrates the WebSocket event system without requiring Radamsa
"""

import logging
import time
from typing import Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def event_callback(event_type, event_data: Dict[str, Any]):
    """Mock event callback that simulates WebSocket emission"""
    print(f"\n🔔 WebSocket Event Emitted:")
    print(f"   Type: {event_type.value}")
    print(f"   Data: {event_data}")
    
    # Simulate WebSocket message types
    if event_type.value == 'campaign_started':
        print("   📡 → Sending 'campaign_status' to Flutter client")
    elif event_type.value == 'test_case_completed':
        print("   📊 → Sending 'test_case_update' to Flutter client")
    elif event_type.value == 'crash_detected':
        print("   🚨 → Sending 'crash_alert' to Flutter client")
    elif event_type.value == 'statistics_update':
        print("   📈 → Sending 'statistics_update' to Flutter client")
    elif event_type.value == 'progress_update':
        print("   ⏳ → Sending 'progress_update' to Flutter client")

def main():
    """Test WebSocket event integration without external dependencies"""
    print("=== Simple WebSocket Integration Test ===")
    print("Testing event emission without Radamsa dependency\n")
    
    try:
        # Import the enhanced orchestrator
        from iot_protocol_fuzzer.core.orchestrator import Orchestrator, CampaignConfig, EventType
        print("✅ Successfully imported enhanced orchestrator with WebSocket support")
        
        # Create a simple mock generator
        class MockGenerator:
            def seed_corpus(self):
                return [
                    b"AT+CGMI\r\n",
                    b"AT+CGMM\r\n", 
                    b"AT+CGMR\r\n",
                    b"AT+CGSN\r\n",
                    b"AT+COPS?\r\n"
                ]
            
            def generate(self, seeds, iterations):
                """Generate test payloads"""
                for i in range(iterations):
                    # Simple payload variation
                    seed = seeds[i % len(seeds)]
                    yield seed + b"_" + str(i).encode()
        
        # Create a mock harness
        class MockHarness:
            def __init__(self):
                self.test_count = 0
                
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
                
                # Simulate occasional crashes for testing
                if self.test_count % 7 == 0:
                    return MockResult(crashed=True)
                elif self.test_count % 11 == 0:
                    return MockResult(timeout=True)
                else:
                    return MockResult()
        
        # Create mock components
        generator = MockGenerator()
        harness = MockHarness()
        
        # Create config with event callback
        config = CampaignConfig(
            iterations=15,  # Short test
            delay=0.3,      # 300ms delay for visibility
            save_crashes=True,
            event_callback=event_callback  # Enable WebSocket events!
        )
        
        # Create orchestrator
        orchestrator = Orchestrator(
            generator=generator,
            harness=harness,
            config=config
        )
        
        print("\n🚀 Starting fuzzing campaign with WebSocket events...")
        print("   Watch for real-time events that would be sent to Flutter client:")
        
        # Run the fuzzer
        orchestrator.run()
        
        print("\n✅ Campaign completed successfully!")
        print("📊 Final statistics:")
        stats = orchestrator.get_current_stats()
        for key, value in stats.items():
            print(f"   {key}: {value}")
        
        print("\n🎉 WebSocket integration test completed!")
        print("   The fuzzer now emits real-time events that can be sent to Flutter clients")
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 