#!/usr/bin/env python3
"""
Test script to demonstrate WebSocket event integration with IoT Protocol Fuzzer
This script shows how the fuzzer now emits real-time events that can be captured
and forwarded to Django WebSocket consumers.
"""

import logging
import time
from typing import Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def event_callback(event_type, event_data: Dict[str, Any]):
    """
    Mock event callback that simulates what Django WebSocket system would do
    In real implementation, this would be handled by IoTFuzzerBridge
    """
    print(f"\n🔔 WebSocket Event Emitted:")
    print(f"   Type: {event_type}")
    print(f"   Data: {event_data}")
    
    # Simulate different types of WebSocket messages
    if event_type.value == 'campaign_started':
        print("   📡 Sending 'campaign_status' WebSocket message to clients")
    elif event_type.value == 'test_case_completed':
        print("   📊 Sending 'test_case_update' WebSocket message to clients")
    elif event_type.value == 'crash_detected':
        print("   🚨 Sending 'crash_alert' WebSocket message to clients")
    elif event_type.value == 'statistics_update':
        print("   📈 Sending 'statistics_update' WebSocket message to clients")
    elif event_type.value == 'progress_update':
        print("   ⏳ Sending 'progress_update' WebSocket message to clients")

def main():
    """Test the WebSocket event integration"""
    print("=== IoT Protocol Fuzzer WebSocket Integration Test ===")
    print("This demonstrates how the fuzzer now emits real-time events")
    print("that can be captured and sent to Flutter clients via WebSocket.\n")
    
    try:
        # Import fuzzer components
        from iot_protocol_fuzzer.core.orchestrator import Orchestrator, CampaignConfig, EventType
        from iot_protocol_fuzzer.generators.radamsa_generator import RadamsaGenerator
        from iot_protocol_fuzzer.harnesses.uart_harness import UARTHarness
        from iot_protocol_fuzzer.interfaces.uart_interface import UARTInterface
        
        print("✅ Successfully imported iot_protocol_fuzzer with WebSocket support")
        
        # Create a mock UART interface (won't actually connect)
        try:
            uart_interface = UARTInterface(device="/dev/null", baudrate=115200)
        except:
            print("⚠️  Could not create real UART interface, using mock")
            uart_interface = None
        
        # Create harness
        harness = UARTHarness(interface=uart_interface)
        
        # Create generator with simple seed corpus
        generator = RadamsaGenerator()
        generator.seed_corpus = lambda: [
            b"AT+CGMI\r\n",
            b"AT+CGMM\r\n", 
            b"AT+CGMR\r\n"
        ]
        
        # Create campaign config with event callback
        config = CampaignConfig(
            iterations=20,  # Short test
            delay=0.2,      # 200ms delay
            save_crashes=True,
            event_callback=event_callback  # This enables WebSocket events!
        )
        
        # Create orchestrator
        orchestrator = Orchestrator(
            generator=generator,
            harness=harness,
            config=config
        )
        
        print("\n🚀 Starting fuzzing campaign with WebSocket event emission...")
        print("   Watch for real-time events that would be sent to WebSocket clients:")
        print("   - Campaign status updates")
        print("   - Test case progress")
        print("   - Statistics updates")
        print("   - Crash alerts (if any)")
        
        # Start fuzzing
        orchestrator.run()
        
        print("\n✅ Campaign completed successfully!")
        print("📊 Final statistics:")
        stats = orchestrator.get_current_stats()
        for key, value in stats.items():
            print(f"   {key}: {value}")
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure iot_protocol_fuzzer is properly installed")
    except Exception as e:
        print(f"❌ Error during testing: {e}")

if __name__ == "__main__":
    main() 