#!/usr/bin/env python3
# Part 2: Authentication and API Communication

import os
import json
import time
import requests
import threading
import keyring
from urllib.parse import urljoin
from datetime import datetime, timedelta
import uuid
import platform
import subprocess
import tkinter as tk
from PIL import Image

class ApiClient:
    def __init__(self, app):
        self.app = app
        self.base_url = app.config.get("api_base_url", "http://localhost:9600")
        self.access_token = None
        self.user_data = None
        self.token_service_name = "AttendanceTracker"
        self.token_username = "access_token"
        self.offline_mode = False
        self.token_expiry = None
        self.refresh_token = None
        
        # Try to load saved token
        self._load_token()
        
        # Start token refresh thread if token exists
        if self.access_token and self.refresh_token:
            self._start_token_refresh_thread()
    
    def _load_token(self):
        """Load saved token from secure storage"""
        try:
            token = keyring.get_password(self.token_service_name, self.token_username)
            if token:
                saved_data = json.loads(token)
                self.access_token = saved_data.get("token")
                self.refresh_token = saved_data.get("refresh_token")
                self.token_expiry = saved_data.get("expiry")
                self.user_data = saved_data.get("user_data")
                self.app.user_email = saved_data.get("email")
                
                # Check if token is expired
                if self.token_expiry and time.time() > self.token_expiry:
                    self.app.log("Saved token is expired, will try to refresh")
                    # We'll still set is_logged_in to True and try to refresh in the background
                
                self.app.is_logged_in = True
                self.app.log("Loaded saved authentication token")
                return True
        except Exception as e:
            self.app.log(f"Error loading saved token: {str(e)}", "error")
        return False
    
    def _save_token(self, token, refresh_token=None, expiry=None, user_data=None, email=None):
        """Save token to secure storage"""
        try:
            # Use existing values if not provided
            refresh_token = refresh_token or self.refresh_token
            user_data = user_data or self.user_data
            email = email or self.app.user_email
            expiry = expiry or self.token_expiry
            
            saved_data = {
                "token": token,
                "refresh_token": refresh_token,
                "expiry": expiry,
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
    
    def _refresh_token_task(self):
        """Background task to refresh token before it expires"""
        while self.running and self.access_token and self.refresh_token:
            # Calculate time until token expires
            if self.token_expiry:
                now = time.time()
                time_until_expiry = self.token_expiry - now
                
                # If token expires in less than 5 minutes, refresh it
                if time_until_expiry < 300:
                    self.app.log("Token is about to expire, refreshing...")
                    self._refresh_token_now()
                
                # Sleep for a while (check every minute)
                time.sleep(60)
            else:
                # If we don't know when token expires, check every 30 minutes
                time.sleep(1800)
    
    def _start_token_refresh_thread(self):
        """Start background thread for token refresh"""
        self.running = True
        self.refresh_thread = threading.Thread(target=self._refresh_token_task, daemon=True)
        self.refresh_thread.start()
    
    def _stop_token_refresh_thread(self):
        """Stop token refresh thread"""
        self.running = False
        if hasattr(self, 'refresh_thread') and self.refresh_thread.is_alive():
            self.refresh_thread.join(timeout=1.0)
    
    def _refresh_token_now(self):
        """Refresh the access token using refresh token"""
        if not self.refresh_token:
            self.app.log("No refresh token available", "warning")
            return False
            
        url = urljoin(self.base_url, "/api/desktop/refresh-token")
        payload = {"refresh_token": self.refresh_token}
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    # Extract and store new tokens
                    token_data = data.get("data", {})
                    new_token = token_data.get("accessToken")
                    new_refresh_token = token_data.get("refreshToken")
                    expiry = time.time() + token_data.get("expiresIn", 3600)
                    
                    if new_token:
                        self.access_token = new_token
                        if new_refresh_token:
                            self.refresh_token = new_refresh_token
                        self.token_expiry = expiry
                        
                        # Save updated tokens
                        self._save_token(new_token, new_refresh_token, expiry)
                        
                        self.app.log("Token refreshed successfully")
                        return True
            
            self.app.log(f"Failed to refresh token: {response.status_code}", "warning")
            return False
            
        except requests.RequestException as e:
            self.app.log(f"Token refresh error: {str(e)}", "error")
            # Enter offline mode if we can't reach the server
            self.offline_mode = True
            return False
    
    def check_online_status(self):
        """Check if we can connect to the API server"""
        try:
            response = requests.get(self.base_url, timeout=5)
            self.offline_mode = False
            return True
        except requests.RequestException:
            self.offline_mode = True
            return False
    
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
            # First check if we're online
            if not self.check_online_status():
                if callback:
                    callback(False, "Cannot connect to server. Check your internet connection.")
                return
                
            try:
                self.app.log(f"Sending login request with payload: {json.dumps(payload)}")
                response = requests.post(url, json=payload, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        # Extract and store token
                        user_data = data.get("data", {})
                        token = user_data.get("accessToken")
                        refresh_token = user_data.get("refreshToken")
                        expires_in = user_data.get("expiresIn", 3600)
                        
                        if token:
                            self.access_token = token
                            self.refresh_token = refresh_token
                            self.token_expiry = time.time() + expires_in
                            self.user_data = user_data
                            self.app.user_email = email
                            self.app.is_logged_in = True
                            
                            # Save token securely
                            self._save_token(token, refresh_token, self.token_expiry, user_data, email)
                            
                            # Start token refresh thread
                            self._start_token_refresh_thread()
                            
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
                self.offline_mode = True
                
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
            # Always stop the token refresh thread
            self._stop_token_refresh_thread()
            
            try:
                # Only attempt server communication if online
                if not self.offline_mode:
                    response = requests.post(url, headers=headers, timeout=10)
                    
                    if response.status_code == 200:
                        self.app.log("User logged out successfully on server")
                
                # Clear token regardless of response or online status
                self.access_token = None
                self.refresh_token = None
                self.token_expiry = None
                self.user_data = None
                self.app.is_logged_in = False
                self._clear_token()
                
                self.app.log("User logged out locally")
                
                if callback:
                    callback(True, "Logout successful")
                        
            except requests.RequestException as e:
                self.app.log(f"Logout request error: {str(e)}", "error")
                self.offline_mode = True
                
                # Still clear local token
                self.access_token = None
                self.refresh_token = None
                self.token_expiry = None
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
            # If we're in offline mode, don't even try to connect
            if self.offline_mode:
                self.app.log("In offline mode, storing connection data locally", "info")
                if callback:
                    callback(False, "In offline mode, connection data stored locally")
                return
                
            try:
                # Define headers for authentication
                headers = {"Authorization": f"Bearer {self.access_token}"}  # Add this line
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
                
                # If unauthorized, try to refresh token and retry
                if response.status_code == 401:
                    self.app.log("Unauthorized while tracking connection, trying to refresh token", "warning")
                    if self._refresh_token_now():
                        # Try again with new token
                        headers = {"Authorization": f"Bearer {self.access_token}"}
                        response = requests.post(url, json=payload, headers=headers, timeout=10)
                        
                        if response.status_code == 200:
                            data = response.json()
                            if data.get("success"):
                                if callback:
                                    callback(True, "Connection tracked successfully after token refresh", data.get("data"))
                                return
                
                # Handle error
                self.app.log(f"Connection tracking failed with status code {response.status_code}", "error")
                
                if callback:
                    callback(False, f"Failed to track connection: {response.reason}")
                    
            except requests.RequestException as e:
                self.app.log(f"Connection tracking request error: {str(e)}", "error")
                self.offline_mode = True
                
                if callback:
                    callback(False, "Connection error. Connection data will be stored locally.")
        
        # Run the tracking request in a separate thread
        threading.Thread(target=_do_track).start()

# Provide an explicit 'extend_app_authentication' function that must be exported
def extend_app_authentication(app):
    """
    Extend AttendanceApp with authentication functions
    This is the main exported function for this module
    """
    # Initialize API client
    app.api_client = ApiClient(app)
    
    # Add a status indicator for online/offline mode
    app.is_online = True  # Default to online
    
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
        # Safe access to status_var
        if hasattr(app, 'status_var'):
            app.status_var.set("Logging out...")
        else:
            print("Logging out...")
        
        def logout_callback(success, message):
            if success:
                if hasattr(app, 'status_var'):
                    app.status_var.set("Logged out")
                else:
                    print("Logged out")
                    
                # Safely destroy the window if it exists
                if app.root and hasattr(app.root, 'winfo_exists') and app.root.winfo_exists():
                    try:
                        app.root.destroy()
                    except:
                        pass
                app.root = None
                
                # Important: Show the login window immediately
                app.show_login()
            else:
                if hasattr(app, 'status_var'):
                    app.status_var.set(message)
                else:
                    print(f"Logout error: {message}")
        
        app.api_client.logout(logout_callback)
    
    app.handle_logout = handle_logout_extended
    
    # Add a check_login function
    def check_login():
        """Check if user is already logged in with saved token"""
        if app.api_client.access_token:
            app.is_logged_in = True
            app.user_email = app.api_client.user_data.get("email") if app.api_client.user_data else None
            
            # Start a background check for token validity/refresh
            def background_token_check():
                # Wait a moment to ensure app is fully initialized
                time.sleep(1)
                # Try to check online status
                app.api_client.check_online_status()
                # If token needs refresh, do it
                if app.api_client.token_expiry and time.time() > app.api_client.token_expiry - 300:
                    app.api_client._refresh_token_now()
            
            threading.Thread(target=background_token_check, daemon=True).start()
            
            return True
        return False
    
    app.check_login = check_login
    
    # Add a function to update online/offline status display
    def update_online_status():
        if hasattr(app, 'online_status_var'):
            status = "Online" if not app.api_client.offline_mode else "Offline"
            app.online_status_var.set(f"Status: {status}")
            
            # Change color based on status
            if hasattr(app, 'online_status_label'):
                color = "green" if not app.api_client.offline_mode else "red"
                app.online_status_label.config(fg=color)
    
    app.update_online_status = update_online_status
    
    # Modify the show_main_window method to display online/offline status
    original_show_main_window = app.show_main_window
    
    def show_main_window_extended():
        # Check if root exists and is valid
        if hasattr(app, 'root') and app.root:
            try:
                # Test if the root window is still valid
                app.root.winfo_exists()
                # If valid, destroy existing widgets
                for widget in app.root.winfo_children():
                    widget.destroy()
            except (AttributeError, tk.TclError):
                # If not valid, set to None so a new one will be created
                app.root = None
        
        # Call original function which will create a new window if needed
        original_show_main_window()
        
        # Add online/offline status indicator if it doesn't exist
        if hasattr(app, 'root') and app.root and not hasattr(app, 'online_status_var'):
            status_frame = None
            
            # Find the status frame if it exists
            for widget in app.root.winfo_children():
                if hasattr(widget, 'winfo_children'):
                    for child in widget.winfo_children():
                        if hasattr(child, 'cget') and child.cget('text') == "Connection Status":
                            status_frame = child
                            break
            
            if status_frame:
                app.online_status_var = tk.StringVar(value="Status: Checking...")
                app.online_status_label = tk.Label(status_frame, textvariable=app.online_status_var)
                app.online_status_label.pack(anchor="w")
                
                # Update status
                app.update_online_status()
                
                # Periodically check online status
                def check_status_periodically():
                    while app.running and app.is_logged_in:
                        app.api_client.check_online_status()
                        app.update_online_status()
                        time.sleep(30)  # Check every 30 seconds
                
                threading.Thread(target=check_status_periodically, daemon=True).start()
    
    app.show_main_window = show_main_window_extended
    
    # Add tray icon click handler
    def on_tray_icon_clicked(icon):
        if app.is_logged_in:
            app.show_main_window()
        else:
            app.show_login()
            
    # If the app already has a tray icon, update its behavior
    if hasattr(app, 'tray_icon') and app.tray_icon:
        try:
            app.tray_icon.on_click = on_tray_icon_clicked
        except:
            # Some implementations might not support changing callbacks
            pass
    
    # Modify the minimize_to_tray method
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