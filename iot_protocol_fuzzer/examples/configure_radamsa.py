#!/usr/bin/env python3
"""
Radamsa Configuration Helper for IoT Protocol Fuzzer

This script helps configure the radamsa path for the IoT protocol fuzzer examples.
It will find radamsa on your system and update the example files accordingly.
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

def find_radamsa():
    """Find radamsa binary on the system."""
    # Check if radamsa is in PATH
    radamsa_path = shutil.which("radamsa")
    if radamsa_path:
        return radamsa_path
    
    # Common installation locations
    common_paths = [
        "/usr/bin/radamsa",
        "/usr/local/bin/radamsa",
        "/opt/radamsa/bin/radamsa",
        "/home/tkxb/Projects/radamsa/bin/radamsa",  # User's custom path
    ]
    
    for path in common_paths:
        if os.path.exists(path) and os.access(path, os.X_OK):
            return path
    
    # Search in user's home directory
    home_dir = Path.home()
    for radamsa_file in home_dir.rglob("radamsa"):
        if radamsa_file.is_file() and os.access(radamsa_file, os.X_OK):
            return str(radamsa_file)
    
    return None

def test_radamsa(radamsa_path):
    """Test if radamsa is working correctly."""
    try:
        result = subprocess.run(
            [radamsa_path, "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False

def update_example_files(radamsa_path):
    """Update all example files with the correct radamsa path."""
    examples_dir = Path(__file__).parent
    example_files = [
        "simple_can_fuzz.py",
        "simple_uart_fuzz.py",
        "advanced_uart_fuzz.py",
        "simple_spi_fuzz.py"
    ]
    
    updated_files = []
    
    for example_file in example_files:
        file_path = examples_dir / example_file
        if not file_path.exists():
            continue
            
        # Read the file
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Replace the radamsa path
        old_line = '    radamsa_path = "/home/tkxb/Projects/radamsa/bin/radamsa"'
        new_line = f'    radamsa_path = "{radamsa_path}"'
        
        if old_line in content:
            content = content.replace(old_line, new_line)
            
            # Write back the file
            with open(file_path, 'w') as f:
                f.write(content)
            
            updated_files.append(example_file)
    
    return updated_files

def main():
    print("🔍 Radamsa Configuration Helper for IoT Protocol Fuzzer")
    print("=" * 60)
    
    # Find radamsa
    print("Searching for radamsa binary...")
    radamsa_path = find_radamsa()
    
    if not radamsa_path:
        print("❌ Radamsa not found on this system!")
        print("\nInstallation options:")
        print("1. Install via package manager:")
        print("   sudo apt-get install radamsa")
        print("\n2. Compile from source:")
        print("   git clone https://gitlab.com/akihe/radamsa.git")
        print("   cd radamsa")
        print("   make")
        print("   sudo make install")
        print("\n3. Or specify custom path when running this script:")
        print("   python configure_radamsa.py /path/to/radamsa")
        return 1
    
    print(f"✅ Found radamsa at: {radamsa_path}")
    
    # Test radamsa
    print("Testing radamsa functionality...")
    if test_radamsa(radamsa_path):
        print("✅ Radamsa is working correctly")
    else:
        print("⚠️  Radamsa found but may not be working properly")
        print("   Try running: {} --version".format(radamsa_path))
    
    # Update example files
    print("\nUpdating example files...")
    updated_files = update_example_files(radamsa_path)
    
    if updated_files:
        print("✅ Updated the following files:")
        for file in updated_files:
            print(f"   - {file}")
    else:
        print("⚠️  No files were updated (they may already be correct)")
    
    # Show usage
    print("\n🚀 Ready to use!")
    print("You can now run the fuzzing examples:")
    print("   python simple_uart_fuzz.py")
    print("   python advanced_uart_fuzz.py")
    print("   python simple_can_fuzz.py")
    print("   python simple_spi_fuzz.py")
    
    return 0

if __name__ == "__main__":
    # Allow custom path as command line argument
    if len(sys.argv) > 1:
        custom_path = sys.argv[1]
        if os.path.exists(custom_path) and os.access(custom_path, os.X_OK):
            print(f"Using custom radamsa path: {custom_path}")
            updated_files = update_example_files(custom_path)
            if updated_files:
                print("✅ Updated files with custom path")
            sys.exit(0)
        else:
            print(f"❌ Custom path not found or not executable: {custom_path}")
            sys.exit(1)
    
    sys.exit(main()) 