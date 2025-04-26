#!/usr/bin/env python3
# Part 3: WiFi Monitoring and Attendance Tracking

import os
import sys
import time
import json
import socket
import platform
import threading
import subprocess
import sqlite3
from datetime import datetime, timedelta
import tkinter as tk

# Connection tracking database setup
DB_FILE = os.path.join(os.path.expanduser("~"), ".attendance_tracker", "connections.db")

class ConnectionDatabase:
    """Local database for storing connection events when offline"""
    def __init__(self):
        self.db_path = DB_FILE
        self._initialize_db()
    
    def _initialize_db(self):
        """Create database and tables if they don't exist"""
        db_dir = os.path.dirname(self.db_path)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)
            
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create table for connection events
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS connection_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            ssid TEXT NOT NULL,
            email TEXT NOT NULL,
            ip_address TEXT,
            mac_address TEXT,
            computer_name TEXT,
            timestamp REAL,
            connection_start_time REAL,
            connection_start_time_formatted TEXT,
            connection_duration REAL,
            connection_duration_formatted TEXT,
            synced INTEGER DEFAULT 0
        )
        ''')
        
        # Create table for current connection state
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS connection_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            is_connected INTEGER,
            ssid TEXT,
            connection_start_time REAL,
            last_updated REAL
        )
        ''')
        
        conn.commit()
        conn.close()
    
    def add_event(self, event_data):
        """Add a connection event to the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        columns = ', '.join(event_data.keys())
        placeholders = ', '.join(['?' for _ in event_data])
        values = tuple(event_data.values())
        
        cursor.execute(
            f"INSERT INTO connection_events ({columns}) VALUES ({placeholders})",
            values
        )
        
        conn.commit()
        event_id = cursor.lastrowid
        conn.close()
        
        return event_id
    
    def save_connection_state(self, is_connected, ssid=None, connection_start_time=None):
        """Save current connection state to survive app restarts"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Clear previous state
        cursor.execute("DELETE FROM connection_state")
        
        # Insert new state
        cursor.execute(
            "INSERT INTO connection_state (is_connected, ssid, connection_start_time, last_updated) VALUES (?, ?, ?, ?)",
            (1 if is_connected else 0, ssid or "", connection_start_time or time.time(), time.time())
        )
        
        conn.commit()
        conn.close()
    
    def get_connection_state(self):
        """Get saved connection state"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM connection_state ORDER BY last_updated DESC LIMIT 1")
        row = cursor.fetchone()
        
        conn.close()
        
        if row:
            return {
                "is_connected": bool(row["is_connected"]),
                "ssid": row["ssid"],
                "connection_start_time": row["connection_start_time"],
                "last_updated": row["last_updated"]
            }
        else:
            return {
                "is_connected": False,
                "ssid": None,
                "connection_start_time": None,
                "last_updated": None
            }
    
    def get_unsynced_events(self):
        """Get all unsynced events"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM connection_events WHERE synced = 0 ORDER BY timestamp ASC")
        rows = cursor.fetchall()
        
        events = []
        for row in rows:
            events.append(dict(row))
        
        conn.close()
        return events
    
    def mark_as_synced(self, event_id):
        """Mark an event as synced with the server"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("UPDATE connection_events SET synced = 1 WHERE id = ?", (event_id,))
        
        conn.commit()
        conn.close()

class WiFiMonitor:
    def __init__(self, app):
        self.app = app
        self.target_ssid = app.config.get("target_ssid", "Vadakkemadom 5G")
        self.current_ssid = None
        self.last_ssid = None
        self.is_connected_to_target = False
        self.connection_start_time = None
        self.check_interval = 5  # seconds
        self.running = True
        self.offline_db = ConnectionDatabase()
        
        # Load previous connection state to handle app restarts
        self._load_connection_state()
        
        # Start monitoring thread
        self.monitor_thread = threading.Thread(target=self.monitor_wifi, daemon=True)
        self.monitor_thread.start()
    
    def _load_connection_state(self):
        """Load saved connection state to handle restarts"""
        state = self.offline_db.get_connection_state()
        if state["is_connected"] and state["ssid"] == self.target_ssid:
            self.app.log("Restoring previous connection state")
            self.is_connected_to_target = True
            self.last_ssid = state["ssid"]
            self.connection_start_time = state["connection_start_time"]
        else:
            self.is_connected_to_target = False
            self.connection_start_time = None
            
    def get_current_ssid(self):
        """Get the current WiFi SSID (platform-specific)"""
        try:
            if platform.system() == "Windows":
                # Windows implementation using netsh
                output = subprocess.check_output(["netsh", "wlan", "show", "interfaces"], 
                                                universal_newlines=True)
                for line in output.split("\n"):
                    if "SSID" in line and "BSSID" not in line:
                        ssid = line.split(":", 1)[1].strip()
                        return ssid if ssid else None
                        
            elif platform.system() == "Darwin":  # macOS
                # macOS implementation using airport
                airport_path = "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport"
                output = subprocess.check_output([airport_path, "-I"], universal_newlines=True)
                for line in output.split("\n"):
                    if " SSID:" in line:
                        ssid = line.split(":", 1)[1].strip()
                        return ssid if ssid else None
                        
            else:  # Linux
                # Linux implementation using nmcli
                output = subprocess.check_output(["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"], 
                                               universal_newlines=True)
                for line in output.split("\n"):
                    if line.startswith("yes:"):
                        ssid = line.split(":", 1)[1].strip()
                        return ssid if ssid else None
                        
        except (subprocess.SubprocessError, FileNotFoundError, OSError) as e:
            self.app.log(f"Error getting WiFi SSID: {str(e)}", "error")
            
        return None
        
    def get_local_ip(self):
        """Get the local IP address"""
        try:
            # Create a socket and connect to an external server to get local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            try:
                # Fallback method
                host_name = socket.gethostname()
                ip = socket.gethostbyname(host_name)
                return ip
            except:
                return "127.0.0.1"
    
    def format_duration(self, seconds):
        """Format seconds to HH:MM:SS"""
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"
    
    def monitor_wifi(self):
        """Main WiFi monitoring loop"""
        self.app.log("WiFi monitoring started")
        
        while self.running:
            if not self.app.is_logged_in:
                time.sleep(self.check_interval)
                continue
                
            # Get current SSID
            self.current_ssid = self.get_current_ssid()
            self.app.current_ssid = self.current_ssid  # Share with main app
            
            # Update UI if available
            if hasattr(self.app, 'update_wifi_status'):
                self.app.update_wifi_status(bool(self.current_ssid), self.current_ssid)
            
            # Check if SSID changed
            if self.current_ssid != self.last_ssid:
                # If we're now connected to target network
                if self.current_ssid == self.target_ssid:
                    self.app.log(f"Connected to target WiFi network: {self.target_ssid}")
                    self.is_connected_to_target = True
                    self.connection_start_time = time.time()
                    
                    # Save connection state to database
                    self.offline_db.save_connection_state(True, self.target_ssid, self.connection_start_time)
                    
                    # Prepare connection event data
                    connection_data = {
                        "ssid": self.target_ssid,
                        "ip_address": self.get_local_ip(),
                        "mac_address": self.app.get_mac_address(),
                        "computer_name": self.app.get_computer_name(),
                        "timestamp": time.time(),
                        "connection_start_time": self.connection_start_time,
                        "connection_start_time_formatted": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    
                    # First save locally
                    connection_data["event_type"] = "connect"
                    connection_data["email"] = self.app.user_email or ""
                    local_event_id = self.offline_db.add_event(connection_data)
                    
                    # Send connect event to API if possible
                    if hasattr(self.app, 'api_client'):
                        def callback(success, message, data=None):
                            if success:
                                # Mark as synced in local DB
                                self.offline_db.mark_as_synced(local_event_id)
                                self.app.log(f"Connection event synced, event ID: {local_event_id}")
                        
                        self.app.api_client.track_connection("connect", connection_data, callback)
                
                # If we were connected to target but now disconnected
                elif self.last_ssid == self.target_ssid:
                    self.app.log(f"Disconnected from target WiFi network: {self.target_ssid}")
                    self.is_connected_to_target = False
                    
                    # Update connection state in database
                    self.offline_db.save_connection_state(False)
                    
                    # Calculate connection duration
                    if self.connection_start_time:
                        duration = time.time() - self.connection_start_time
                        formatted_duration = self.format_duration(duration)
                        
                        self.app.log(f"Connection duration: {formatted_duration}")
                        
                        # Prepare disconnection event data
                        disconnection_data = {
                            "ssid": self.target_ssid,
                            "ip_address": self.get_local_ip(),
                            "mac_address": self.app.get_mac_address(),
                            "computer_name": self.app.get_computer_name(),
                            "timestamp": time.time(),
                            "connection_start_time": self.connection_start_time,
                            "connection_start_time_formatted": datetime.fromtimestamp(
                                self.connection_start_time).strftime("%Y-%m-%d %H:%M:%S"),
                            "connection_duration": duration,
                            "connection_duration_formatted": formatted_duration
                        }
                        
                        # First save locally
                        disconnection_data["event_type"] = "disconnect"
                        disconnection_data["email"] = self.app.user_email or ""
                        local_event_id = self.offline_db.add_event(disconnection_data)
                        
                        # Send disconnect event to API if possible
                        if hasattr(self.app, 'api_client'):
                            def callback(success, message, data=None):
                                if success:
                                    # Mark as synced in local DB
                                    self.offline_db.mark_as_synced(local_event_id)
                                    self.app.log(f"Disconnection event synced, event ID: {local_event_id}")
                            
                            self.app.api_client.track_connection("disconnect", disconnection_data, callback)
                    
                self.last_ssid = self.current_ssid
            
            # Even if SSID didn't change, periodically update the saved state
            if self.is_connected_to_target and self.connection_start_time:
                self.offline_db.save_connection_state(True, self.target_ssid, self.connection_start_time)
            
            # Sync any offline events if we're online
            self.sync_offline_events()
            
            # Sleep before next check
            time.sleep(self.check_interval)
            
    def sync_offline_events(self):
        """Sync offline events to the server if possible"""
        if not hasattr(self.app, 'api_client') or not self.app.api_client.access_token:
            return
            
        # Don't try to sync if we're in offline mode
        if hasattr(self.app.api_client, 'offline_mode') and self.app.api_client.offline_mode:
            return
            
        # Get unsynced events
        events = self.offline_db.get_unsynced_events()
        if not events:
            return
            
        self.app.log(f"Attempting to sync {len(events)} offline events")
            
        for event in events:
            # Remove SQLite-specific fields
            event_id = event.pop('id', None)
            event.pop('synced', None)
            
            # Send to API
            def callback(success, message, data=None, _event_id=event_id):  # Use default arg to capture current event_id
                if success:
                    self.offline_db.mark_as_synced(_event_id)
                    self.app.log(f"Synced offline event {_event_id}: {event['event_type']}")
            
            self.app.api_client.track_connection(event['event_type'], event, callback)
            
            # Sleep briefly to avoid API rate limits
            time.sleep(0.5)
    
    def stop(self):
        """Stop the monitoring thread"""
        self.running = False
        if self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=1.0)
        self.app.log("WiFi monitoring stopped")

# Extend AttendanceApp with WiFi monitoring
def extend_app_wifi_monitoring(app):
    # Initialize WiFi monitor
    app.wifi_monitor = WiFiMonitor(app)
    
    # Override exit handler to stop WiFi monitor
    original_exit_app = app.exit_app
    
    def exit_app_extended(icon=None):
        # Stop WiFi monitor
        if hasattr(app, 'wifi_monitor'):
            app.wifi_monitor.stop()
        
        # Call original exit function
        original_exit_app(icon)
    
    app.exit_app = exit_app_extended
    
    # Override the update_wifi_status method to show more detail
    original_update_wifi_status = app.update_wifi_status
    
    def update_wifi_status_extended(connected, ssid=None):
        if not hasattr(app, 'wifi_status_var') or not hasattr(app, 'connection_status_var'):
            return
            
        if connected and ssid:
            app.wifi_status_var.set(f"Connected to: {ssid}")
            
            if ssid == app.config["target_ssid"]:
                app.connection_status_var.set("✓ Connected to office network")
                
                # Add duration info if available
                if hasattr(app, 'wifi_monitor') and app.wifi_monitor.connection_start_time:
                    duration = time.time() - app.wifi_monitor.connection_start_time
                    formatted_duration = app.wifi_monitor.format_duration(duration)
                    
                    # Create a duration variable if it doesn't exist
                    if not hasattr(app, 'connection_duration_var'):
                        if app.root and hasattr(app.root, 'winfo_exists') and app.root.winfo_exists():
                            # Find status frame
                            status_frame = None
                            for widget in app.root.winfo_children():
                                if hasattr(widget, 'winfo_children'):
                                    for child in widget.winfo_children():
                                        if hasattr(child, 'cget') and child.cget('text') == "Connection Status":
                                            status_frame = child
                                            break
                            
                            if status_frame:
                                app.connection_duration_var = tk.StringVar(value="")
                                duration_label = tk.Label(status_frame, textvariable=app.connection_duration_var)
                                duration_label.pack(anchor="w")
                    
                    # Update duration if variable exists
                    if hasattr(app, 'connection_duration_var'):
                        app.connection_duration_var.set(f"Duration: {formatted_duration}")
            else:
                app.connection_status_var.set("✗ Not connected to office network")
                # Clear duration if not connected to target
                if hasattr(app, 'connection_duration_var'):
                    app.connection_duration_var.set("")
        else:
            app.wifi_status_var.set("Not connected to WiFi")
            app.connection_status_var.set("✗ Not connected to office network")
            # Clear duration if not connected
            if hasattr(app, 'connection_duration_var'):
                app.connection_duration_var.set("")
    
    app.update_wifi_status = update_wifi_status_extended
    
    return app

# Main integration function to combine all parts
def main():
    from part1 import AttendanceApp
    
    # Create app instance
    app = AttendanceApp()
    
    # Extend with authentication functionality
    from part2 import extend_app_authentication
    app = extend_app_authentication(app)
    
    # Extend with WiFi monitoring
    app = extend_app_wifi_monitoring(app)
    
    # Check if already logged in and act accordingly
    if app.check_login():
        app.show_main_window()
    else:
        app.minimize_to_tray()

if __name__ == "__main__":
    main()