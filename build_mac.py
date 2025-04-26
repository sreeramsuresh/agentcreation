#!/usr/bin/env python3
"""
macOS build script for Attendance Tracker
Creates a macOS .app bundle and DMG installer
"""

import os
import sys
import shutil
import subprocess
import platform
import plistlib
import argparse
from pathlib import Path

# Define app info
APP_NAME = "AttendanceTracker"
APP_VERSION = "1.0.0"
APP_DESCRIPTION = "Attendance Tracker for WiFi-based attendance"
APP_AUTHOR = "Your Company Name"
APP_URL = "https://yourcompany.com"
APP_ICON = "AppIcon.icns"  # macOS icon file

def ensure_dependencies():
    """Ensure all build dependencies are installed"""
    print("Checking build dependencies...")
    
    # Check for PyInstaller
    try:
        import PyInstaller
        print("✓ PyInstaller found")
    except ImportError:
        print("✗ PyInstaller not found, installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    
    # Check for create-dmg
    create_dmg_path = shutil.which("create-dmg")
    if create_dmg_path:
        print(f"✓ create-dmg found at {create_dmg_path}")
    else:
        print("✗ create-dmg not found.")
        print("  Please install create-dmg with: brew install create-dmg")
        print("  If you don't have Homebrew, install it from https://brew.sh/")
        return False
    
    # Check for required Python packages
    required_packages = ["keyring", "pillow", "pystray"]
    for package in required_packages:
        try:
            __import__(package)
            print(f"✓ {package} found")
        except ImportError:
            print(f"✗ {package} not found, installing...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
    
    return True

def create_icon_file():
    """Create macOS icon file if it doesn't exist"""
    if os.path.exists(APP_ICON):
        return
    
    print(f"Creating {APP_ICON} file...")
    try:
        from PIL import Image
        # Create a simple colored square
        img = Image.new('RGB', (1024, 1024), color=(66, 133, 244))
        
        # Save as PNG
        png_path = "icon.png"
        img.save(png_path)
        
        # For macOS, we need to create an .icns file, which requires iconutil
        # First, create the iconset directory structure
        iconset_dir = "AppIcon.iconset"
        os.makedirs(iconset_dir, exist_ok=True)
        
        # Create various size icons
        sizes = [16, 32, 64, 128, 256, 512, 1024]
        for size in sizes:
            img_resized = img.resize((size, size), Image.LANCZOS)
            img_resized.save(f"{iconset_dir}/icon_{size}x{size}.png")
            # Also create 2x versions (required for Retina displays)
            if size * 2 <= 1024:  # Don't exceed our source image size
                img_resized = img.resize((size*2, size*2), Image.LANCZOS)
                img_resized.save(f"{iconset_dir}/icon_{size}x{size}@2x.png")
        
        # Use iconutil to convert the iconset to .icns
        subprocess.run(["iconutil", "-c", "icns", iconset_dir], check=True)
        
        # Clean up
        shutil.rmtree(iconset_dir)
        
        print(f"✓ Created {APP_ICON}")
    except Exception as e:
        print(f"✗ Failed to create icon: {str(e)}")
        print("  You will need to provide your own .icns file")
        # Create a text file with instructions
        with open("icon_instructions.txt", "w") as f:
            f.write(f"Please create an icon file named {APP_ICON} before building.")

def create_pyinstaller_spec():
    """Create PyInstaller spec file for macOS"""
    spec_content = f"""# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('icon.png', '.'),
        ('{APP_ICON}', '.'),
    ],
    hiddenimports=['keyring.backends.macOS'],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='{APP_NAME}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='{APP_ICON}',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='{APP_NAME}',
)

app = BUNDLE(
    coll,
    name='{APP_NAME}.app',
    icon='{APP_ICON}',
    bundle_identifier='com.{APP_AUTHOR.lower().replace(" ", "")}.{APP_NAME.lower()}',
    info_plist={{
        'CFBundleShortVersionString': '{APP_VERSION}',
        'CFBundleVersion': '{APP_VERSION}',
        'NSHumanReadableCopyright': '© {APP_AUTHOR}',
        'NSHighResolutionCapable': True,
        'LSUIElement': True,  # Makes the app a "background" app (no Dock icon)
        'LSBackgroundOnly': False,  # Not completely invisible
        'NSRequiresAquaSystemAppearance': False,  # Support Dark Mode
    }},
)
"""
    spec_path = f"{APP_NAME}_mac.spec"
    with open(spec_path, "w") as f:
        f.write(spec_content)
    
    print(f"✓ Created PyInstaller spec file: {spec_path}")
    return spec_path

def create_dmg_script():
    """Create script for DMG creation"""
    script_content = f"""#!/bin/bash
# Script to create DMG for {APP_NAME}

# Configuration
APP_NAME="{APP_NAME}"
APP_VERSION="{APP_VERSION}"
DMG_NAME="${{APP_NAME}}-${{APP_VERSION}}"
SOURCE_APP="dist/${{APP_NAME}}.app"
OUTPUT_DMG="dist/${{DMG_NAME}}.dmg"
BACKGROUND_IMG="dmg_background.png"
DMG_WIDTH=640
DMG_HEIGHT=480
APP_X=160
APP_Y=170
APPS_LINK_X=480
APPS_LINK_Y=170

# Create background image if it doesn't exist
if [ ! -f "$BACKGROUND_IMG" ]; then
    echo "Creating background image..."
    convert -size ${{DMG_WIDTH}}x${{DMG_HEIGHT}} \\
            xc:white \\
            -font Helvetica -pointsize 24 -gravity center \\
            -fill black -annotate +0+0 "Drag ${{APP_NAME}} to Applications to install" \\
            -fill none -stroke black -strokewidth 2 \\
            -draw "line 120,${{APPS_LINK_Y}} 200,${{APPS_LINK_Y}}" \\
            "$BACKGROUND_IMG"
    echo "✓ Created background image"
fi

# Ensure output directory exists
mkdir -p "$(dirname "$OUTPUT_DMG")"

# Remove existing DMG if it exists
if [ -f "$OUTPUT_DMG" ]; then
    rm "$OUTPUT_DMG"
fi

# Create DMG
echo "Creating DMG..."
create-dmg \\
    --volname "${{APP_NAME}}" \\
    --volicon "${{SOURCE_APP}}/Contents/Resources/{APP_ICON}" \\
    --background "$BACKGROUND_IMG" \\
    --window-pos 200 120 \\
    --window-size ${{DMG_WIDTH}} ${{DMG_HEIGHT}} \\
    --icon-size 100 \\
    --icon "${{APP_NAME}}.app" ${{APP_X}} ${{APP_Y}} \\
    --app-drop-link ${{APPS_LINK_X}} ${{APPS_LINK_Y}} \\
    --no-internet-enable \\
    "$OUTPUT_DMG" \\
    "dist/"

# Check if DMG was created successfully
if [ -f "$OUTPUT_DMG" ]; then
    echo "✓ DMG created: $OUTPUT_DMG"
else
    echo "✗ Failed to create DMG"
    exit 1
fi
"""
    
    script_path = "create_dmg.sh"
    with open(script_path, "w") as f:
        f.write(script_content)
    
    # Make the script executable
    os.chmod(script_path, 0o755)
    
    print(f"✓ Created DMG creation script: {script_path}")
    return script_path

def create_license_file():
    """Create license file if needed"""
    if os.path.exists("LICENSE.txt"):
        return
    
    with open("LICENSE.txt", "w") as f:
        f.write(f"""SOFTWARE LICENSE AGREEMENT FOR {APP_NAME}

PLEASE READ THIS LICENSE AGREEMENT CAREFULLY BEFORE USING THE SOFTWARE.

By installing this software, you agree to be bound by the terms of this agreement.

1. GRANT OF LICENSE
This application is licensed, not sold. This license gives you the right to install and use the software on your computer.

2. DESCRIPTION OF OTHER RIGHTS AND LIMITATIONS
The software will collect information about your WiFi connections for attendance tracking purposes.
You may not reverse engineer, decompile, or disassemble the software.

3. COPYRIGHT
All title and copyrights in and to the software are owned by {APP_AUTHOR}.

4. PRIVACY POLICY
The application collects the following information:
- Your WiFi connection details
- Computer name and MAC address
- IP address
- Connection timestamps

This information is used solely for attendance tracking purposes.
""")
    
    print("✓ Created LICENSE.txt")

def build_app(spec_path):
    """Build macOS app using PyInstaller"""
    print("Building application with PyInstaller...")
    result = subprocess.run(["pyinstaller", "--clean", spec_path], capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"✗ PyInstaller failed: {result.stderr}")
        return False
    else:
        print("✓ PyInstaller build successful")
        return True

def build_dmg(dmg_script):
    """Build DMG installer"""
    print("Building DMG installer...")
    result = subprocess.run([f"./{dmg_script}"], shell=True, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"✗ DMG creation failed: {result.stderr}")
        return False
    else:
        dmg_path = os.path.join("dist", f"{APP_NAME}-{APP_VERSION}.dmg")
        print(f"✓ DMG created successfully: {dmg_path}")
        return True

def main():
    parser = argparse.ArgumentParser(description=f'Build {APP_NAME} for macOS')
    args = parser.parse_args()
    
    # Check if running on macOS
    if platform.system() != "Darwin":
        print("This script must be run on macOS.")
        sys.exit(1)
    
    # Ensure we have all dependencies
    if not ensure_dependencies():
        sys.exit(1)
    
    # Create icon file if needed
    create_icon_file()
    
    # Create license file
    create_license_file()
    
    # Create PyInstaller spec
    spec_path = create_pyinstaller_spec()
    
    # Create DMG script
    dmg_script = create_dmg_script()
    
    # Build app
    if not build_app(spec_path):
        sys.exit(1)
    
    # Build DMG
    if not build_dmg(dmg_script):
        sys.exit(1)
    
    print(f"\nBuild completed successfully!")
    print(f"DMG installer: dist/{APP_NAME}-{APP_VERSION}.dmg")

if __name__ == "__main__":
    main()