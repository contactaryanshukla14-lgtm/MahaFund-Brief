import httpx
import random

def get_free_indian_proxy() -> str:
    """
    Fetches a random free Indian proxy from ProxyScrape.
    Returns in format: http://ip:port
    """
    try:
        url = "https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&proxy_format=protocolipport&format=text&country=in"
        res = httpx.get(url, timeout=10)
        res.raise_for_status()
        
        proxies = [p.strip() for p in res.text.split("\n") if p.strip()]
        if proxies:
            # Pick a random proxy to avoid hitting a dead one repeatedly
            proxy = random.choice(proxies)
            # Ensure it has http:// prefix if missing
            if not proxy.startswith("http"):
                proxy = "http://" + proxy
            print(f"Loaded dynamic proxy: {proxy}")
            return proxy
    except Exception as e:
        print(f"Failed to fetch dynamic proxy: {e}")
        
    return None
