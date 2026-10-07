import logging
import re
import time
import random
from typing import List, Optional, Dict
import httpx

# Setup logger for Flipkart keyword collector
logger = logging.getLogger("flipkart_keyword_collector")

FLIPKART_AUTOSUGGEST_ENDPOINTS = [
    "https://2.rome.api.flipkart.com/4/discover/autosuggest",
    "https://1.rome.api.flipkart.com/4/discover/autosuggest",
    "https://3.rome.api.flipkart.com/4/discover/autosuggest",
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]

# Global statistics tracking for batch execution monitoring
RETRIES_STATS: Dict[str, int] = {
    "403_responses": 0,
    "total_retries": 0
}


def get_flipkart_headers() -> Dict[str, str]:
    """Generate dynamic headers with randomized desktop User-Agent."""
    ua = random.choice(USER_AGENTS)
    return {
        "User-Agent": ua,
        "x-user-agent": f"{ua} FKUA/msite/0.0.4/msite/Mobile",
        "Content-Type": "application/json",
        "Referer": "https://www.flipkart.com/",
        "Origin": "https://www.flipkart.com"
    }


def fetch_flipkart_suggestions_api(
    query: str,
    timeout: float = 8.0,
    max_retries: int = 3,
    base_backoff_delay: float = 1.0
) -> List[str]:
    """
    Fetch search suggestions directly from Flipkart's autosuggest API endpoints.
    Includes HTTP 403 / 429 retry handling with exponential backoff.
    Returns clean, real search keywords from Flipkart safely.
    """
    if not query or not str(query).strip():
        return []

    clean_query = re.sub(r'\s+', ' ', str(query)).strip()
    payload = {
        "query": clean_query,
        "contextUri": "/",
        "marketPlaceId": "FLIPKART",
        "types": ["QUERY", "QUERY_STORE", "PRODUCT", "RICH", "PARTITION"],
        "rows": 10
    }

    keywords: List[str] = []
    seen_lower = set()

    for endpoint in FLIPKART_AUTOSUGGEST_ENDPOINTS:
        for attempt in range(1, max_retries + 1):
            try:
                headers = get_flipkart_headers()
                logger.info(f"Querying Flipkart autosuggest API ({endpoint}) for '{clean_query}' (Attempt {attempt}/{max_retries})")
                
                with httpx.Client(timeout=timeout) as client:
                    resp = client.post(endpoint, json=payload, headers=headers)
                    
                    if resp.status_code == 200:
                        try:
                            data = resp.json()
                            suggestions = data.get("RESPONSE", {}).get("suggestions", [])
                            
                            for item in suggestions:
                                item_data = item.get("data", {})
                                kw_candidates = []
                                
                                comp_val = item_data.get("component", {}).get("value", {})
                                if isinstance(comp_val, dict):
                                    t_val = comp_val.get("title", {})
                                    if isinstance(t_val, dict) and t_val.get("text"):
                                        kw_candidates.append(t_val.get("text"))
                                
                                action_params = item_data.get("component", {}).get("action", {}).get("params", {})
                                if action_params.get("query"):
                                    kw_candidates.append(action_params.get("query").replace("+", " "))
                                    
                                for f in ["value", "text", "title", "query"]:
                                    val = item_data.get(f)
                                    if val and isinstance(val, str):
                                        kw_candidates.append(val)
                                        
                                for cand in kw_candidates:
                                    cleaned_cand = re.sub(r'\s+', ' ', str(cand)).strip()
                                    if cleaned_cand:
                                        cand_lower = cleaned_cand.lower()
                                        if cand_lower not in seen_lower:
                                            seen_lower.add(cand_lower)
                                            keywords.append(cleaned_cand)
                                            break
                        except Exception as json_err:
                            logger.warning(f"Error parsing JSON from Flipkart API response for '{clean_query}': {json_err}")
                            
                        if keywords:
                            logger.info(f"Successfully collected {len(keywords)} keywords from Flipkart API.")
                            return keywords
                        else:
                            logger.warning(f"Flipkart API returned 200 OK but no valid suggestions for '{clean_query}'.")
                            break
                            
                    elif resp.status_code in (403, 429):
                        RETRIES_STATS["403_responses"] += 1
                        RETRIES_STATS["total_retries"] += 1
                        backoff = base_backoff_delay * (2 ** (attempt - 1)) + random.uniform(0.1, 0.4)
                        logger.warning(
                            f"Flipkart API blocked with HTTP {resp.status_code} at {endpoint}. "
                            f"Backoff retry in {backoff:.2f}s (Attempt {attempt}/{max_retries})..."
                        )
                        time.sleep(backoff)
                    else:
                        logger.warning(f"Flipkart API returned HTTP status {resp.status_code} at {endpoint}")
                        break

            except httpx.TimeoutException:
                RETRIES_STATS["total_retries"] += 1
                logger.error(f"Timeout of {timeout}s exceeded while querying Flipkart API at {endpoint} (Attempt {attempt}/{max_retries})")
                time.sleep(1.0)
            except Exception as e:
                logger.error(f"Exception encountered while querying Flipkart API at {endpoint}: {e}")
                break

    return keywords


def collect_flipkart_keywords(seed_keyword: str, browser=None) -> List[str]:
    """
    Collect Flipkart search suggestions for a seed keyword safely.
    
    Args:
        seed_keyword: Search phrase seed (e.g., "cricket bat").
        browser: Optional Playwright browser instance for fallback browser scraping.
        
    Returns:
        List[str]: Cleaned, non-empty, deduplicated list of real keywords from Flipkart.
    """
    if not seed_keyword or not str(seed_keyword).strip():
        logger.warning("Empty seed keyword provided to collect_flipkart_keywords.")
        return []

    clean_seed = re.sub(r'\s+', ' ', str(seed_keyword)).strip()
    logger.info(f"Starting Flipkart keyword collection for seed: '{clean_seed}'")

    # 1. Try fast, direct API collection with retry and exponential backoff
    api_keywords = fetch_flipkart_suggestions_api(clean_seed)
    if api_keywords:
        return api_keywords

    # 2. Browser fallback if browser instance is provided
    if browser:
        logger.info(f"Attempting Playwright browser fallback collection for seed: '{clean_seed}'")
        try:
            headers = get_flipkart_headers()
            context = browser.new_context(
                user_agent=headers["User-Agent"],
                viewport={"width": 1366, "height": 900}
            )
            context.set_default_timeout(15000)
            page = context.new_page()

            captured_keywords = []

            def handle_response(response):
                if "autosuggest" in response.url.lower() and response.status == 200:
                    try:
                        data = response.json()
                        suggestions = data.get("RESPONSE", {}).get("suggestions", [])
                        for item in suggestions:
                            comp_val = item.get("data", {}).get("component", {}).get("value", {})
                            if isinstance(comp_val, dict):
                                t_val = comp_val.get("title", {})
                                if isinstance(t_val, dict) and t_val.get("text"):
                                    kw = re.sub(r'\s+', ' ', t_val.get("text")).strip()
                                    if kw and kw.lower() not in [k.lower() for k in captured_keywords]:
                                        captured_keywords.append(kw)
                    except Exception:
                        pass

            page.on("response", handle_response)
            page.goto("https://www.flipkart.com/", wait_until="domcontentloaded", timeout=20000)

            search_box = page.locator("input[title*='Search'], input[placeholder*='Search'], input[name='q']")
            if search_box.count() > 0:
                search_box.first.click()
                search_box.first.press_sequentially(clean_seed, delay=50)
                page.wait_for_timeout(3000)

            context.close()

            if captured_keywords:
                logger.info(f"Successfully collected {len(captured_keywords)} keywords via Playwright browser fallback.")
                return captured_keywords

        except Exception as e:
            logger.error(f"Playwright browser fallback failed for Flipkart seed '{clean_seed}': {e}")

    logger.warning(f"No keywords collected for Flipkart seed '{clean_seed}'.")
    return []
