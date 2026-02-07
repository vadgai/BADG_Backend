"""
Bot Detection and Filtering
Identifies and filters bot traffic from analytics
"""

import re
from typing import List, Set


# Common bot user agent patterns
BOT_PATTERNS: List[str] = [
    # Search engine bots
    r'googlebot',
    r'bingbot',
    r'slurp',  # Yahoo
    r'duckduckbot',
    r'baiduspider',
    r'yandexbot',
    r'sogou',
    r'exabot',
    r'facebot',
    r'ia_archiver',  # Internet Archive
    
    # Social media bots
    r'facebookexternalhit',
    r'twitterbot',
    r'linkedinbot',
    r'whatsapp',
    r'telegrambot',
    r'skypeuripreview',
    
    # Monitoring and scraping bots
    r'uptimerobot',
    r'pingdom',
    r'newrelic',
    r'statuspage',
    r'crawler',
    r'spider',
    r'scraper',
    r'bot',
    r'crawling',
    
    # Headless browsers (often used for scraping)
    r'headless',
    r'phantomjs',
    r'selenium',
    r'webdriver',
    r'puppeteer',
    r'playwright',
    r'chromium',
    
    # Other common bots
    r'curl',
    r'wget',
    r'python-requests',
    r'go-http-client',
    r'java/',
    r'okhttp',
    r'apache-httpclient',
    r'postman',
    r'insomnia',
    r'httpie',
    
    # Analytics and monitoring
    r'analytics',
    r'monitor',
    r'uptime',
    r'ping',
    r'health',
    r'check',
    
    # Feed readers
    r'feed',
    r'rss',
    r'atom',
    r'syndication',
    
    # Link checkers
    r'linkcheck',
    r'validator',
    r'w3c',
]


# Known good bots (don't filter these, but mark them)
GOOD_BOT_PATTERNS: List[str] = [
    r'googlebot',
    r'bingbot',
    r'slurp',
    r'duckduckbot',
]


def is_bot(user_agent: str, check_good_bots: bool = True) -> bool:
    """
    Check if user agent string indicates a bot.
    
    Args:
        user_agent: User agent string
        check_good_bots: If True, good bots (like Googlebot) are still considered bots
        
    Returns:
        True if bot detected, False otherwise
    """
    if not user_agent:
        return False
    
    user_agent_lower = user_agent.lower()
    
    # Check against bot patterns
    for pattern in BOT_PATTERNS:
        if re.search(pattern, user_agent_lower, re.IGNORECASE):
            # If checking good bots, return True for all bots
            if check_good_bots:
                return True
            
            # Otherwise, only return True if it's not a good bot
            is_good_bot = any(
                re.search(good_pattern, user_agent_lower, re.IGNORECASE)
                for good_pattern in GOOD_BOT_PATTERNS
            )
            if not is_good_bot:
                return True
    
    return False


def is_crawler(user_agent: str) -> bool:
    """
    Check if user agent is a search engine crawler.
    
    Args:
        user_agent: User agent string
        
    Returns:
        True if search engine crawler, False otherwise
    """
    if not user_agent:
        return False
    
    user_agent_lower = user_agent.lower()
    
    crawler_patterns = [
        r'googlebot',
        r'bingbot',
        r'slurp',
        r'duckduckbot',
        r'baiduspider',
        r'yandexbot',
        r'sogou',
    ]
    
    return any(
        re.search(pattern, user_agent_lower, re.IGNORECASE)
        for pattern in crawler_patterns
    )


def filter_bot_ips() -> Set[str]:
    """
    Get set of known bot IP addresses.
    This can be extended with IP ranges from known bot providers.
    
    Returns:
        Set of IP addresses/ranges to filter
    """
    # Googlebot IP ranges (example - should be updated with actual ranges)
    # In production, you might want to verify Googlebot IPs via reverse DNS
    return set()


def should_filter_request(user_agent: str, ip_address: str = None) -> bool:
    """
    Determine if a request should be filtered from analytics.
    
    Args:
        user_agent: User agent string
        ip_address: Optional IP address for additional filtering
        
    Returns:
        True if request should be filtered, False otherwise
    """
    # Filter by user agent
    if is_bot(user_agent, check_good_bots=True):
        return True
    
    # Filter by IP if provided
    if ip_address:
        bot_ips = filter_bot_ips()
        if ip_address in bot_ips:
            return True
    
    return False

