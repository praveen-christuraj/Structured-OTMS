# ip_service.py
"""
IP Geolocation and Device Detection Service for OTMS
Tracks user location and device information for security monitoring
"""

import requests
import re
import socket
from typing import Dict, Optional, Tuple
from datetime import datetime
import hashlib

class IPService:
    """Handle IP geolocation and device detection"""
    
    # Free IP geolocation API (no key required, 1000 requests/day)
    GEOIP_API = "http://ip-api.com/json/{ip}"
    
    @staticmethod
    def get_client_ip() -> str:
        """
        Get client IP address.
        Returns public IP if available, otherwise localhost.
        """
        try:
            # Try to get public IP (with short timeout)
            response = requests.get("https://api.ipify.org?format=json", timeout=1)
            if response.status_code == 200:
                ip = response.json().get("ip", "127.0.0.1")
                # Return public IP if it's not private
                if ip and not ip.startswith("192.168.") and not ip.startswith("10."):
                    return ip
        except:
            pass
        
        # Fallback to localhost (for local development)
        return "127.0.0.1"
    
    @staticmethod
    def get_location_from_ip(ip_address: str) -> Dict[str, Optional[str]]:
        """
        Get location information from IP address.
        Returns: dict with country, city, region, timezone, etc.
        """
        
        # Skip geolocation for localhost/private IPs
        if ip_address in ["127.0.0.1", "localhost", "::1"] or ip_address.startswith("192.168.") or ip_address.startswith("10."):
            try:
                hostname = socket.gethostname()
            except:
                hostname = "Local Machine"
            
            return {
                "country": "Local Network (LAN)",
                "city": hostname,  # Show computer name
                "region": "Development/LAN",
                "timezone": "Local Time",
                "isp": "Local Network",
                "lat": None,
                "lon": None,
                "country_code": None,
            }
        
        try:
            url = IPService.GEOIP_API.format(ip=ip_address)
            response = requests.get(url, timeout=3)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("status") == "success":
                    return {
                        "country": data.get("country", "Unknown"),
                        "city": data.get("city", "Unknown"),
                        "region": data.get("regionName", "Unknown"),
                        "timezone": data.get("timezone", "Unknown"),
                        "isp": data.get("isp", "Unknown"),
                        "lat": data.get("lat"),
                        "lon": data.get("lon"),
                        "country_code": data.get("countryCode"),
                    }
        except Exception as e:
            print(f"IP geolocation failed: {e}")
        
        # Return default if geolocation fails
        return {
            "country": "Unknown",
            "city": "Unknown",
            "region": "Unknown",
            "timezone": "Unknown",
            "isp": "Unknown",
            "lat": None,
            "lon": None,
            "country_code": None,
        }
    
    @staticmethod
    def parse_user_agent(user_agent: str) -> Dict[str, str]:
        """
        Parse user agent string to extract browser, OS, and device type.
        Enhanced to detect Streamlit apps.
        """
        
        if not user_agent:
            return {
                "browser": "Unknown",
                "os": "Unknown",
                "device_type": "Unknown"
            }
        
        # ========== SPECIAL HANDLING FOR STREAMLIT ==========
        if "Streamlit" in user_agent:
            device_type = "Desktop"
            browser = "Streamlit App"
            
            # Extract OS from Streamlit user agent
            # Format: "Streamlit/1.x.x (Windows; Python 3.x.x)"
            if "Windows" in user_agent:
                os_name = "Windows"
            elif "Darwin" in user_agent or "macOS" in user_agent:
                os_name = "macOS"
            elif "Linux" in user_agent:
                os_name = "Linux"
            else:
                os_name = "Unknown"
            
            return {
                "browser": browser,
                "os": os_name,
                "device_type": device_type
            }
        
        # ========== CONTINUE WITH REGULAR DETECTION ==========
        # Detect device type
        device_type = "Desktop"
        if re.search(r'Mobile|Android|iPhone|iPad|iPod', user_agent, re.I):
            if re.search(r'iPad|Tablet', user_agent, re.I):
                device_type = "Tablet"
            else:
                device_type = "Mobile"
        
        # Detect browser
        browser = "Unknown"
        if "Edg" in user_agent:
            browser = "Microsoft Edge"
        elif "Chrome" in user_agent and "Safari" in user_agent:
            browser = "Google Chrome"
        elif "Firefox" in user_agent:
            browser = "Mozilla Firefox"
        elif "Safari" in user_agent and "Chrome" not in user_agent:
            browser = "Safari"
        elif "MSIE" in user_agent or "Trident" in user_agent:
            browser = "Internet Explorer"
        elif "Opera" in user_agent or "OPR" in user_agent:
            browser = "Opera"
        
        # Detect OS
        os_name = "Unknown"
        if "Windows NT 10" in user_agent:
            os_name = "Windows 10/11"
        elif "Windows NT 6.3" in user_agent:
            os_name = "Windows 8.1"
        elif "Windows NT 6.2" in user_agent:
            os_name = "Windows 8"
        elif "Windows NT 6.1" in user_agent:
            os_name = "Windows 7"
        elif "Windows" in user_agent:
            os_name = "Windows"
        elif "Mac OS X" in user_agent:
            # Extract macOS version if possible
            mac_version = re.search(r'Mac OS X (\d+[._]\d+)', user_agent)
            if mac_version:
                version = mac_version.group(1).replace('_', '.')
                os_name = f"macOS {version}"
            else:
                os_name = "macOS"
        elif "Android" in user_agent:
            # Extract Android version if possible
            android_version = re.search(r'Android (\d+\.?\d*)', user_agent)
            if android_version:
                os_name = f"Android {android_version.group(1)}"
            else:
                os_name = "Android"
        elif "Linux" in user_agent:
            os_name = "Linux"
        elif "iPhone" in user_agent or "iPad" in user_agent:
            # Extract iOS version if possible
            ios_version = re.search(r'OS (\d+[._]\d+)', user_agent)
            if ios_version:
                version = ios_version.group(1).replace('_', '.')
                os_name = f"iOS {version}"
            else:
                os_name = "iOS"
        
        return {
            "browser": browser,
            "os": os_name,
            "device_type": device_type
        }
    
    @staticmethod
    def generate_session_id(username: str, ip_address: str, timestamp: datetime) -> str:
        """Generate unique session ID"""
        data = f"{username}:{ip_address}:{timestamp.isoformat()}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    @staticmethod
    def get_flag_emoji(country_or_code: Optional[str]) -> str:
        """Return a flag emoji for a country name or ISO code. Falls back to white flag."""
        if not country_or_code:
            return "🏳️"
        val = country_or_code.strip()
        if len(val) == 2 and val.isalpha():  # ISO code
            code = val.upper()
        else:
            # Minimal name->code map (extend as needed)
            name_map = {
                "Nigeria": "NG",
                "United States": "US",
                "United Kingdom": "GB",
                "Canada": "CA",
                "India": "IN",
            }
            code = name_map.get(val, "")
        if len(code) != 2:
            return "🏳️"
        # Convert ASCII A-Z to regional indicator symbols
        return chr(ord(code[0].upper()) + 127397) + chr(ord(code[1].upper()) + 127397)
    
    @staticmethod
    def is_suspicious_login(
        username: str,
        ip_address: str,
        previous_ips: list,
        previous_countries: list
    ) -> Tuple[bool, str]:
        """
        Detect suspicious login patterns.
        Returns: (is_suspicious, reason)
        """
        
        # Skip check for localhost
        if ip_address in ["127.0.0.1", "localhost"] or ip_address.startswith("192.168.") or ip_address.startswith("10."):
            return False, ""
        
        # Check 1: New IP from different country
        if previous_ips and ip_address not in previous_ips:
            location = IPService.get_location_from_ip(ip_address)
            current_country = location.get("country", "Unknown")
            
            if previous_countries and current_country not in previous_countries:
                if current_country != "Unknown" and "Local" not in current_country:
                    return True, f"Login from new country: {current_country}"
        
        # Check 2: Rapid logins from different IPs (would need session data)
        # Check 3: Login from known blacklisted IPs (would need blacklist)
        
        return False, ""
    
    @staticmethod
    def get_flag_emoji(country: str) -> str:
        """Get flag emoji for country name"""
        flags = {
            "United States": "🇺🇸",
            "United Kingdom": "🇬🇧",
            "Canada": "🇨🇦",
            "Australia": "🇦🇺",
            "Germany": "🇩🇪",
            "France": "🇫🇷",
            "India": "🇮🇳",
            "China": "🇨🇳",
            "Japan": "🇯🇵",
            "Brazil": "🇧🇷",
            "Russia": "🇷🇺",
            "Mexico": "🇲🇽",
            "South Korea": "🇰🇷",
            "Spain": "🇪🇸",
            "Italy": "🇮🇹",
            "Netherlands": "🇳🇱",
            "Singapore": "🇸🇬",
            "United Arab Emirates": "🇦🇪",
            "Saudi Arabia": "🇸🇦",
            "South Africa": "🇿🇦",
            "Indonesia": "🇮🇩",
            "Malaysia": "🇲🇾",
            "Thailand": "🇹🇭",
            "Philippines": "🇵🇭",
            "Vietnam": "🇻🇳",
            "Pakistan": "🇵🇰",
            "Bangladesh": "🇧🇩",
            "Turkey": "🇹🇷",
            "Egypt": "🇪🇬",
            "Nigeria": "🇳🇬",
            "Kenya": "🇰🇪",
            "Argentina": "🇦🇷",
            "Chile": "🇨🇱",
            "Colombia": "🇨🇴",
            "Peru": "🇵🇪",
            "Poland": "🇵🇱",
            "Sweden": "🇸🇪",
            "Norway": "🇳🇴",
            "Denmark": "🇩🇰",
            "Finland": "🇫🇮",
            "Belgium": "🇧🇪",
            "Switzerland": "🇨🇭",
            "Austria": "🇦🇹",
            "Portugal": "🇵🇹",
            "Greece": "🇬🇷",
            "Czech Republic": "🇨🇿",
            "Romania": "🇷🇴",
            "Hungary": "🇭🇺",
            "Ukraine": "🇺🇦",
            "Israel": "🇮🇱",
            "New Zealand": "🇳🇿",
            "Ireland": "🇮🇪",
            "Qatar": "🇶🇦",
            "Kuwait": "🇰🇼",
            "Oman": "🇴🇲",
            "Bahrain": "🇧🇭",
            "Local Network": "🏠",
            "Local": "🏠",
            "Unknown": "🌍",
        }
        return flags.get(country, "🌍")
    
    @staticmethod
    def get_device_icon(device_type: str) -> str:
        """Get icon for device type"""
        icons = {
            "Desktop": "💻",
            "Mobile": "📱",
            "Tablet": "📱",
            "Unknown": "🖥️"
        }
        return icons.get(device_type, "🖥️")
    
    @staticmethod
    def get_browser_icon(browser: str) -> str:
        """Get icon for browser"""
        icons = {
            "Google Chrome": "🌐",
            "Microsoft Edge": "🌐",
            "Mozilla Firefox": "🦊",
            "Safari": "🧭",
            "Opera": "🎭",
            "Streamlit App": "⚡",
            "Unknown": "🌐"
        }
        return icons.get(browser, "🌐")