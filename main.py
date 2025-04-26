#!/usr/bin/env python3
# main.py - Entry Point for Attendance Tracker Application

import os
import sys
import time
import importlib.util
import traceback

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

def main():
    try:
        # Get directory of this script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        if not script_dir:
            script_dir = os.getcwd()
        
        # Import the three parts
        sys.path.append(script_dir)
        
        # Import Part 1 (Installation, UI, and System Tray)
        part1_path = os.path.join(script_dir, "part1.py")
        part1 = import_module_from_file("part1", part1_path)
        
        # Import Part 2 (Authentication and API Communication)
        part2_path = os.path.join(script_dir, "part2.py")
        part2 = import_module_from_file("part2", part2_path)
        
        # Import Part 3 (WiFi Monitoring and Attendance Tracking)
        part3_path = os.path.join(script_dir, "part3.py")
        part3 = import_module_from_file("part3", part3_path)
        
        # Create app instance
        app = part1.AttendanceApp()
        
        # Extend with authentication functionality
        app = part2.extend_app_authentication(app)
        
        # Extend with WiFi monitoring
        app = part3.extend_app_wifi_monitoring(app)
        
        # Create a simple default icon if it doesn't exist
        icon_path = os.path.join(script_dir, "icon.png")
        if not os.path.exists(icon_path):
            try:
                from PIL import Image
                img = Image.new('RGB', (64, 64), color=(66, 133, 244))
                img.save(icon_path)
                print(f"Created default icon at {icon_path}")
            except Exception as e:
                print(f"Warning: Could not create default icon: {str(e)}")
        
        # Check if already logged in and act accordingly
        if app.check_login():
            # Wait a moment to ensure UI is ready
            time.sleep(0.2)
            app.show_main_window()
        else:
            # Wait a moment to ensure tray icon is ready
            time.sleep(0.2)
            app.show_login()
        
    except Exception as e:
        print(f"Error in main application: {str(e)}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()