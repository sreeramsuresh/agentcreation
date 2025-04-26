#!/usr/bin/env python3
"""
Cross-platform build script for Attendance Tracker
Detects platform and runs the appropriate build script
"""

import os
import sys
import platform
import subprocess
import argparse

def check_requirements():
    """Check basic requirements for all platforms"""
    # Check Python version
    if sys.version_info < (3, 6):
        print("Error: Python 3.6 or higher is required.")
        return False
    
    # Check pip is installed
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "--version"], stdout=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        print("Error: pip is not installed. Please install pip.")
        return False
    
    return True

def check_nsis_path(nsis_path):
    """Check if the provided NSIS path exists and is valid"""
    if nsis_path and os.path.exists(nsis_path):
        print(f"[OK] Found NSIS at: {nsis_path}")
        return True
    return False

def ensure_build_scripts():
    """Ensure that platform-specific build scripts exist"""
    required_scripts = {
        "Windows": "build_windows.py",
        "Darwin": "build_macos.py",  # macOS
        "Linux": "build_linux.py"
    }
    
    current_platform = platform.system()
    script_file = required_scripts.get(current_platform)
    
    if not script_file:
        print(f"Error: Unsupported platform: {current_platform}")
        return False
    
    if not os.path.exists(script_file):
        print(f"Error: Build script '{script_file}' not found.")
        print("Please ensure all build scripts are in the current directory.")
        return False
    
    return script_file

def main():
    parser = argparse.ArgumentParser(description='Build Attendance Tracker for the current platform')
    
    # Add platform-specific arguments
    if platform.system() == "Windows":
        parser.add_argument('--nsis-path', help='Path to makensis.exe if not in PATH')
    elif platform.system() == "Linux":
        parser.add_argument('--deb-only', action='store_true', help='Build only Debian package (skip AppImage)')
        parser.add_argument('--appimage-only', action='store_true', help='Build only AppImage (skip Debian package)')
    
    args = parser.parse_args()
    
    # Check requirements
    if not check_requirements():
        sys.exit(1)
    
    # Special check for Windows NSIS path
    if platform.system() == "Windows" and args.nsis_path:
        if not check_nsis_path(args.nsis_path):
            print(f"Error: The specified NSIS path does not exist: {args.nsis_path}")
            sys.exit(1)
    
    # Get the appropriate build script
    build_script = ensure_build_scripts()
    if not build_script:
        sys.exit(1)
    
    print(f"Building for {platform.system()}...")
    
    # Run the platform-specific build script with arguments
    cmd = [sys.executable, build_script]
    
    # Add any arguments passed to this script
    if platform.system() == "Windows" and args.nsis_path:
        cmd.extend(["--nsis-path", args.nsis_path])
    elif platform.system() == "Linux":
        if args.deb_only:
            cmd.append("--deb-only")
        if args.appimage_only:
            cmd.append("--appimage-only")
    
    try:
        # Use subprocess.run with captured output
        process = subprocess.run(cmd, capture_output=True, text=True)
        
        # Print output for visibility
        if process.stdout:
            print(process.stdout)
        
        if process.stderr:
            print("Errors:", process.stderr)
        
        if process.returncode != 0:
            print(f"\nBuild process failed with error code {process.returncode}")
            sys.exit(1)
        else:
            print("\nBuild process completed successfully!")
    except Exception as e:
        print(f"\nBuild process failed with error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()