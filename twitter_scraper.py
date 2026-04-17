"""
twitter_scraper.py
──────────────────
Riset akun Twitter/X project tanpa API berbayar.
Strategi berlapis:
  1. Nitter publik instances (mirror Twitter tanpa rate limit)
  2. Scrape langsung x.com / twitter.com (guest session)
  3. SocialBlade & Twitterscore untuk metrics tambahan
"""

import re
import asyncio
import logging
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urlparse, quote
from typing import Optional

logger = logging.getLogger(__name__)

# ── Nitter instances publik (fallback satu per satu) ──────────────
NITTER_INSTANCES = [
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.1d4.us",
    "https://nitter.kavin.rocks",
    "https://nitter.unixfox.eu",
    "https://nitter.moomoo.me",
    "https://nitter.it",
    "https://nitter.nl",
]

HEADERS_BROWSER = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class TwitterScraper:
    """Scraper akun Twitter/X project tanpa API key"""

    def __init__(self):
        self.timeout = aiohttp.ClientTimeout(total=15)

    # ────────────────────────────────────────────────────────────────
    # PUBLIC ENTRY POINT
    # ────────────────────────────────────────────────────────────────
    async def research_account(self, twitter_handle: str) -> dict:
        """
        Riset lengkap satu akun Twitter project.
        Return dict dengan profile + tweets + topics.
        """
        handle = self._clean_handle(twitter_handle)
        logger.info(f"Researching Twitter: @{handle}")

        result = {
            "handle": handle,
            "profile": {},
            "pinned_tweet": "",
            "recent_tweets": [],
            "key_topics": [],
            "announcements": [],
            "tone_sample": [],
            "success": False,
            "source": "",
        }

        # Coba Nitter dulu (paling reliable & bebas bot-check)
        nitter_data = await self._scrape_nitter(handle)
        if nitter_data and nitter_data.get("tweets"):
            result.update(nitter_data)
            result["success"] = True
            result["source"] = "nitter"
            logger.info(f"Nitter OK: {len(result['recent_tweets'])} tweets")
            return result

        # Fallback: scrape x.com langsung
        logger.info("Nitter failed, trying x.com direct...")
        xcom_data = await self._scrape_xcom(handle)
        if xcom_data and xcom_data.get("tweets"):
            result.update(xcom_data)
            result["success"] = True
            result["source"] = "xcom"
            logger.info(f"x.com OK: {len(result['recent_tweets'])} tweets")
            return result

        # Fallback: scrape search hasil Google tentang akun ini
        logger.info("Direct scrape failed, trying web search approach...")
        search_data = await self._scrape_via_search(handle)
        if search_data:
            result.update(search_data)
            result["success"] = True
            result["source"] = "websearch"

        return result

    # ────────────────────────────────────────────────────────────────
    # NITTER SCRAPER
    # ────────────────────────────────────────────────────────────────
    async def _scrape_nitter(self, handle: str) -> Optional[dict]:
        async with aiohttp.ClientSession(headers=HEADERS_BROWSER) as session:
            for instance in NITTER_INSTANCES:
                try:
                    url = f"{instance}/{handle}"
                    async with session.get(
                        url, timeout=self.timeout, ssl=False, allow_redirects=True
                    ) as resp:
                        if resp.status != 200:
                            continue
                        html = await resp.text(errors="ignore")
                        parsed = self._parse_nitter_html(html, handle)
                        if parsed and parsed.get("tweets"):
                            parsed["nitter_instance"] = instance
                            return parsed
                except Exception as e:
                    logger.debug(f"Nitter {instance} failed: {e}")
                    continue
                await asyncio.sleep(0.3)
        return None

    def _parse_nitter_html(self, html: str, handle: str) -> Optional[dict]:
        soup = BeautifulSoup(html, "html.parser")

        # Detect error pages
        if soup.find(class_="error-panel") or "Instance is down" in html:
            return None

        data = {"handle": handle, "profile": {}, "recent_tweets": [],
                 "pinned_tweet": "", "announcements": [], "tone_sample": []}

        # ── Profile ──────────────────────────────────────────────────
        profile = {}

        name_el = soup.find(class_="profile-card-fullname")
        if name_el:
            profile["name"] = name_el.get_text(strip=True)

        bio_el = soup.find(class_="profile-bio")
        if bio_el:
            profile["bio"] = bio_el.get_text(strip=True)

        # Stats: followers, following, tweets count
        for stat in soup.find_all(class_="profile-stat"):
            label_el = stat.find(class_="profile-stat-header")
            value_el = stat.find(class_="profile-stat-num")
            if label_el and value_el:
                label = label_el.get_text(strip=True).lower()
                value = value_el.get_text(strip=True)
                profile[label] = value

        # Website link
        website_el = soup.find(class_="profile-website")
        if website_el:
            a = website_el.find("a")
            if a:
                profile["website"] = a.get("href", "")

        # Joined / location
        for el in soup.find_all(class_="profile-joindate"):
            profile["joined"] = el.get_text(strip=True)

        data["profile"] = profile

        # ── Tweets ───────────────────────────────────────────────────
        tweet_items = soup.find_all(class_="timeline-item")
        tweets_text = []

        for item in tweet_items[:25]:
            # Skip retweets
            if item.find(class_="retweet-header"):
                continue

            content_el = item.find(class_="tweet-content")
            if not content_el:
                continue

            text = content_el.get_text(separator=" ", strip=True)
            if len(text) < 15:
                continue

            # Stats tweet
            tweet_stats = {}
            for stat_el in item.find_all(class_="tweet-stat"):
                icon_el = stat_el.find("span", class_=re.compile(r"icon-"))
                val_el = stat_el.find(class_="tweet-stat")
                full_text = stat_el.get_text(strip=True)
                if "comment" in stat_el.get("class", []) or "reply" in str(stat_el):
                    tweet_stats["replies"] = full_text
                nums = re.findall(r"[\d,]+", full_text)
                if nums:
                    tweet_stats["engagement"] = nums[0]

            # Pinned?
            is_pinned = bool(item.find(class_="pinned"))

            tweet_obj = {
                "text": text[:500],
                "pinned": is_pinned,
                "stats": tweet_stats,
            }

            if is_pinned:
                data["pinned_tweet"] = text[:500]

            # Classify
            lower = text.lower()
            if any(kw in lower for kw in ["launch", "announce", "introducing",
                                           "excited", "thrilled", "partnership",
                                           "listing", "mainnet", "testnet", "live"]):
                data["announcements"].append(text[:400])

            tweets_text.append(tweet_obj)

        data["tweets"] = tweets_text
        data["recent_tweets"] = [t["text"] for t in tweets_text[:20]]

        # ── Extract topics & tone ────────────────────────────────────
        data["key_topics"] = self._extract_topics(data["recent_tweets"])
        data["tone_sample"] = data["recent_tweets"][:5]

        return data if tweets_text else None

    # ────────────────────────────────────────────────────────────────
    # X.COM DIRECT SCRAPER (guest mode)
    # ────────────────────────────────────────────────────────────────
    async def _scrape_xcom(self, handle: str) -> Optional[dict]:
        """
        Coba akses x.com/handle langsung.
        Kadang berhasil untuk akun publik.
        """
        urls_to_try = [
            f"https://x.com/{handle}",
            f"https://twitter.com/{handle}",
        ]
        async with aiohttp.ClientSession(headers=HEADERS_BROWSER) as session:
            for url in urls_to_try:
                try:
                    async with session.get(
                        url, timeout=self.timeout, ssl=False, allow_redirects=True
                    ) as resp:
                        if resp.status != 200:
                            continue
                        html = await resp.text(errors="ignore")
                        parsed = self._parse_xcom_html(html, handle)
                        if parsed:
                            return parsed
                except Exception as e:
                    logger.debug(f"x.com direct failed: {e}")
        return None

    def _parse_xcom_html(self, html: str, handle: str) -> Optional[dict]:
        """
        Parse x.com HTML — konten sering ada di meta tags & JSON-LD
        meski JS belum render.
        """
        soup = BeautifulSoup(html, "html.parser")
        data = {"handle": handle, "profile": {}, "recent_tweets": [],
                 "pinned_tweet": "", "announcements": [], "tone_sample": []}

        tweets_found = []

        # Meta OG/twitter tags — sering ada bio & nama
        for og in [("og:description", "description"), ("og:title", "name")]:
            m = soup.find("meta", property=og[0]) or soup.find("meta", attrs={"name": og[0]})
            if m and m.get("content"):
                data["profile"][og[1]] = m["content"]

        # JSON-LD embedded data
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                import json
                ld = json.loads(script.string or "{}")
                if isinstance(ld, dict):
                    if ld.get("@type") == "Person":
                        data["profile"]["name"] = ld.get("name", "")
                        data["profile"]["description"] = ld.get("description", "")
                    # Extract any text content
                    for k, v in ld.items():
                        if isinstance(v, str) and len(v) > 30:
                            tweets_found.append(v[:400])
            except Exception:
                pass

        # Cari tweet text di meta description (x.com sering embed ini)
        desc = data["profile"].get("description", "")
        if desc and len(desc) > 30:
            tweets_found.append(desc)

        # Cari konten yang tersembunyi di noscript atau data attrs
        for el in soup.find_all(attrs={"data-testid": True}):
            text = el.get_text(strip=True)
            if 20 < len(text) < 600:
                tweets_found.append(text[:400])

        data["recent_tweets"] = list(dict.fromkeys(tweets_found))[:15]
        data["key_topics"] = self._extract_topics(data["recent_tweets"])
        data["tone_sample"] = data["recent_tweets"][:5]
        data["tweets"] = [{"text": t} for t in data["recent_tweets"]]

        return data if data["recent_tweets"] else None

    # ────────────────────────────────────────────────────────────────
    # WEB SEARCH FALLBACK — cari tweet via Google/DuckDuckGo
    # ────────────────────────────────────────────────────────────────
    async def _scrape_via_search(self, handle: str) -> Optional[dict]:
        """
        Last resort: cari tweet & info project via DuckDuckGo HTML search.
        """
        data = {"handle": handle, "profile": {}, "recent_tweets": [],
                 "pinned_tweet": "", "announcements": [], "tone_sample": []}

        queries = [
            f"site:twitter.com OR site:x.com @{handle}",
            f"{handle} crypto project twitter announcement",
            f"@{handle} twitter thread tokenomics",
        ]

        found_texts = []
        async with aiohttp.ClientSession(headers=HEADERS_BROWSER) as session:
            for q in queries[:2]:
                try:
                    ddg_url = f"https://html.duckduckgo.com/html/?q={quote(q)}"
                    async with session.get(ddg_url, timeout=self.timeout, ssl=False) as resp:
                        if resp.status != 200:
                            continue
                        html = await resp.text(errors="ignore")
                        soup = BeautifulSoup(html, "html.parser")
                        for result in soup.find_all(class_="result__snippet"):
                            text = result.get_text(strip=True)
                            if len(text) > 40:
                                found_texts.append(text[:400])
                        # Also grab result titles
                        for title in soup.find_all(class_="result__title"):
                            text = title.get_text(strip=True)
                            if len(text) > 20:
                                data["profile"]["name"] = text
                                break
                except Exception as e:
                    logger.debug(f"DDG search failed: {e}")
                await asyncio.sleep(0.5)

        data["recent_tweets"] = found_texts[:15]
        data["key_topics"] = self._extract_topics(found_texts)
        data["tone_sample"] = found_texts[:5]
        data["tweets"] = [{"text": t} for t in found_texts]

        return data if found_texts else None

    # ────────────────────────────────────────────────────────────────
    # HELPERS
    # ────────────────────────────────────────────────────────────────
    def _clean_handle(self, raw: str) -> str:
        """Bersihkan handle: '@Uniswap' atau 'x.com/Uniswap' → 'Uniswap'"""
        raw = raw.strip()
        # Dari URL
        for pattern in [r"(?:twitter\.com|x\.com)/([A-Za-z0-9_]+)",
                         r"@([A-Za-z0-9_]+)"]:
            m = re.search(pattern, raw)
            if m:
                return m.group(1)
        # Hapus @ jika ada
        return raw.lstrip("@")

    def _extract_topics(self, tweets: list[str]) -> list[str]:
        """Ekstrak topik utama dari kumpulan tweets"""
        keyword_freq: dict[str, int] = {}
        stop = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                "being", "have", "has", "had", "do", "does", "did", "will",
                "would", "could", "should", "may", "might", "must", "shall",
                "to", "of", "in", "for", "on", "with", "at", "by", "from",
                "it", "its", "this", "that", "these", "those", "we", "our",
                "you", "your", "they", "their", "and", "or", "but", "not",
                "so", "if", "as", "up", "out", "about", "into", "than",
                "more", "just", "can", "get", "all", "new", "what", "how"}

        for tweet in tweets:
            words = re.findall(r"\b[A-Za-z][A-Za-z0-9]{2,}\b", tweet)
            for word in words:
                w = word.lower()
                if w not in stop and len(w) > 3:
                    keyword_freq[w] = keyword_freq.get(w, 0) + 1

        # Ambil top 12 keyword
        sorted_kw = sorted(keyword_freq.items(), key=lambda x: x[1], reverse=True)
        return [kw for kw, _ in sorted_kw[:12]]

    def format_for_research(self, data: dict) -> str:
        """Format data Twitter menjadi teks riset untuk prompt AI"""
        if not data.get("success"):
            return f"[Twitter @{data.get('handle','?')}: Data tidak tersedia]"

        lines = []
        handle = data["handle"]
        lines.append(f"\n{'='*55}")
        lines.append(f"TWITTER/X ACCOUNT: @{handle}")
        lines.append(f"Source: {data.get('source', 'unknown')}")
        lines.append(f"{'='*55}")

        # Profile
        profile = data.get("profile", {})
        if profile.get("name"):
            lines.append(f"Display Name: {profile['name']}")
        if profile.get("bio") or profile.get("description"):
            bio = profile.get("bio") or profile.get("description", "")
            lines.append(f"Bio: {bio[:300]}")
        if profile.get("followers"):
            lines.append(f"Followers: {profile['followers']}")
        if profile.get("tweets"):
            lines.append(f"Total Tweets: {profile.get('tweets','?')}")
        if profile.get("joined"):
            lines.append(f"Joined: {profile['joined']}")
        if profile.get("website"):
            lines.append(f"Website (from profile): {profile['website']}")

        # Pinned tweet
        if data.get("pinned_tweet"):
            lines.append(f"\nPINNED TWEET:")
            lines.append(f'  "{data["pinned_tweet"][:400]}"')

        # Announcements / major tweets
        if data.get("announcements"):
            lines.append(f"\nKEY ANNOUNCEMENTS ({len(data['announcements'])}):")
            for ann in data["announcements"][:5]:
                lines.append(f'  → "{ann[:300]}"')

        # Recent tweets sample
        if data.get("recent_tweets"):
            lines.append(f"\nRECENT TWEETS SAMPLE ({len(data['recent_tweets'])} collected):")
            for tw in data["recent_tweets"][:15]:
                lines.append(f'  • "{tw[:300]}"')

        # Topics
        if data.get("key_topics"):
            lines.append(f"\nKEY TOPICS from Twitter: {', '.join(data['key_topics'])}")

        # Tone sample
        if data.get("tone_sample"):
            lines.append(f"\nTONE & VOICE EXAMPLES (untuk menangkap gaya komunikasi project):")
            for t in data["tone_sample"][:3]:
                lines.append(f'  "{t[:200]}"')

        return "\n".join(lines)
