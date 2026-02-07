"""
IP Address Utilities
Hashing and anonymization for privacy-compliant analytics
"""

import hashlib
import ipaddress
from typing import Optional


def hash_ip(ip_address: Optional[str], salt: Optional[str] = None) -> str:
    """
    Hash IP address for anonymization.
    Uses SHA-256 with optional salt for additional security.
    
    Args:
        ip_address: IP address string (IPv4 or IPv6)
        salt: Optional salt for additional security (default: "vadg_analytics")
        
    Returns:
        Hexadecimal hash string (64 characters)
    """
    if not ip_address:
        return ""
    
    # Default salt for consistent hashing
    if salt is None:
        salt = "vadg_analytics_salt_2024"
    
    # Normalize IP address
    try:
        # Validate and normalize IP
        ip_obj = ipaddress.ip_address(ip_address)
        normalized_ip = str(ip_obj)
    except ValueError:
        # Invalid IP, return empty hash
        return ""
    
    # Create hash
    hash_input = f"{normalized_ip}{salt}".encode('utf-8')
    hash_result = hashlib.sha256(hash_input).hexdigest()
    
    return hash_result


def anonymize_ip(ip_address: Optional[str]) -> str:
    """
    Anonymize IP address by zeroing out the last octet (IPv4) or last 64 bits (IPv6).
    This provides a balance between privacy and geolocation accuracy.
    
    Args:
        ip_address: IP address string
        
    Returns:
        Anonymized IP address string
    """
    if not ip_address:
        return ""
    
    try:
        ip_obj = ipaddress.ip_address(ip_address)
        
        if isinstance(ip_obj, ipaddress.IPv4Address):
            # Zero out last octet for IPv4
            ip_int = int(ip_obj)
            anonymized_int = (ip_int >> 8) << 8  # Clear last 8 bits
            return str(ipaddress.IPv4Address(anonymized_int))
        elif isinstance(ip_obj, ipaddress.IPv6Address):
            # Zero out last 64 bits for IPv6
            ip_int = int(ip_obj)
            anonymized_int = (ip_int >> 64) << 64  # Clear last 64 bits
            return str(ipaddress.IPv6Address(anonymized_int))
    except ValueError:
        pass
    
    return ""


def get_client_ip(request) -> Optional[str]:
    """
    Extract client IP address from FastAPI request.
    Handles proxy headers (X-Forwarded-For, X-Real-IP).
    
    Args:
        request: FastAPI Request object
        
    Returns:
        Client IP address string or None
    """
    if not request:
        return None
    
    # Check X-Forwarded-For header (first IP is the original client)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # X-Forwarded-For can contain multiple IPs, take the first one
        ip = forwarded_for.split(",")[0].strip()
        if ip:
            return ip
    
    # Check X-Real-IP header
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    
    # Fall back to direct client IP
    if request.client:
        return request.client.host
    
    return None

