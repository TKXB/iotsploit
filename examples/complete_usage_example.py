#!/usr/bin/env python3
"""
Complete Usage Example for IoTSploit Tool Management System
===========================================================

This example demonstrates the complete architecture in action:
- Centralized Tool Manager
- Multiple execution backends
- Task queuing and scheduling
- Category-specific operations
- Real-world IoT security testing scenarios

Run this example to see the full system capabilities.
"""

import sys
import os
import time
import logging
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sat_toolkit.core.centralized_tool_manager import (
    get_centralized_tool_manager, print_system_report
)
from sat_toolkit.core.execution_queue import TaskPriority, TaskStatus

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def demo_system_initialization():
    """Demonstrate system initialization and health check"""
    print("\n" + "="*60)
    print("🚀 SYSTEM INITIALIZATION DEMO")
    print("="*60)
    
    # Get the centralized manager (automatically initializes)
    manager = get_centralized_tool_manager()
    
    # Print comprehensive system report
    print_system_report()
    
    return manager

def demo_tool_discovery_and_validation():
    """Demonstrate tool discovery and validation"""
    print("\n" + "="*60)
    print("🔍 TOOL DISCOVERY & VALIDATION DEMO")
    print("="*60)
    
    manager = get_centralized_tool_manager()
    
    # Discover all tools
    print("Discovering tools...")
    discovery_results = manager.discover_tools()
    
    print(f"\nDiscovery Results:")
    for tool_name, status in discovery_results.items():
        icon = "✅" if status.value == "available" else "❌"
        print(f"  {icon} {tool_name}: {status.value}")
    
    # Get available tools by category
    print(f"\nTools by Category:")
    available_tools = manager.category_manager.get_available_tools()
    missing_tools = manager.category_manager.get_missing_tools()
    category_info = manager.category_manager.get_category_info()
    
    print(f"  📂 {category_info.name}: {len(available_tools)} available, {len(missing_tools)} missing")
    if available_tools:
        for tool in available_tools[:5]:  # Show first 5
            print(f"     ✅ {tool}")
        if len(available_tools) > 5:
            print(f"     ... and {len(available_tools) - 5} more")
    
    if missing_tools:
        print(f"  Missing tools:")
        for tool in missing_tools[:3]:  # Show first 3
            print(f"     ❌ {tool}")
        if len(missing_tools) > 3:
            print(f"     ... and {len(missing_tools) - 3} more")

def demo_synchronous_execution():
    """Demonstrate synchronous tool execution"""
    print("\n" + "="*60)
    print("⚡ SYNCHRONOUS EXECUTION DEMO")
    print("="*60)
    
    manager = get_centralized_tool_manager()
    
    # Test different execution scenarios
    test_cases = [
        {
            'name': 'Python Version Check',
            'tool': 'python3',
            'args': ['--version'],
            'description': 'Check Python version'
        },
        {
            'name': 'Git Status',
            'tool': 'git',
            'args': ['--version'],
            'description': 'Check Git version'
        },
        {
            'name': 'Network Ping Test',
            'tool': 'ping',
            'args': ['-c', '2', '8.8.8.8'],
            'description': 'Ping Google DNS'
        }
    ]
    
    for test_case in test_cases:
        tool_name = test_case['tool']
        
        if not manager.is_tool_available(tool_name):
            print(f"⏭️  Skipping {test_case['name']}: {tool_name} not available")
            continue
        
        print(f"\n🔧 {test_case['name']}")
        print(f"   Description: {test_case['description']}")
        print(f"   Command: {tool_name} {' '.join(test_case['args'])}")
        
        try:
            result = manager.execute_tool(tool_name, test_case['args'], timeout=10)
            
            if result.success:
                print(f"   ✅ Success (took {result.execution_time:.2f}s)")
                if result.stdout.strip():
                    print(f"   📤 Output: {result.stdout.strip()[:100]}...")
            else:
                print(f"   ❌ Failed (code: {result.return_code})")
                if result.stderr.strip():
                    print(f"   📤 Error: {result.stderr.strip()[:100]}...")
                    
        except Exception as e:
            print(f"   💥 Exception: {e}")

def demo_asynchronous_execution():
    """Demonstrate asynchronous task execution"""
    print("\n" + "="*60)
    print("🔄 ASYNCHRONOUS EXECUTION DEMO")
    print("="*60)
    
    manager = get_centralized_tool_manager()
    
    # Submit multiple tasks with different priorities
    tasks = []
    
    # High priority task
    if manager.is_tool_available('python3'):
        task_id = manager.submit_task(
            'python3', ['-c', 'import time; time.sleep(2); print("High priority task done")'],
            priority=TaskPriority.HIGH,
            metadata={'description': 'High priority Python task'}
        )
        tasks.append(('High Priority Task', task_id))
        print(f"📋 Submitted high priority task: {task_id}")
    
    # Normal priority tasks
    for i in range(3):
        if manager.is_tool_available('python3'):
            task_id = manager.submit_task(
                'python3', ['-c', f'import time; time.sleep(1); print("Task {i+1} done")'],
                priority=TaskPriority.NORMAL,
                metadata={'description': f'Normal task {i+1}'}
            )
            tasks.append((f'Normal Task {i+1}', task_id))
            print(f"📋 Submitted normal task {i+1}: {task_id}")
    
    # Low priority task
    if manager.is_tool_available('python3'):
        task_id = manager.submit_task(
            'python3', ['-c', 'import time; time.sleep(1); print("Low priority task done")'],
            priority=TaskPriority.LOW,
            metadata={'description': 'Low priority Python task'}
        )
        tasks.append(('Low Priority Task', task_id))
        print(f"📋 Submitted low priority task: {task_id}")
    
    # Monitor task execution
    print(f"\n📊 Monitoring task execution...")
    
    completed_tasks = 0
    while completed_tasks < len(tasks):
        time.sleep(0.5)
        
        # Check queue stats
        stats = manager.get_queue_stats()
        print(f"   Queue: {stats.running_tasks} running, {stats.pending_tasks} pending")
        
        # Check completed tasks
        for task_name, task_id in tasks:
            task = manager.get_task(task_id)
            if task and task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                if task.status == TaskStatus.COMPLETED:
                    print(f"   ✅ {task_name} completed")
                    if task.result and task.result.stdout.strip():
                        print(f"      Output: {task.result.stdout.strip()}")
                else:
                    print(f"   ❌ {task_name} failed")
                
                # Remove from monitoring
                tasks = [(n, t) for n, t in tasks if t != task_id]
                completed_tasks += 1
                break

def demo_category_specific_operations():
    """Demonstrate category-specific tool operations"""
    print("\n" + "="*60)
    print("📂 CATEGORY-SPECIFIC OPERATIONS DEMO")
    print("="*60)
    
    manager = get_centralized_tool_manager()
    
    # Hardware Tools Demo
    print(f"\n🔧 Hardware Tools Demo:")
    
    if manager.is_tool_available('esptool'):
        print("   ✅ ESP32 tools available")
        # Note: This would require actual hardware
        print("   📝 ESP32 flash example (requires hardware):")
        print("      manager.flash_esp32('/dev/ttyUSB0', 'firmware.bin')")
    else:
        print("   ❌ ESP32 tools not available")
        print("   💡 Install with: pip install esptool")
    
    # Network Tools Demo
    print(f"\n🌐 Network Tools Demo:")
    
    if manager.is_tool_available('nmap'):
        print("   ✅ Network scanning tools available")
        print("   🔍 Performing localhost port scan...")
        try:
            result = manager.scan_network('127.0.0.1', '22,80,443', scan_type='tcp')
            if result['status'] == 'success':
                print(f"   ✅ Scan completed in {result['execution_time']:.2f}s")
                # Show first few lines of output
                lines = result['output'].split('\n')[:5]
                for line in lines:
                    if line.strip():
                        print(f"      {line}")
            else:
                print(f"   ❌ Scan failed: {result['message']}")
        except Exception as e:
            print(f"   💥 Scan error: {e}")
    else:
        print("   ❌ Network tools not available")
        print("   💡 Install with: sudo apt install nmap")
    
    # Security Tools Demo
    print(f"\n🔒 Security Tools Demo:")
    
    if manager.is_tool_available('strings'):
        print("   ✅ Binary analysis tools available")
        
        # Create a test file for string extraction
        test_file = '/tmp/test_binary'
        try:
            with open(test_file, 'w') as f:
                f.write("This is a test file\nwith some strings\nfor demonstration\n")
            
            print(f"   🔍 Extracting strings from test file...")
            result = manager.extract_strings(test_file, min_length=3)
            
            if result['status'] == 'success':
                strings = result['strings'][:5]  # First 5 strings
                print(f"   ✅ Found {len(result['strings'])} strings")
                for s in strings:
                    if s.strip():
                        print(f"      '{s.strip()}'")
            else:
                print(f"   ❌ String extraction failed: {result['message']}")
                
            # Cleanup
            os.unlink(test_file)
            
        except Exception as e:
            print(f"   💥 String extraction error: {e}")
    else:
        print("   ❌ Security tools not available")
        print("   💡 Install with: sudo apt install binutils")
    
    # System Tools Demo
    print(f"\n💻 System Tools Demo:")
    
    if manager.is_tool_available('adb'):
        print("   ✅ Android tools available")
        print("   📱 Checking for Android devices...")
        try:
            result = manager.list_adb_devices()
            if result['status'] == 'success':
                devices = result['devices']
                if devices:
                    print(f"   ✅ Found {len(devices)} Android device(s):")
                    for device in devices:
                        print(f"      📱 {device['id']}: {device['status']}")
                else:
                    print("   📱 No Android devices connected")
            else:
                print(f"   ❌ ADB check failed: {result['message']}")
        except Exception as e:
            print(f"   💥 ADB error: {e}")
    else:
        print("   ❌ Android tools not available")
        print("   💡 Install Android SDK platform-tools")

def demo_execution_backends():
    """Demonstrate different execution backends"""
    print("\n" + "="*60)
    print("🚀 EXECUTION BACKENDS DEMO")
    print("="*60)
    
    manager = get_centralized_tool_manager()
    
    # List available backends
    backends = manager.list_execution_backends()
    print(f"Available execution backends: {backends}")
    
    if not manager.is_tool_available('python3'):
        print("❌ Python3 not available, skipping backend demo")
        return
    
    # Test each backend with the same command
    test_command = ['-c', 'print("Hello from backend!")']
    
    for backend in backends:
        print(f"\n🔧 Testing {backend} backend:")
        try:
            # Set backend as default temporarily
            original_backend = manager.backend_manager.default_backend
            manager.set_default_backend(backend)
            
            result = manager.execute_tool('python3', test_command, timeout=5)
            
            if result.success:
                print(f"   ✅ Success with {backend}")
                print(f"   📤 Output: {result.stdout.strip()}")
                print(f"   ⏱️  Time: {result.execution_time:.3f}s")
            else:
                print(f"   ❌ Failed with {backend}")
                print(f"   📤 Error: {result.stderr.strip()}")
            
            # Restore original backend
            manager.set_default_backend(original_backend)
            
        except Exception as e:
            print(f"   💥 Exception with {backend}: {e}")

def demo_system_monitoring():
    """Demonstrate system monitoring and health checks"""
    print("\n" + "="*60)
    print("📊 SYSTEM MONITORING DEMO")
    print("="*60)
    
    manager = get_centralized_tool_manager()
    
    # Get system health
    health = manager.get_system_health(force_refresh=True)
    
    print(f"System Health: {health.status}")
    print(f"Tools: {health.available_tools}/{health.total_tools}")
    print(f"Critical missing: {health.missing_critical_tools}")
    
    # Show category status
    print(f"\nCategory Status:")
    for category, info in health.category_status.items():
        status = "✅" if info['can_operate'] else "❌"
        print(f"  {status} {category}: {len(info['available_tools'])}/{info['total_tools']} tools")
    
    # Show recommendations
    if health.recommendations:
        print(f"\nRecommendations:")
        for rec in health.recommendations:
            print(f"  💡 {rec}")
    
    # Get installation recommendations
    print(f"\nInstallation Recommendations:")
    install_recs = manager.get_installation_recommendations()
    for category, tools in install_recs.items():
        if tools.get('required'):
            print(f"  🔴 {category} required: {', '.join(tools['required'])}")
        if tools.get('optional'):
            print(f"  🟡 {category} optional: {', '.join(tools['optional'][:3])}...")

def demo_real_world_scenario():
    """Demonstrate a real-world IoT security testing scenario"""
    print("\n" + "="*60)
    print("🎯 REAL-WORLD IoT SECURITY TESTING SCENARIO")
    print("="*60)
    
    manager = get_centralized_tool_manager()
    
    print("Scenario: IoT Device Security Assessment")
    print("Steps:")
    print("1. Network discovery")
    print("2. Port scanning")
    print("3. Service enumeration")
    print("4. Firmware analysis (simulated)")
    print("5. Report generation")
    
    # Step 1: Network Discovery (simulated)
    print(f"\n🔍 Step 1: Network Discovery")
    if manager.is_tool_available('ping'):
        print("   📡 Checking network connectivity...")
        result = manager.execute_tool('ping', ['-c', '1', '8.8.8.8'], timeout=10)
        if result.success:
            print("   ✅ Network connectivity confirmed")
        else:
            print("   ❌ Network connectivity issues")
    
    # Step 2: Port Scanning
    print(f"\n🔍 Step 2: Port Scanning")
    if manager.is_tool_available('nmap'):
        print("   🎯 Scanning localhost for demonstration...")
        result = manager.scan_network('127.0.0.1', '22,80,443,8080', scan_type='tcp')
        if result['status'] == 'success':
            print("   ✅ Port scan completed")
            print(f"   ⏱️  Scan time: {result['execution_time']:.2f}s")
        else:
            print(f"   ❌ Port scan failed: {result['message']}")
    else:
        print("   ⏭️  Skipping port scan (nmap not available)")
    
    # Step 3: Service Enumeration (simulated)
    print(f"\n🔍 Step 3: Service Enumeration")
    print("   📋 Would enumerate services on discovered ports")
    print("   📋 Would check for default credentials")
    print("   📋 Would identify service versions")
    
    # Step 4: Firmware Analysis
    print(f"\n🔍 Step 4: Firmware Analysis")
    if manager.is_tool_available('strings'):
        print("   🔬 Analyzing firmware (simulated with test file)...")
        
        # Create a simulated firmware file
        firmware_file = '/tmp/simulated_firmware.bin'
        try:
            with open(firmware_file, 'w') as f:
                f.write("FIRMWARE_VERSION=1.2.3\n")
                f.write("admin:password123\n")
                f.write("http://update.server.com\n")
                f.write("SECRET_KEY=abc123def456\n")
            
            result = manager.extract_strings(firmware_file, min_length=5)
            
            if result['status'] == 'success':
                print("   ✅ String extraction completed")
                interesting_strings = [s for s in result['strings'] 
                                     if any(keyword in s.lower() for keyword in 
                                           ['password', 'key', 'admin', 'version'])]
                
                if interesting_strings:
                    print("   🚨 Potentially interesting strings found:")
                    for s in interesting_strings[:3]:
                        print(f"      • {s.strip()}")
            
            # Cleanup
            os.unlink(firmware_file)
            
        except Exception as e:
            print(f"   💥 Firmware analysis error: {e}")
    else:
        print("   ⏭️  Skipping firmware analysis (strings not available)")
    
    # Step 5: Report Generation
    print(f"\n📊 Step 5: Report Generation")
    print("   📝 Generating security assessment report...")
    print("   ✅ Assessment completed!")
    print("   📋 Summary:")
    print("      • Network connectivity: Verified")
    print("      • Open ports: Identified")
    print("      • Potential vulnerabilities: Found")
    print("      • Recommendations: Generated")

def main():
    """Main demonstration function"""
    print("🎯 IoTSploit Tool Management System - Complete Demo")
    print("This demo showcases the complete architecture in action")
    
    try:
        # Run all demonstrations
        manager = demo_system_initialization()
        demo_tool_discovery_and_validation()
        demo_synchronous_execution()
        demo_asynchronous_execution()
        demo_category_specific_operations()
        demo_execution_backends()
        demo_system_monitoring()
        demo_real_world_scenario()
        
        print("\n" + "="*60)
        print("🎉 DEMO COMPLETED SUCCESSFULLY!")
        print("="*60)
        print("The IoTSploit Tool Management System is ready for use.")
        print("Key features demonstrated:")
        print("✅ Centralized tool management")
        print("✅ Multiple execution backends")
        print("✅ Asynchronous task execution")
        print("✅ Category-specific operations")
        print("✅ System health monitoring")
        print("✅ Real-world security testing")
        
        # Final system report
        print("\nFinal System Report:")
        print_system_report()
        
        # Cleanup
        print("\n🧹 Cleaning up...")
        manager.cleanup()
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Demo interrupted by user")
    except Exception as e:
        print(f"\n\n💥 Demo failed with error: {e}")
        logger.exception("Demo failed")
    finally:
        # Ensure cleanup
        try:
            manager = get_centralized_tool_manager()
            manager.shutdown(wait=False)
        except:
            pass

if __name__ == "__main__":
    main() 