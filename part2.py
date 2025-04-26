#!/usr/bin/env python3
# Part 2: Authentication and API Communication

import os
import json
import time
import requests
import threading
import keyring
from urllib.parse import urljoin
from datetime import datetime
import uuid
import platform
import subprocess

class ApiClient:
    def __init__(self, app):
        self.app = app
        self.base_url = app.config.get("api_base_url", "http://localhost:9600")
        self.access_token = None
        self.user_data = None
        self.token_service_name = "AttendanceTracker"
        self.token_username = "access_token"
        
        # Try to load saved token
        self._load_token()
    
    def _load_token(self):
        """Load saved token from secure storage"""
        try:
            token = keyring.get_password(self.token_service_name, self.token_username)
            if token:
                saved_data = json.loads(token)
                self.access_token = saved_data.get("token")
                self.user_data = saved_data.get("user_data")
                self.app.user_email = saved_data.get("email")
                self.app.is_logged_in = True
                self.app.log("Loaded saved authentication token")
                return True
        except Exception as e:
            self.app.log(f"Error loading saved token: {str(e)}", "error")
        return False
    
    def _save_token(self, token, user_data, email):
        """Save token to secure storage"""
        try:
            saved_data = {
                "token": token,
                "user_data": user_data,
                "email": email
            }
            keyring.set_password(self.token_service_name, self.token_username, json.dumps(saved_data))
            self.app.log("Saved authentication token")
        except Exception as e:
            self.app.log(f"Error saving token: {str(e)}", "error")
    
    def _clear_token(self):
        """Clear saved token from secure storage"""
        try:
            keyring.delete_password(self.token_service_name, self.token_username)
            self.app.log("Cleared authentication token")
        except Exception as e:
            self.app.log(f"Error clearing token: {str(e)}", "error")
    
    def get_mac_address(self):
        """Get device MAC address"""
        try:
            mac = ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff) 
                           for elements in range(0, 48, 8)][::-1])
            return mac
        except Exception as e:
            self.app.log(f"Error getting MAC address: {str(e)}", "error")
            return "00:00:00:00:00:00"
    
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
                        return ssid if ssid else "Unknown"
                        
            elif platform.system() == "Darwin":  # macOS
                # macOS implementation using airport
                airport_path = "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport"
                output = subprocess.check_output([airport_path, "-I"], universal_newlines=True)
                for line in output.split("\n"):
                    if " SSID:" in line:
                        ssid = line.split(":", 1)[1].strip()
                        return ssid if ssid else "Unknown"
                        
            else:  # Linux
                # Linux implementation using nmcli
                output = subprocess.check_output(["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"], 
                                               universal_newlines=True)
                for line in output.split("\n"):
                    if line.startswith("yes:"):
                        ssid = line.split(":", 1)[1].strip()
                        return ssid if ssid else "Unknown"
                        
        except (subprocess.SubprocessError, FileNotFoundError, OSError) as e:
            self.app.log(f"Error getting WiFi SSID: {str(e)}", "error")
            
        # If we failed to get the SSID, return the target SSID
        return self.app.config.get("target_ssid", "SSAA323")
    
    def login(self, email, password, callback=None):
        """Login to the API and get access token"""
        url = urljoin(self.base_url, "/api/desktop/login")
        
        # Get system information - directly instead of relying on app properties
        mac_address = self.get_mac_address()
        current_ssid = self.get_current_ssid()
        
        self.app.log(f"Login attempt with MAC: {mac_address}, SSID: {current_ssid}")
        
        payload = {
            "email": email,
            "password": password,
            "macAddress": mac_address,
            "ssid": current_ssid
        }
        
        def _do_login():
            try:
                self.app.log(f"Sending login request with payload: {json.dumps(payload)}")
                response = requests.post(url, json=payload, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        # Extract and store token
                        user_data = data.get("data", {})
                        token = user_data.get("accessToken")
                        
                        if token:
                            self.access_token = token
                            self.user_data = user_data
                            self.app.user_email = email
                            self.app.is_logged_in = True
                            
                            # Save token securely
                            self._save_token(token, user_data, email)
                            
                            self.app.log(f"User {email} logged in successfully")
                            
                            if callback:
                                callback(True, "Login successful")
                            return
                
                # Handle specific error cases
                if response.status_code == 400:
                    data = response.json()
                    message = data.get("message", "Login failed")
                    
                    # Check if user is already registered with another device
                    if "already registered" in message.lower():
                        error_msg = "User already registered with another device"
                    else:
                        error_msg = message
                        
                    self.app.log(f"Login failed: {error_msg}", "error")
                    
                    if callback:
                        callback(False, error_msg)
                    return
                        
                elif response.status_code == 401:
                    error_msg = "Invalid email or password"
                    self.app.log(f"Login failed: {error_msg}", "error")
                    
                    if callback:
                        callback(False, error_msg)
                    return
                
                # General error
                self.app.log(f"Login failed with status code {response.status_code}", "error")
                
                if callback:
                    callback(False, f"Login failed: {response.reason}")
                    
            except requests.RequestException as e:
                self.app.log(f"Login request error: {str(e)}", "error")
                
                if callback:
                    callback(False, "Connection error. Please check your internet connection.")
        
        # Run the login request in a separate thread
        threading.Thread(target=_do_login).start()
    
    def logout(self, callback=None):
        """Logout from the API"""
        if not self.access_token:
            if callback:
                callback(True, "Already logged out")
            return
            
        url = urljoin(self.base_url, "/api/desktop/logout")
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        def _do_logout():
            try:
                response = requests.post(url, headers=headers, timeout=10)
                
                # Clear token regardless of response
                self.access_token = None
                self.user_data = None
                self.app.is_logged_in = False
                self._clear_token()
                
                if response.status_code == 200:
                    self.app.log("User logged out successfully")
                    
                    if callback:
                        callback(True, "Logout successful")
                else:
                    self.app.log(f"Logout failed with status code {response.status_code}", "warning")
                    
                    if callback:
                        callback(True, "Logged out locally")
                        
            except requests.RequestException as e:
                self.app.log(f"Logout request error: {str(e)}", "error")
                # Still clear local token
                self.access_token = None
                self.user_data = None
                self.app.is_logged_in = False
                self._clear_token()
                
                if callback:
                    callback(True, "Logged out locally")
        
        # Run the logout request in a separate thread
        threading.Thread(target=_do_logout).start()
    
    def track_connection(self, event_type, connection_data, callback=None):
        """Send connection tracking data to API"""
        if not self.access_token:
            self.app.log("Cannot track connection: Not logged in", "warning")
            if callback:
                callback(False, "Not logged in")
            return
            
        url = urljoin(self.base_url, "/api/desktop/track-connection")
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        # Prepare payload
        payload = {
            "event_type": event_type,
            "ssid": connection_data.get("ssid", ""),
            "email": self.app.user_email,
            "ip_address": connection_data.get("ip_address", ""),
            "mac_address": connection_data.get("mac_address", ""),
            "computer_name": connection_data.get("computer_name", ""),
            "timestamp": connection_data.get("timestamp", time.time()),
            "connection_start_time": connection_data.get("connection_start_time", time.time()),
            "connection_start_time_formatted": connection_data.get("connection_start_time_formatted", 
                                                                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        }
        
        # Add duration fields for disconnect events
        if event_type == "disconnect":
            payload["connection_duration"] = connection_data.get("connection_duration", 0)
            payload["connection_duration_formatted"] = connection_data.get("connection_duration_formatted", "00:00:00")
        
        def _do_track():
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        record_id = data.get("data", {}).get("recordId")
                        
                        if event_type == "connect":
                            self.app.log(f"Connection tracked successfully (ID: {record_id})")
                        else:
                            duration = data.get("data", {}).get("duration", "00:00:00")
                            self.app.log(f"Disconnection tracked successfully (ID: {record_id}, Duration: {duration})")
                        
                        if callback:
                            callback(True, "Connection tracked successfully", data.get("data"))
                        return
                
                # Handle error
                self.app.log(f"Connection tracking failed with status code {response.status_code}", "error")
                
                if callback:
                    callback(False, f"Failed to track connection: {response.reason}")
                    
            except requests.RequestException as e:
                self.app.log(f"Connection tracking request error: {str(e)}", "error")
                
                if callback:
                    callback(False, "Connection error. Connection data will be stored locally.")
        
        # Run the tracking request in a separate thread
        threading.Thread(target=_do_track).start()

# Extend AttendanceApp with authentication functions
def extend_app_authentication(app):
    # Initialize API client
    app.api_client = ApiClient(app)
    
    # Override login handler
    original_handle_login = app.handle_login
    
    def handle_login_extended():
        email = app.email_var.get()
        password = app.password_var.get()
        
        if not email or not password:
            app.status_var.set("Please enter both email and password")
            return
            
        app.status_var.set("Logging in...")
        
        def login_callback(success, message):
            if success:
                app.status_var.set("Login successful")
                app.show_main_window()
            else:
                app.status_var.set(message)
        
        app.api_client.login(email, password, login_callback)
    
    app.handle_login = handle_login_extended
    
    # Override logout handler
    original_handle_logout = app.handle_logout
    
    def handle_logout_extended():
        app.status_var.set("Logging out...")
        
        def logout_callback(success, message):
            if success:
                app.status_var.set("Logged out")
                # Safely destroy the window
                if app.root and hasattr(app.root, 'winfo_exists') and app.root.winfo_exists():
                    try:
                        app.root.destroy()
                    except:
                        pass
                app.root = None
                
                # Short delay before showing login again
                def show_login_delayed():
                    time.sleep(0.1)
                    app.show_login()
                
                threading.Thread(target=show_login_delayed).start()
            else:
                app.status_var.set(message)
        
        app.api_client.logout(logout_callback)
    
    app.handle_logout = handle_logout_extended
    
    # Add a check_login function
    def check_login():
        """Check if user is already logged in with saved token"""
        if app.api_client.access_token:
            app.is_logged_in = True
            app.user_email = app.api_client.user_data.get("email") if app.api_client.user_data else None
            return True
        return False
    
    app.check_login = check_login
    
    # Modify the app startup to show main window if already logged in
    original_minimize_to_tray = app.minimize_to_tray
    
    def minimize_to_tray_extended():
        # Safely check if root exists and withdraw it
        if app.root and hasattr(app.root, 'winfo_exists') and app.root.winfo_exists():
            try:
                app.root.withdraw()
            except Exception as e:
                app.log(f"Error withdrawing window: {str(e)}", "error")
        
        # Auto show login window if not logged in
        if not app.is_logged_in and app.tray_icon:
            # Use a short delay to allow tray icon to appear first
            def delayed_login():
                time.sleep(0.5)
                app.show_login()
            
            threading.Thread(target=delayed_login).start()
    
    app.minimize_to_tray = minimize_to_tray_extended
    
    return app