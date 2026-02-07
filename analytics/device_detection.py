"""
Device, Browser, and OS Detection Utility
Parses user-agent strings to extract device information
"""

import re
from typing import Optional, Dict, Tuple
from .models import DeviceType


def detect_device_type(user_agent: str) -> DeviceType:
    """
    Detect device type from user agent string.
    
    Args:
        user_agent: User agent string
        
    Returns:
        DeviceType enum value
    """
    if not user_agent:
        return DeviceType.UNKNOWN
    
    user_agent_lower = user_agent.lower()
    
    # Mobile detection
    mobile_patterns = [
        r'mobile', r'android', r'iphone', r'ipod', r'blackberry',
        r'windows phone', r'opera mini', r'palm', r'pocket'
    ]
    if any(re.search(pattern, user_agent_lower) for pattern in mobile_patterns):
        # Check if it's actually a tablet
        tablet_patterns = [
            r'ipad', r'android(?!.*mobile)', r'tablet', r'playbook', r'kindle'
        ]
        if any(re.search(pattern, user_agent_lower) for pattern in tablet_patterns):
            return DeviceType.TABLET
        return DeviceType.MOBILE
    
    # Tablet detection
    tablet_patterns = [
        r'ipad', r'android(?!.*mobile)', r'tablet', r'playbook', r'kindle',
        r'silk', r'gt-p', r'gt-n', r'sm-t'
    ]
    if any(re.search(pattern, user_agent_lower) for pattern in tablet_patterns):
        return DeviceType.TABLET
    
    return DeviceType.DESKTOP


def detect_browser(user_agent: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Detect browser name and version from user agent.
    
    Args:
        user_agent: User agent string
        
    Returns:
        Tuple of (browser_name, browser_version)
    """
    if not user_agent:
        return None, None
    
    user_agent_lower = user_agent.lower()
    
    # Chrome (including Edge Chromium)
    if 'edg/' in user_agent_lower or 'edgios/' in user_agent_lower:
        version_match = re.search(r'edg[\/]?([\d.]+)', user_agent_lower)
        version = version_match.group(1) if version_match else None
        return 'Edge', version
    
    if 'chrome' in user_agent_lower and 'chromium' not in user_agent_lower:
        version_match = re.search(r'chrome[\/]([\d.]+)', user_agent_lower)
        version = version_match.group(1) if version_match else None
        return 'Chrome', version
    
    # Firefox
    if 'firefox' in user_agent_lower:
        version_match = re.search(r'firefox[\/]([\d.]+)', user_agent_lower)
        version = version_match.group(1) if version_match else None
        return 'Firefox', version
    
    # Safari (but not Chrome)
    if 'safari' in user_agent_lower and 'chrome' not in user_agent_lower:
        version_match = re.search(r'version[\/]([\d.]+)', user_agent_lower)
        version = version_match.group(1) if version_match else None
        return 'Safari', version
    
    # Opera
    if 'opera' in user_agent_lower or 'opr/' in user_agent_lower:
        version_match = re.search(r'(?:opera|opr)[\/]([\d.]+)', user_agent_lower)
        version = version_match.group(1) if version_match else None
        return 'Opera', version
    
    # Internet Explorer
    if 'msie' in user_agent_lower or 'trident' in user_agent_lower:
        version_match = re.search(r'(?:msie |rv:)([\d.]+)', user_agent_lower)
        version = version_match.group(1) if version_match else None
        return 'Internet Explorer', version
    
    # Samsung Internet
    if 'samsungbrowser' in user_agent_lower:
        version_match = re.search(r'samsungbrowser[\/]([\d.]+)', user_agent_lower)
        version = version_match.group(1) if version_match else None
        return 'Samsung Internet', version
    
    return None, None


def detect_os(user_agent: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Detect operating system and version from user agent.
    
    Args:
        user_agent: User agent string
        
    Returns:
        Tuple of (os_name, os_version)
    """
    if not user_agent:
        return None, None
    
    user_agent_lower = user_agent.lower()
    
    # Windows
    if 'windows' in user_agent_lower:
        if 'windows nt 10.0' in user_agent_lower or 'windows 10' in user_agent_lower:
            return 'Windows', '10'
        elif 'windows nt 6.3' in user_agent_lower:
            return 'Windows', '8.1'
        elif 'windows nt 6.2' in user_agent_lower:
            return 'Windows', '8'
        elif 'windows nt 6.1' in user_agent_lower:
            return 'Windows', '7'
        elif 'windows nt 6.0' in user_agent_lower:
            return 'Windows', 'Vista'
        elif 'windows nt 5.1' in user_agent_lower:
            return 'Windows', 'XP'
        else:
            version_match = re.search(r'windows nt ([\d.]+)', user_agent_lower)
            version = version_match.group(1) if version_match else 'Unknown'
            return 'Windows', version
    
    # macOS
    if 'mac os x' in user_agent_lower or 'macintosh' in user_agent_lower:
        version_match = re.search(r'mac os x ([\d_]+)', user_agent_lower)
        if version_match:
            version = version_match.group(1).replace('_', '.')
            return 'macOS', version
        return 'macOS', None
    
    # iOS
    if 'iphone os' in user_agent_lower or 'ipad' in user_agent_lower:
        version_match = re.search(r'os ([\d_]+)', user_agent_lower)
        if version_match:
            version = version_match.group(1).replace('_', '.')
            return 'iOS', version
        return 'iOS', None
    
    # Android
    if 'android' in user_agent_lower:
        version_match = re.search(r'android ([\d.]+)', user_agent_lower)
        version = version_match.group(1) if version_match else None
        return 'Android', version
    
    # Linux
    if 'linux' in user_agent_lower:
        # Try to detect specific Linux distributions
        if 'ubuntu' in user_agent_lower:
            return 'Ubuntu', None
        elif 'fedora' in user_agent_lower:
            return 'Fedora', None
        elif 'debian' in user_agent_lower:
            return 'Debian', None
        return 'Linux', None
    
    # Chrome OS
    if 'cros' in user_agent_lower:
        return 'Chrome OS', None
    
    return None, None


def parse_user_agent(user_agent: str) -> Dict[str, any]:
    """
    Parse user agent string and return all detected information.
    
    Args:
        user_agent: User agent string
        
    Returns:
        Dictionary with device_type, browser, browser_version, os, os_version
    """
    device_type = detect_device_type(user_agent)
    browser, browser_version = detect_browser(user_agent)
    os, os_version = detect_os(user_agent)
    
    return {
        'device_type': device_type,
        'browser': browser,
        'browser_version': browser_version,
        'os': os,
        'os_version': os_version
    }

