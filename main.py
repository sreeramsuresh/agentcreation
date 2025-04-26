#!/usr/bin/env python3
# main.py - Entry Point for Attendance Tracker Application

import os
import sys
import time
import importlib.util
import traceback
import platform
from datetime import datetime

def import_module_from_file(module_name, file_path):
    """Import a module from a file path"""
    try:
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        print(f"Error importing module {module_name} from {file_path}: {str(e)}")
        traceback.print_exc()
        sys.exit(1)

def setup_autostart(enable=True):
    """Set up application to run at system startup"""
    script_path = os.path.abspath(__file__)
    
    try:
        if platform.system() == "Windows":
            import winreg
            startup_key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE
            )
            
            if enable:
                winreg.SetValueEx(
                    startup_key,
                    "AttendanceTracker",
                    0,
                    winreg.REG_SZ,
                    f'pythonw "{script_path}"'
                )
            else:
                try:
                    winreg.DeleteValue(startup_key, "AttendanceTracker")
                except FileNotFoundError:
                    pass
                    
            winreg.CloseKey(startup_key)
            
        elif platform.system() == "Darwin":  # macOS
            plist_path = os.path.expanduser("~/Library/LaunchAgents/com.attendance.tracker.plist")
            
            if enable:
                plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.attendance.tracker</string>
    <key>ProgramArguments</key>
    <array>
        <string>python3</string>
        <string>{script_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
"""
                os.makedirs(os.path.dirname(plist_path), exist_ok=True)
                with open(plist_path, "w") as f:
                    f.write(plist_content)
                
                # Load the plist
                os.system(f"launchctl load {plist_path}")
            else:
                if os.path.exists(plist_path):
                    # Unload the plist
                    os.system(f"launchctl unload {plist_path}")
                    os.remove(plist_path)
                    
        else:  # Linux
            autostart_dir = os.path.expanduser("~/.config/autostart")
            desktop_file = os.path.join(autostart_dir, "attendance-tracker.desktop")
            
            if enable:
                os.makedirs(autostart_dir, exist_ok=True)
                
                desktop_content = f"""[Desktop Entry]
Type=Application
Name=Attendance Tracker
Exec=python3 {script_path}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
"""
                with open(desktop_file, "w") as f:
                    f.write(desktop_content)
                
                # Make executable
                os.chmod(desktop_file, 0o755)
            else:
                if os.path.exists(desktop_file):
                    os.remove(desktop_file)
                    
        return True
    except Exception as e:
        print(f"Error setting up autostart: {str(e)}")
        traceback.print_exc()
        return False

def create_log_entry(message):
    """Create a log entry with timestamp"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if not script_dir:
        script_dir = os.getcwd()
    
    log_dir = os.path.join(os.path.expanduser("~"), ".attendance_tracker")
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, "startup.log")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with open(log_file, "a") as f:
        f.write(f"{timestamp} - {message}\n")

def main():
    try:
        # Create log entry
        create_log_entry("Application starting")
        
        # Get directory of this script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        if not script_dir:
            script_dir = os.getcwd()
        
        # Import the three parts
        sys.path.append(script_dir)
        
        # Import Part 1 (Installation, UI, and System Tray)
        create_log_entry("Loading part1.py")
        part1_path = os.path.join(script_dir, "part1.py")
        part1 = import_module_from_file("part1", part1_path)
        
        # Import Part 2 (Authentication and API Communication)
        create_log_entry("Loading part2.py")
        part2_path = os.path.join(script_dir, "part2.py")
        part2 = import_module_from_file("part2", part2_path)
        
        # Import Part 3 (WiFi Monitoring and Attendance Tracking)
        create_log_entry("Loading part3.py")
        part3_path = os.path.join(script_dir, "part3.py")
        part3 = import_module_from_file("part3", part3_path)
        
        # Create app instance
        create_log_entry("Creating app instance")
        app = part1.AttendanceApp()
        
        # Extend with authentication functionality
        create_log_entry("Extending app with authentication")
        app = part2.extend_app_authentication(app)
        
        # Extend with WiFi monitoring
        create_log_entry("Extending app with WiFi monitoring")
        app = part3.extend_app_wifi_monitoring(app)
        
        # Create a simple default icon if it doesn't exist
        icon_path = os.path.join(script_dir, "icon.png")
        if not os.path.exists(icon_path):
            try:
                from PIL import Image
                img = Image.new('RGB', (64, 64), color=(66, 133, 244))
                img.save(icon_path)
                create_log_entry(f"Created default icon at {icon_path}")
            except Exception as e:
                create_log_entry(f"Warning: Could not create default icon: {str(e)}")
        
        # Check if already logged in and act accordingly
        create_log_entry("Checking login status")
        if app.check_login():
            create_log_entry("User is logged in, showing main window")
            # Wait a moment to ensure UI is ready
            time.sleep(0.2)
            
            # Safely show main window only if root doesn't exist or hasn't been destroyed
            if not hasattr(app, 'root') or app.root is None:
                app.show_main_window()
            else:
                try:
                    # Test if the root window is still valid
                    app.root.winfo_exists()
                    app.show_main_window()
                except (AttributeError, tk.TclError):
                    # If there's an error, create a new main window
                    app.root = None
                    app.show_main_window()
        else:
            create_log_entry("User not logged in, showing login window")
            # Wait a moment to ensure tray icon is ready
            time.sleep(0.2)
            app.show_login()
        
    except Exception as e:
        error_msg = f"Error in main application: {str(e)}"
        create_log_entry(error_msg)
        print(error_msg)
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()