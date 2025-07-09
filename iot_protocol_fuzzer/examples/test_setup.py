#!/usr/bin/env python3
"""
Setup Test for IoT Protocol Fuzzer

This script tests if all dependencies and configurations are working correctly
for the IoT protocol fuzzer examples.
"""

import sys
import shutil
import subprocess
from pathlib import Path

def test_radamsa():
    """Test if radamsa is working correctly."""
    print("Testing Radamsa...")
    
    # Check if radamsa is available
    radamsa_path = shutil.which("radamsa")
    if not radamsa_path:
        # Try custom path from examples
        custom_path = "/home/tkxb/Projects/radamsa/bin/radamsa"
        if Path(custom_path).exists():
            radamsa_path = custom_path
        else:
            print("❌ Radamsa not found in PATH or custom location")
            return False
    
    print(f"✅ Found radamsa at: {radamsa_path}")
    
    # Test radamsa functionality
    try:
        result = subprocess.run(
            [radamsa_path, "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            print("✅ Radamsa is working correctly")
            return True
        else:
            print(f"❌ Radamsa version check failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Error testing radamsa: {e}")
        return False

def test_radamsa_generator():
    """Test if RadamsaGenerator can be imported and used."""
    print("\nTesting RadamsaGenerator...")
    
    try:
        from iot_protocol_fuzzer.generators.radamsa_generator import RadamsaGenerator
        print("✅ RadamsaGenerator imported successfully")
        
        # Test with custom path
        radamsa_path = "/home/tkxb/Projects/radamsa/bin/radamsa"
        if Path(radamsa_path).exists():
            gen = RadamsaGenerator(radamsa_path=radamsa_path)
            print("✅ RadamsaGenerator created with custom path")
        else:
            gen = RadamsaGenerator()
            print("✅ RadamsaGenerator created with default path")
        
        # Test mutation
        seeds = [b"test"]
        gen.seed_corpus = lambda: seeds
        mutations = list(gen.generate(seeds, 1))
        if mutations:
            print(f"✅ Generated {len(mutations)} mutations")
            return True
        else:
            print("❌ No mutations generated")
            return False
            
    except Exception as e:
        print(f"❌ Error testing RadamsaGenerator: {e}")
        return False

def test_harnesses():
    """Test if harnesses can be imported."""
    print("\nTesting Harnesses...")
    
    tests = [
        ("CAN", "iot_protocol_fuzzer.harnesses.can_harness", "CANHarness"),
        ("UART", "iot_protocol_fuzzer.harnesses.uart_harness", "UARTHarness"),
        ("SPI", "iot_protocol_fuzzer.harnesses.spi_harness", "SPIHarness"),
    ]
    
    results = []
    for name, module, cls in tests:
        try:
            exec(f"from {module} import {cls}")
            print(f"✅ {name} harness imported successfully")
            results.append(True)
        except Exception as e:
            print(f"❌ {name} harness import failed: {e}")
            results.append(False)
    
    return all(results)

def test_interfaces():
    """Test if interfaces can be imported."""
    print("\nTesting Interfaces...")
    
    tests = [
        ("CAN", "iot_protocol_fuzzer.interfaces.can_interface", "SocketCANInterface", "python-can"),
        ("UART", "iot_protocol_fuzzer.interfaces.uart_interface", "UARTInterface", "pyserial"),
        ("SPI", "iot_protocol_fuzzer.interfaces.spi_interface", "SPIInterface", "spidev"),
    ]
    
    results = []
    for name, module, cls, package in tests:
        try:
            exec(f"from {module} import {cls}")
            print(f"✅ {name} interface imported successfully")
            results.append(True)
        except Exception as e:
            print(f"⚠️  {name} interface import failed: {e}")
            print(f"   Install with: pip install {package}")
            results.append(False)
    
    return results

def test_orchestrator():
    """Test if orchestrator can be imported."""
    print("\nTesting Orchestrator...")
    
    try:
        from iot_protocol_fuzzer.core.orchestrator import Orchestrator, CampaignConfig
        print("✅ Orchestrator imported successfully")
        
        # Test configuration
        config = CampaignConfig(iterations=1, delay=0.0, save_crashes=False)
        print("✅ CampaignConfig created successfully")
        return True
        
    except Exception as e:
        print(f"❌ Error testing Orchestrator: {e}")
        return False

def test_examples():
    """Test if example files are properly configured."""
    print("\nTesting Example Files...")
    
    examples_dir = Path(__file__).parent
    example_files = [
        "simple_can_fuzz.py",
        "simple_uart_fuzz.py", 
        "advanced_uart_fuzz.py",
        "simple_spi_fuzz.py"
    ]
    
    results = []
    for example_file in example_files:
        file_path = examples_dir / example_file
        if file_path.exists():
            try:
                with open(file_path, 'r') as f:
                    content = f.read()
                
                # Check if radamsa path is configured
                if 'radamsa_path =' in content:
                    print(f"✅ {example_file} has radamsa path configured")
                    results.append(True)
                else:
                    print(f"⚠️  {example_file} may need radamsa path configuration")
                    results.append(False)
                    
            except Exception as e:
                print(f"❌ Error reading {example_file}: {e}")
                results.append(False)
        else:
            print(f"❌ {example_file} not found")
            results.append(False)
    
    return all(results)

def main():
    """Run all tests."""
    print("🧪 IoT Protocol Fuzzer Setup Test")
    print("=" * 50)
    
    tests = [
        ("Radamsa Binary", test_radamsa),
        ("RadamsaGenerator", test_radamsa_generator),
        ("Harnesses", test_harnesses),
        ("Interfaces", test_interfaces),
        ("Orchestrator", test_orchestrator),
        ("Examples", test_examples),
    ]
    
    results = []
    for name, test_func in tests:
        print(f"\n{'='*20} {name} {'='*20}")
        try:
            result = test_func()
            results.append(result)
        except Exception as e:
            print(f"❌ Unexpected error in {name}: {e}")
            results.append(False)
    
    # Summary
    print("\n" + "="*50)
    print("📋 Test Summary")
    print("="*50)
    
    for (name, _), result in zip(tests, results):
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{name:<20} {status}")
    
    # Overall result
    interface_results = results[3] if len(results) > 3 else []
    core_passed = all(results[:3]) and all(results[4:])  # Skip interface results
    interface_warnings = isinstance(interface_results, list) and not all(interface_results)
    
    print("\n" + "="*50)
    if core_passed:
        print("🎉 Core fuzzer functionality is working!")
        if interface_warnings:
            print("⚠️  Some interfaces may not work (install missing packages)")
        print("\nYou can now run the fuzzing examples:")
        print("   python simple_uart_fuzz.py")
        print("   python advanced_uart_fuzz.py")
        print("   python simple_can_fuzz.py")
        print("   python simple_spi_fuzz.py")
    else:
        print("❌ Some core components are not working")
        print("Please fix the issues above before running fuzzing examples")
    
    return 0 if core_passed else 1

if __name__ == "__main__":
    sys.exit(main()) 