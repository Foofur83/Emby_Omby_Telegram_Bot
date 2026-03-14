# Author: Foofur83
import asyncio
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from urllib.parse import quote as urlquote

import aiohttp
import yaml
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, CallbackQueryHandler, filters
import re

DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "requests.json")
USERS_FILE = os.path.join(os.path.dirname(__file__), "data", "users.json")
EPISODE_NOTIFICATIONS_FILE = os.path.join(os.path.dirname(__file__), "data", "episode_notifications.json")
MESSAGES_FILE = os.path.join(os.path.dirname(__file__), "data", "pending_messages.json")
BOT_LOG_FILE = os.path.join(os.path.dirname(__file__), "data", "bot_messages.json")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def ensure_data_dir():
    d = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(d, exist_ok=True)
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)
    if not os.path.exists(EPISODE_NOTIFICATIONS_FILE):
        with open(EPISODE_NOTIFICATIONS_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)
    if not os.path.exists(MESSAGES_FILE):
        with open(MESSAGES_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)
    if not os.path.exists(BOT_LOG_FILE):
        with open(BOT_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)


def load_requests():
    ensure_data_dir()
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_requests(data):
    ensure_data_dir()
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_users():
    ensure_data_dir()
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Safety check: users should be a list, not a dict
            if isinstance(data, dict):
                logger.warning("users.json was corrupted (dict instead of list), resetting...")
                return []
            return data
    except:
        return []


def save_users(data):
    ensure_data_dir()
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_episode_notifications():
    """Load episode notification tracking (which episodes have been notified)"""
    ensure_data_dir()
    try:
        with open(EPISODE_NOTIFICATIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def save_episode_notifications(data):
    """Save episode notification tracking"""
    ensure_data_dir()
    with open(EPISODE_NOTIFICATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_pending_messages():
    """Load pending messages from web interface"""
    ensure_data_dir()
    try:
        with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []


def save_pending_messages(data):
    """Save pending messages"""
    ensure_data_dir()
    with open(MESSAGES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def log_bot_message(message_type: str, user_id: int, username: str, message: str, direction: str = "sent"):
    """
    Log bot messages for web interface display
    message_type: 'text', 'notification', 'manual', 'command'
    direction: 'sent' or 'received'
    """
    ensure_data_dir()
    try:
        with open(BOT_LOG_FILE, "r", encoding="utf-8") as f:
            logs = json.load(f)
    except:
        logs = []
    
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": message_type,
        "user_id": user_id,
        "username": username,
        "message": message[:500],  # Limit message length
        "direction": direction
    }
    
    logs.append(log_entry)
    
    # Keep only last 200 messages
    if len(logs) > 200:
        logs = logs[-200:]
    
    with open(BOT_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)


async def reply_and_log(message, text, user, **kwargs):
    """Helper: Send reply_text and automatically log it"""
    await message.reply_text(text, **kwargs)
    username = user.username or user.first_name
    # Strip markdown for logging
    clean_text = text.replace("**", "").replace("__", "").replace("*", "").replace("_", "")
    log_bot_message("text", user.id, username, clean_text[:500], "sent")


def get_user_by_telegram_id(telegram_id: int):
    """Haal gebruiker op via Telegram ID"""
    users = load_users()
    for user in users:
        # Safety check: skip if user is not a dict
        if not isinstance(user, dict):
            continue
        if user.get("telegram_user_id") == telegram_id:
            return user
    return None


def is_user_approved(telegram_id: int) -> bool:
    """Check of gebruiker goedgekeurd is"""
    user = get_user_by_telegram_id(telegram_id)
    return user and user.get("approved", False)


class OmbiEmbyBot:
    def __init__(self, config: dict):
        def _norm(u: str):
            if not u:
                return u
            u = u.strip()
            if not (u.startswith("http://") or u.startswith("https://")):
                u = "http://" + u
            return u.rstrip("/")

        self.config = config or {}
        # allow an explicit API base override if SPA is served at root
        self.ombi_api_url = _norm(self.config.get("ombi_api_url"))
        self.ombi_url = _norm(self.config.get("ombi_url"))
        self.ombi_key = self.config.get("ombi_api_key")
        self.ombi_key_header = self.config.get("ombi_api_key_header", "ApiKey")

        self.emby_url = _norm(self.config.get("emby_url"))
        self.emby_key = self.config.get("emby_api_key")

        self.poll_interval = int(self.config.get("poll_interval_seconds", 60))

        # aiohttp session created lazily inside running event loop
        self.session: aiohttp.ClientSession | None = None

    async def ensure_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()

    async def _request_json(self, method: str, url: str, **kwargs):
        """Perform a request and return (json_or_text, status). On connection error, retry with alternate scheme."""
        await self.ensure_session()
        try:
            async with self.session.request(method, url, **kwargs) as r:
                text = await r.text()
                if r.status >= 400:
                    logger.warning("Request to %s failed (%s): %s", url, r.status, text)
                    return None, r.status
                # try parse json
                try:
                    return await r.json(), r.status
                except Exception:
                    return text, r.status
        except (aiohttp.ClientConnectorError, aiohttp.ClientOSError) as e:
            # try alternate scheme
            if url.startswith("http://"):
                alt = "https://" + url[len("http://"):]
            elif url.startswith("https://"):
                alt = "http://" + url[len("https://"):]
            else:
                logger.warning("Connection error for %s: %s", url, e)
                return None, None
            logger.warning("Primary connection failed for %s: %s; retrying with %s", url, e, alt)
            try:
                async with self.session.request(method, alt, **kwargs) as r:
                    text = await r.text()
                    if r.status >= 400:
                        logger.warning("Request to %s failed (%s): %s", alt, r.status, text)
                        return None, r.status
                    try:
                        return await r.json(), r.status
                    except Exception:
                        return text, r.status
            except Exception as e2:
                logger.warning("Retry with alternate scheme failed for %s: %s", alt, e2)
                return None, None
        except asyncio.TimeoutError:
            logger.warning("Request timed out: %s", url)
            return None, None
        except Exception:
            logger.exception("Unexpected error during request to %s", url)
            return None, None

    async def close(self):
        if self.session:
            await self.session.close()

    # Ombi
    async def ombi_search(self, query: str):
        """Search for movies and TV shows using Ombi v1 endpoints"""
        if not self.ombi_url:
            return []
        await self.ensure_session()
        headers = {self.ombi_key_header: self.ombi_key} if self.ombi_key else {}
        
        results = []
        
        # Search movies (v1)
        url = f"{self.ombi_url}/api/v1/Search/movie/{urlquote(query)}"
        logger.info(f"Searching Ombi movies: {url}")
        data, status = await self._request_json("GET", url, headers=headers, timeout=10)
        if data and isinstance(data, list):
            logger.info("Ombi movie search found %d results", len(data))
            # Tag elk resultaat als movie
            for item in data:
                item["mediaType"] = "movie"
            results.extend(data)
        else:
            logger.warning(f"Ombi movie search returned: {data}")
        
        # Search TV shows (v1)
        url = f"{self.ombi_url}/api/v1/Search/tv/{urlquote(query)}"
        logger.info(f"Searching Ombi TV: {url}")
        data, status = await self._request_json("GET", url, headers=headers, timeout=10)
        if data and isinstance(data, list):
            logger.info("Ombi TV search found %d results", len(data))
            # Tag elk resultaat als tv en log de velden
            for item in data:
                item["mediaType"] = "tv"
                # Debug: log beschikbare velden voor eerste resultaat
                if data.index(item) == 0:
                    logger.info(f"TV result fields: {list(item.keys())}")
                    logger.info(f"Poster-related fields: posterPath={item.get('posterPath')}, banner={item.get('banner')}, poster={item.get('poster')}")
            results.extend(data)
        else:
            logger.warning(f"Ombi TV search returned: {data}")
        
        if not results:
            logger.error("Ombi search returned no results. Check ombi_url, ombi_api_key, and ombi_api_key_header in config.yaml")
        
        return results

    async def ombi_request(self, item: dict | None, media_type: str = "movie", requested_seasons: list = None):
        """Request a movie or TV show in Ombi using the correct API endpoints"""
        if not self.ombi_url or not item:
            return None
        await self.ensure_session()
        headers = {self.ombi_key_header: self.ombi_key, "Content-Type": "application/json"} if self.ombi_key else {"Content-Type": "application/json"}
        
        # Use correct endpoint based on media type (from Swagger docs)
        if media_type.lower() in ("tv", "series"):
            # Probeer eerst v1 API (oudere maar stabielere versie)
            url = f"{self.ombi_url}/api/v1/Request/tv"
            
            # TV request payload voor v1 API - eenvoudigere structuur
            # Try to get the correct TV DB ID
            tv_db_id = item.get("tvDbId") or item.get("theTvDbId") or item.get("id")
            
            if requested_seasons is None:
                # Request alle seizoenen
                payload = {
                    "tvDbId": tv_db_id,
                    "requestAll": True
                }
            else:
                # Request specifieke seizoenen
                payload = {
                    "tvDbId": tv_db_id,
                    "seasons": [{"seasonNumber": s, "episodes": []} for s in requested_seasons]
                }
            
            logger.info(f"Ombi TV request payload (v1): {payload}")
        else:
            url = f"{self.ombi_url}/api/v1/Request/movie"
            # Movie request payload
            payload = {
                "theMovieDbId": item.get("theMovieDbId") or item.get("id")
            }
        
        data, status = await self._request_json("POST", url, headers=headers, json=payload, timeout=10)
        if data and not (isinstance(data, str) and "<" in data):
            logger.info("Ombi %s request succeeded", media_type)
            # Log response structure voor debugging
            if isinstance(data, dict):
                logger.debug(f"Ombi response keys: {list(data.keys())}")
            return data
        logger.error("Ombi %s request failed. Check configuration.", media_type)
        return None

    async def ombi_get_all_requests(self):
        """Get all movie and TV requests from Ombi with current status"""
        if not self.ombi_url:
            return []
        await self.ensure_session()
        headers = {self.ombi_key_header: self.ombi_key} if self.ombi_key else {}
        
        all_requests = []
        
        # Get all movie requests
        url = f"{self.ombi_url}/api/v1/Request/movie"
        logger.debug(f"Fetching all Ombi movie requests: {url}")
        data, status = await self._request_json("GET", url, headers=headers, timeout=10)
        if data and isinstance(data, list):
            for item in data:
                item["mediaType"] = "movie"
            all_requests.extend(data)
            logger.info(f"Fetched {len(data)} movie requests from Ombi")
        
        # Get all TV requests
        url = f"{self.ombi_url}/api/v1/Request/tv"
        logger.debug(f"Fetching all Ombi TV requests: {url}")
        data, status = await self._request_json("GET", url, headers=headers, timeout=10)
        if data and isinstance(data, list):
            for item in data:
                item["mediaType"] = "tv"
            all_requests.extend(data)
            logger.info(f"Fetched {len(data)} TV requests from Ombi")
        
        return all_requests

    async def ombi_get_request_by_id(self, request_id: int, media_type: str = "movie"):
        """Get request details from Ombi by request ID (via fetching all requests)"""
        if not request_id:
            return None
        
        # Haal alle requests op en filter op ID
        all_requests = await self.ombi_get_all_requests()
        
        # Zoek de specifieke request
        for req in all_requests:
            req_id = req.get("requestId") or req.get("id")
            
            # DEBUG: Log alle IDs die we vinden
            title = req.get("title") or req.get("name", "Unknown")
            logger.debug(f"Checking request: {title}, parent ID={req_id}, mediaType={req.get('mediaType')}")
            
            # Check parent level ID
            if req_id == request_id:
                logger.info(f"Found Ombi request {request_id} ({title}): available={req.get('available', False)}")
                return req
            
            # For TV shows, also check childRequests IDs
            if req.get("mediaType") == "tv":
                child_requests = req.get("childRequests", [])
                logger.debug(f"  {title} has {len(child_requests)} childRequests")
                for child in child_requests:
                    child_id = child.get("id") or child.get("requestId")
                    logger.debug(f"    child ID: {child_id}")
                    if child_id == request_id:
                        logger.info(f"Found Ombi request {request_id} ({title}) in childRequests: available={req.get('available', False)}")
                        return req
        
        logger.warning(f"Request ID {request_id} not found in Ombi (checked parent and child IDs)")
        return None

    # Emby
    async def emby_search(self, title: str, content_type: str = "Movie"):
        if not self.emby_url:
            return None
        await self.ensure_session()
        url = f"{self.emby_url}/Items"
        params = {
            "searchTerm": title,
            "IncludeItemTypes": content_type,
            "Recursive": "true",  # String niet boolean (aiohttp requirement)
            "Fields": "Path,Overview"
        }
        headers = {"X-Emby-Token": self.emby_key} if self.emby_key else {}
        data, status = await self._request_json("GET", url, params=params, headers=headers, timeout=10)
        
        # Debug logging
        if data:
            items = data.get("Items", [])
            logger.info(f"Emby search voor '{title}' ({content_type}): {len(items)} resultaten")
            if items:
                logger.info(f"  - Eerste resultaat: {items[0].get('Name', 'Unknown')}")
        
        return data
    
    async def emby_search_smart(self, title: str, content_type: str = "Movie"):
        """
        Slimmere Emby search die meerdere varianten probeert
        om betere matches te vinden. Filtert op similarity.
        """
        from difflib import SequenceMatcher
        
        def similarity(a: str, b: str) -> float:
            """Calculate similarity score between two strings (0-1)"""
            return SequenceMatcher(None, a.lower(), b.lower()).ratio()
        
        # Probeer eerst exacte match
        result = await self.emby_search(title, content_type)
        if result and result.get("Items"):
            items = result["Items"]
            
            # Filter results by title similarity - keep only good matches (>0.6 similarity)
            filtered_items = []
            for item in items:
                item_name = item.get("Name", "")
                score = similarity(title, item_name)
                
                # Log similarity for debugging
                logger.info(f"  Similarity: {score:.2f} - '{item_name}' vs '{title}'")
                
                if score >= 0.6:  # At least 60% similar
                    filtered_items.append(item)
            
            if filtered_items:
                result["Items"] = filtered_items
                logger.info(f"Filtered to {len(filtered_items)} relevant results (similarity >= 0.6)")
                return result
        
        # Probeer zonder jaar (bijv. "The Matrix (1999)" -> "The Matrix")
        import re
        title_no_year = re.sub(r'\s*\(\d{4}\)\s*$', '', title).strip()
        if title_no_year != title:
            logger.info(f"Probeer zonder jaar: '{title_no_year}'")
            result = await self.emby_search(title_no_year, content_type)
            if result and result.get("Items"):
                items = result["Items"]
                filtered_items = [item for item in items if similarity(title_no_year, item.get("Name", "")) >= 0.6]
                if filtered_items:
                    result["Items"] = filtered_items
                    return result
        
        # Probeer zonder "The" aan het begin
        if title.lower().startswith("the "):
            title_no_the = title[4:]
            logger.info(f"Probeer zonder 'The': '{title_no_the}'")
            result = await self.emby_search(title_no_the, content_type)
            if result and result.get("Items"):
                items = result["Items"]
                filtered_items = [item for item in items if similarity(title_no_the, item.get("Name", "")) >= 0.6]
                if filtered_items:
                    result["Items"] = filtered_items
                    return result
        
        # Probeer met "The" aan het eind (bijv. "Matrix, The")
        if not title.lower().startswith("the ") and ", the" not in title.lower():
            title_with_the_end = f"{title}, The"
            logger.info(f"Probeer met 'The' aan eind: '{title_with_the_end}'")
            result = await self.emby_search(title_with_the_end, content_type)
            if result and result.get("Items"):
                items = result["Items"]
                filtered_items = [item for item in items if similarity(title, item.get("Name", "")) >= 0.6]
                if filtered_items:
                    result["Items"] = filtered_items
                    return result
        
        # Geen match gevonden
        logger.warning(f"Geen Emby match gevonden voor '{title}' met alle varianten")
        return None
    
    async def emby_get_recent(self, limit: int = 10):
        """Get recently added items from Emby"""
        if not self.emby_url:
            return None
        await self.ensure_session()
        url = f"{self.emby_url}/Items"
        params = {
            "SortBy": "DateCreated",
            "SortOrder": "Descending",
            "Recursive": "true",
            "Limit": limit,
            "Fields": "DateCreated,Overview",
            "IncludeItemTypes": "Movie,Series,Episode"
        }
        headers = {"X-Emby-Token": self.emby_key} if self.emby_key else {}
        data, status = await self._request_json("GET", url, params=params, headers=headers, timeout=10)
        return data
    
    async def emby_get_series_details(self, series_name: str):
        """Get detailed info about a series including seasons and episodes"""
        if not self.emby_url:
            return None
        await self.ensure_session()
        
        # First find the series
        url = f"{self.emby_url}/Items"
        params = {"searchTerm": series_name, "IncludeItemTypes": "Series", "Recursive": "true"}
        headers = {"X-Emby-Token": self.emby_key} if self.emby_key else {}
        data, status = await self._request_json("GET", url, params=params, headers=headers, timeout=10)
        
        if not data or not data.get("Items"):
            return None
        
        series_id = data["Items"][0]["Id"]
        
        # Get episodes for this series
        url = f"{self.emby_url}/Shows/{series_id}/Episodes"
        params = {"Fields": "DateCreated,Overview"}
        episodes_data, _ = await self._request_json("GET", url, params=params, headers=headers, timeout=10)
        
        return {"series": data["Items"][0], "episodes": episodes_data}
    
    async def emby_get_latest_episodes(self, series_name: str, days: int = 7):
        """Get episodes added in the last N days for a series"""
        details = await self.emby_get_series_details(series_name)
        if not details or not details.get("episodes"):
            return []
        
        from datetime import datetime, timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        recent_episodes = []
        for ep in details["episodes"].get("Items", []):
            created = ep.get("DateCreated", "")
            if created:
                try:
                    ep_date = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    if ep_date > cutoff:
                        recent_episodes.append(ep)
                except:
                    pass
        
        return recent_episodes

    async def emby_get_seasons(self, series_id: str):
        """Get all seasons for a series by ID"""
        if not self.emby_url:
            return []
        await self.ensure_session()
        
        url = f"{self.emby_url}/Shows/{series_id}/Seasons"
        params = {"api_key": self.emby_key, "Fields": "Overview"}
        
        async with self.session.get(url, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("Items", [])
        return []

    async def emby_get_user_continue_watching(self, emby_user_id: str):
        """Get series that the user is currently watching (Continue Watching list)"""
        if not self.emby_url:
            return []
        await self.ensure_session()
        
        url = f"{self.emby_url}/Users/{emby_user_id}/Items/Resume"
        params = {
            "api_key": self.emby_key,
            "MediaTypes": "Video",
            "IncludeItemTypes": "Episode",
            "Recursive": "true",
            "Fields": "SeriesInfo,Overview",
            "Limit": 50
        }
        
        async with self.session.get(url, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                items = data.get("Items", [])
                
                # Extract unique series IDs
                series_ids = set()
                series_info = {}
                for item in items:
                    series_id = item.get("SeriesId")
                    series_name = item.get("SeriesName")
                    if series_id:
                        series_ids.add(series_id)
                        series_info[series_id] = {
                            "id": series_id,
                            "name": series_name,
                            "last_watched_episode": item.get("Name"),
                            "season": item.get("ParentIndexNumber"),
                            "episode": item.get("IndexNumber")
                        }
                
                return list(series_info.values())
        return []

    async def emby_get_latest_episode(self, series_id: str, max_age_hours: int = 48):
        """Get the latest episode for a series (if added within max_age_hours)"""
        if not self.emby_url:
            return None
        await self.ensure_session()
        
        url = f"{self.emby_url}/Shows/{series_id}/Episodes"
        params = {
            "api_key": self.emby_key,
            "Fields": "DateCreated,Overview",
            "SortBy": "DateCreated",
            "SortOrder": "Descending",
            "Limit": 1
        }
        
        async with self.session.get(url, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                items = data.get("Items", [])
                
                if items:
                    episode = items[0]
                    date_created = episode.get("DateCreated")
                    
                    if date_created:
                        from datetime import datetime, timedelta
                        try:
                            ep_date = datetime.fromisoformat(date_created.replace("Z", "+00:00"))
                            cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
                            
                            # Only return if it's recent
                            if ep_date > cutoff:
                                return {
                                    "id": episode.get("Id"),
                                    "name": episode.get("Name"),
                                    "season": episode.get("ParentIndexNumber"),
                                    "episode": episode.get("IndexNumber"),
                                    "overview": episode.get("Overview", ""),
                                    "series_name": episode.get("SeriesName"),
                                    "date_added": date_created
                                }
                        except:
                            pass
        return None

    async def emby_get_episodes(self, series_id: str, season_id: str = None):
        """Get episodes for a series, optionally filtered by season"""
        if not self.emby_url:
            return []
        await self.ensure_session()
        
        url = f"{self.emby_url}/Shows/{series_id}/Episodes"
        params = {"api_key": self.emby_key, "Fields": "Overview"}
        
        if season_id:
            params["SeasonId"] = season_id
        
        async with self.session.get(url, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("Items", [])
        return []

    async def emby_verify_series_seasons(self, series_name: str, requested_seasons_data: list):
        """
        Verify per-season episode completeness for a series.
        requested_seasons_data format: [{"seasonNumber": 11, "episodes": [...]}, ...]
        
        Returns: (is_complete: bool, series_id: str, message: str)
        """
        if not self.emby_url or not requested_seasons_data:
            return False, None, "Geen episode data"
        
        await self.ensure_session()
        
        # Find the series in Emby
        url = f"{self.emby_url}/Items"
        params = {"searchTerm": series_name, "IncludeItemTypes": "Series", "Recursive": "true"}
        headers = {"X-Emby-Token": self.emby_key} if self.emby_key else {}
        data, status = await self._request_json("GET", url, params=params, headers=headers, timeout=10)
        
        if not data or not data.get("Items"):
            logger.warning(f"Serie '{series_name}' niet gevonden in Emby")
            return False, None, "Serie niet gevonden in Emby"
        
        series_id = data["Items"][0]["Id"]
        
        # Get all seasons for this series
        seasons = await self.emby_get_seasons(series_id)
        if not seasons:
            logger.warning(f"Geen seizoenen gevonden voor '{series_name}'")
            return False, series_id, "Geen seizoenen gevonden"
        
        # Build season map: {season_number: season_id}
        season_map = {s.get("IndexNumber"): s.get("Id") for s in seasons if s.get("IndexNumber") is not None}
        
        # Check each requested season
        incomplete_seasons = []
        for season_req in requested_seasons_data:
            season_num = season_req.get("seasonNumber")
            expected_episodes = season_req.get("episodes", [])
            expected_count = len(expected_episodes)
            
            if expected_count == 0:
                # No specific episodes requested, assume season is OK if it exists
                if season_num in season_map:
                    continue
                else:
                    incomplete_seasons.append(f"S{season_num} (niet gevonden)")
                    continue
            
            # Get episodes for this season from Emby
            season_id = season_map.get(season_num)
            if not season_id:
                logger.warning(f"Seizoen {season_num} niet gevonden in Emby voor '{series_name}'")
                incomplete_seasons.append(f"S{season_num} (niet gevonden)")
                continue
            
            episodes = await self.emby_get_episodes(series_id, season_id)
            actual_count = len(episodes)
            
            # Calculate ratio for THIS season
            ratio = actual_count / expected_count if expected_count > 0 else 0
            
            logger.info(f"'{series_name}' S{season_num}: {actual_count}/{expected_count} episodes ({ratio:.0%})")
            
            if ratio < 0.7:
                incomplete_seasons.append(f"S{season_num} ({actual_count}/{expected_count})")
        
        if incomplete_seasons:
            message = f"Onvoldoende episodes: {', '.join(incomplete_seasons)}"
            logger.info(f"'{series_name}' nog niet compleet: {message}")
            return False, series_id, message
        
        logger.info(f"'{series_name}' alle aangevraagde seizoenen zijn compleet!")
        return True, series_id, "Alle seizoenen compleet"

    async def emby_get_user_by_name(self, username: str):
        """Get Emby user ID by username"""
        url = f"{self.emby_url}/Users"
        params = {"api_key": self.emby_key}
        
        async with self.session.get(url, params=params) as resp:
            if resp.status == 200:
                users = await resp.json()
                for user in users:
                    if user.get("Name", "").lower() == username.lower():
                        return user
        return None

    async def emby_get_user_devices(self, emby_user_id: str):
        """Get all devices for an Emby user (from sessions)"""
        url = f"{self.emby_url}/Sessions"
        params = {"api_key": self.emby_key}
        
        async with self.session.get(url, params=params) as resp:
            if resp.status == 200:
                sessions = await resp.json()
                # Filter sessions voor deze gebruiker
                user_sessions = [s for s in sessions if s.get("UserId") == emby_user_id]
                
                # Extract device info
                devices = []
                for session in user_sessions:
                    device = {
                        "session_id": session.get("Id"),  # SESSION ID (niet DeviceId!) voor playback
                        "device_id": session.get("DeviceId"),
                        "device_name": session.get("DeviceName"),
                        "client": session.get("Client"),
                        "last_activity": session.get("LastActivityDate"),
                        "supports_remote_control": session.get("SupportsRemoteControl", False),
                        "is_active": session.get("NowPlayingItem") is not None
                    }
                    devices.append(device)
                
                return devices
        return []

    async def emby_get_item_playstate(self, emby_user_id: str, item_id: str):
        """Get playback state for an item for a specific user"""
        url = f"{self.emby_url}/Users/{emby_user_id}/Items/{item_id}"
        params = {"api_key": self.emby_key}
        
        async with self.session.get(url, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                user_data = data.get("UserData", {})
                played_percentage = user_data.get("PlayedPercentage", 0)
                playback_position_ticks = user_data.get("PlaybackPositionTicks", 0)
                is_played = user_data.get("Played", False)
                
                # Return relevant playstate info
                return {
                    "played_percentage": played_percentage,
                    "playback_position_ticks": playback_position_ticks,
                    "is_played": is_played,
                    "has_progress": playback_position_ticks > 0 and played_percentage < 95  # Niet helemaal gezien
                }
        return None

    async def emby_start_playback(self, session_id: str, item_id: str, start_position_ticks: int = 0):
        """Start playback of an item on a specific session"""
        # Stuur play command naar session via Sessions API
        url = f"{self.emby_url}/Sessions/{session_id}/Playing"
        params = {"api_key": self.emby_key}
        
        payload = {
            "ItemIds": [item_id],  # Array van item IDs
            "PlayCommand": "PlayNow",
            "StartPositionTicks": start_position_ticks  # 0 = vanaf begin, anders hervatten
        }
        
        async with self.session.post(url, params=params, json=payload) as resp:
            if resp.status in [200, 204]:
                logger.info(f"Started playback on session {session_id} at position {start_position_ticks}")
                return True
            else:
                error = await resp.text()
                logger.error(f"Failed to start playback: {resp.status} - {error}")
                return False

    async def emby_get_item_id(self, title: str, content_type: str = None):
        """Get Emby item ID by title"""
        result = await self.emby_search(title, content_type=content_type)
        if result and result.get("Items"):
            return result["Items"][0].get("Id")
        return None



def load_config():
    """Load configuration from config.yaml"""




async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = get_user_by_telegram_id(user.id)
    
    # Log incoming command
    log_bot_message("command", user.id, user.username or user.first_name, "/start", "received")
    
    # Eerste keer - niet geregistreerd of niet goedgekeurd (anti-spam versie)
    if not user_data or not user_data.get("approved"):
        if not user_data:
            # Nieuwe gebruiker - kort en privé systeem benadrukken
            await reply_and_log(
                update.message,
                f"👋 Hallo {user.first_name}!\n\n"
                "🔐 **Privé Media Bot**\n\n"
                "Deze bot is onderdeel van een gesloten media server voor uitgenodigde gebruikers.\n\n"
                "Heb je al een account bij deze Emby server?\n\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "📝 **Account Koppelen**\n\n"
                "Type dit commando:\n"
                "`/register`\n\n"
                "_(Kopieer en stuur het commando inclusief de /)_\n\n"
                "De beheerder koppelt je dan aan je Emby account.\n\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "❌ **Geen Emby Account?**\n"
                "Neem eerst contact op met de beheerder.",
                user,
                parse_mode="Markdown"
            )
        else:
            # Al geregistreerd, nog niet goedgekeurd
            reg_date = user_data.get('registered_at', 'onbekend')[:10]
            await reply_and_log(
                update.message,
                f"👋 Hallo {user.first_name}!\n\n"
                "⏳ **Wachten op Goedkeuring**\n\n"
                f"Je registratie is verstuurd op **{reg_date}**.\n\n"
                "De beheerder koppelt je account binnenkort. "
                "Je krijgt automatisch een bericht als je goedgekeurd bent.\n\n"
                "💡 Dit is een privé systeem voor bestaande Emby gebruikers.",
                user,
                parse_mode="Markdown"
            )
    else:
        # Goedgekeurde gebruiker - kort en vriendelijk
        await reply_and_log(
            update.message,
            f"👋 Hey {user.first_name}!\n\n"
            f"✨ Ingelogd als: **{user_data.get('emby_username')}**\n\n"
            "🚀 **Snel starten:**\n"
            "Stuur me een titel:\n"
            "• Dune\n"
            "• Breaking Bad\n"
            "• The Matrix\n\n"
            "🎬 Films: Direct ▶️ afspelen\n"
            "📺 Series: Kies seizoen + aflevering\n\n"
            "─────────────\n\n"
            "⚙️ Commands: /help | /status | /recent\n\n"
            "_Veel kijkplezier!_ 🍿",
            user,
            parse_mode="Markdown"
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Uitgebreide help voor eindgebruikers"""
    user = update.effective_user
    user_data = get_user_by_telegram_id(user.id)
    is_approved = user_data and user_data.get("approved")
    
    # Log incoming command
    log_bot_message("command", user.id, user.username or user.first_name, "/help", "received")
    
    # Niet-geregistreerde of niet-goedgekeurde gebruikers krijgen minimale help
    if not is_approved:
        if not user_data:
            # Helemaal niet geregistreerd
            await update.message.reply_text(
                "ℹ️ **Help - Privé Media Bot**\n\n"
                "Deze bot is onderdeel van een gesloten media server voor uitgenodigde gebruikers.\n\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "🔐 **Toegang Nodig?**\n\n"
                "Als je al een Emby account hebt bij deze server, koppel je Telegram:\n\n"
                "`/register`\n\n"
                "Na goedkeuring krijg je toegang tot alle functies!\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "❌ **Geen Emby Account?**\n\n"
                "Deze bot is niet voor openbaar gebruik. "
                "Neem contact op met de beheerder voor toegang tot de Emby server.",
                parse_mode="Markdown"
            )
        else:
            # Wel geregistreerd maar nog niet goedgekeurd
            await update.message.reply_text(
                "ℹ️ **Help - Wachten op Goedkeuring**\n\n"
                f"Je registratie is verstuurd op {user_data.get('registered_at', 'onbekend')[:10]}.\n\n"
                "De beheerder koppelt je account binnenkort aan Emby. "
                "Je krijgt een bericht zodra je goedgekeurd bent.\n\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "🎯 **Na goedkeuring gebruikmaken van alle functies!**\n\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "⏳ Even geduld... je hoort snel van ons!",
                parse_mode="Markdown"
            )
        return
    
    # Volledige help voor goedgekeurde gebruikers
    help_text = (
        "📖 **Emby Bot - Volledige Handleiding**\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    
    help_text += (
        f"✅ Je bent ingelogd als: **{user_data.get('emby_username')}**\n\n"
    )
    
    help_text += (
        "🎬 **Content Aanvragen**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Type gewoon de titel - de bot doet de rest!\n\n"
        "**Voorbeelden:**\n"
        "• \"Dune\"\n"
        "• \"Breaking Bad\"\n"
        "• \"The Matrix\"\n"
        "• \"Interstellar\"\n\n"
        "Je kunt ook natuurlijk typen:\n"
        "• \"Ik wil The Office kijken\"\n"
        "• \"Zoek Inception\"\n"
        "• \"Heb je Stranger Things?\"\n\n"
        "🔍 **Wat gebeurt er?**\n"
        "1️⃣ Bot zoekt in Ombi\n"
        "2️⃣ Toont resultaten met knoppen\n"
        "3️⃣ Kies het juiste resultaat\n"
        "4️⃣ Als beschikbaar: direct afspelen! ▶️\n"
        "5️⃣ Nog niet beschikbaar? Wordt automatisch aangevraagd\n"
        "6️⃣ Je krijgt een bericht zodra het klaar is! 🔔\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📺 **Series Afspelen**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Voor series kun je exact kiezen welke aflevering:\n\n"
        "**Stap voor stap:**\n"
        "1️⃣ Type serienaam (bijv. \"Breaking Bad\")\n"
        "2️⃣ Klik ▶️ Afspelen (als beschikbaar)\n"
        "3️⃣ Kies seizoen uit het menu\n"
        "4️⃣ Kies aflevering uit het menu\n"
        "5️⃣ Selecteer je apparaat\n"
        "6️⃣ Afspelen start automatisch! 🍿\n\n"
        "💡 **Hervatten:**\n"
        "Als je een aflevering al deels hebt gekeken, "
        "vraagt de bot of je wilt hervatten waar je gebleven was!\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🎥 **Films Afspelen**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Nog simpeler dan series:\n\n"
        "1️⃣ Type filmtitel (bijv. \"Inception\")\n"
        "2️⃣ Klik ▶️ Afspelen\n"
        "3️⃣ Selecteer je apparaat\n"
        "4️⃣ Film start! 🎬\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔔 **Automatische Notificaties**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Je ontvangt automatisch berichten bij:\n\n"
        "✅ Je aanvraag is goedgekeurd in Ombi\n"
        "📺 Content is beschikbaar in Emby (met afspeelknop!)\n"
        "🆕 Nieuwe aflevering van een serie die je kijkt\n\n"
        "**Aflevering notificaties:**\n"
        "De bot monitort welke series je aan het kijken bent en "
        "stuurt automatisch een bericht bij nieuwe afleveringen!\n\n"
        "Uitzetten? Gebruik /notifications\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "⚙️ **Alle Commands**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
    )
    
    help_text += (
        "/start - Welkomstboodschap\n"
        "/help - Deze handleiding\n"
        "/status - Bekijk je aanvragen\n"
        "/notifications - Toggle aflevering alerts\n"
        "/recent - Laatst toegevoegd aan Emby\n"
        "/myshows - Jouw aangevraagde series\n"
        "/updates - Check nieuwe afleveringen\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "❓ **Veelgestelde Vragen**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "**Q: Hoe lang duurt het voor content beschikbaar is?**\n"
        "A: Dat hangt af van Ombi en de download snelheid. Je krijgt automatisch een bericht!\n\n"
        "**Q: Kan ik meerdere dingen tegelijk aanvragen?**\n"
        "A: Ja! Type gewoon meerdere titels na elkaar.\n\n"
        "**Q: Werkt dit op mijn TV/tablet/telefoon?**\n"
        "A: Ja! Je kunt kiezen op welk apparaat je wilt afspelen.\n\n"
        "**Q: Krijg ik te veel notificaties?**\n"
        "A: Gebruik /notifications om aflevering alerts uit te zetten. Aanvraag notificaties blijven aan.\n\n"
        "**Q: De bot vindt mijn zoekopdracht niet**\n"
        "A: Probeer alleen de titel zonder extra woorden, of probeer de Engelse titel.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "💡 **Tips & Tricks**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "• Gebruik exacte titels voor betere resultaten\n"
        "• Probeer Engelse titels als Nederlands niet werkt\n"
        "• Check /status om je aanvragen te zien\n"
        "• Aflevering notificaties zijn standaard aan\n"
        "• Je kunt op elk moment nieuw zoeken\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🎉 **Veel kijkplezier!**\n\n"
        "Vragen? Neem contact op met de admin."
    )
    
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def request_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💡 Je hoeft /request niet meer te gebruiken!\n\n"
        "Stuur me alleen de titel van wat je wilt:\n"
        "• Dune\n"
        "• The Matrix\n"
        "• Stranger Things\n\n"
        "Probeer het nu!"
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    records = load_requests()
    yours = [r for r in records if r.get("telegram_user_id") == user.id]
    if not yours:
        await update.message.reply_text("Je hebt geen opgeslagen aanvragen.")
        return
    texts = [f"- {r.get('title')} ({'Gemeld' if r.get('notified') else 'Wachtend'})"
 for r in yours]
    await update.message.reply_text("\n".join(texts))


async def recent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toon recent toegevoegde items in Emby"""
    bot: OmbiEmbyBot = context.application.bot_data["bot_instance"]
    await update.message.reply_text("🔍 Ophalen van recent toegevoegde content...")
    
    data = await bot.emby_get_recent(limit=10)
    if not data or not data.get("Items"):
        await update.message.reply_text("Kon geen recente items ophalen van Emby.")
        return
    
    lines = ["📺 **Recent toegevoegd aan Emby:**\n"]
    for item in data["Items"]:
        name = item.get("Name", "Onbekend")
        item_type = item.get("Type", "")
        date_created = item.get("DateCreated", "")
        
        # Format date
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(date_created.replace("Z", "+00:00"))
            date_str = dt.strftime("%d-%m-%Y")
        except:
            date_str = "onbekend"
        
        if item_type == "Episode":
            series_name = item.get("SeriesName", "")
            season = item.get("ParentIndexNumber", "?")
            episode = item.get("IndexNumber", "?")
            icon = "📺"
            lines.append(f"{icon} {series_name} - S{season}E{episode} ({date_str})")
        elif item_type == "Movie":
            icon = "🎬"
            lines.append(f"{icon} {name} ({date_str})")
        elif item_type == "Series":
            icon = "📺"
            lines.append(f"{icon} {name} - Serie ({date_str})")
    
    await update.message.reply_text("\n".join(lines[:15]), parse_mode="Markdown")


async def myshows_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toon jouw aangevraagde series"""
    user = update.effective_user
    records = load_requests()
    
    # Filter voor series van deze gebruiker
    your_series = [r for r in records if r.get("telegram_user_id") == user.id and r.get("content_type") == "Series"]
    
    if not your_series:
        await update.message.reply_text("Je hebt nog geen series aangevraagd.")
        return
    
    await update.message.reply_text("🔍 Ophalen van jouw series...")
    
    bot: OmbiEmbyBot = context.application.bot_data["bot_instance"]
    lines = ["📺 **Jouw aangevraagde series:**\n"]
    
    for record in your_series:
        title = record.get("title", "Onbekend")
        # Check if available in Emby
        emby_check = await bot.emby_search(title, content_type="Series")
        
        if emby_check and emby_check.get("Items"):
            series = emby_check["Items"][0]
            # Get episode count
            details = await bot.emby_get_series_details(title)
            if details and details.get("episodes"):
                ep_count = len(details["episodes"].get("Items", []))
                lines.append(f"✅ {title} ({ep_count} afleveringen)")
            else:
                lines.append(f"✅ {title}")
        else:
            lines.append(f"⏳ {title} (nog niet beschikbaar)")
    
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def updates_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check nieuwe afleveringen van jouw series"""
    user = update.effective_user
    records = load_requests()
    
    # Filter voor series van deze gebruiker die beschikbaar zijn
    your_series = [r for r in records if r.get("telegram_user_id") == user.id 
                   and r.get("content_type") == "Series" 
                   and r.get("notified")]
    
    if not your_series:
        await update.message.reply_text("Je hebt geen series in Emby staan.")
        return
    
    await update.message.reply_text("🔍 Checken voor nieuwe afleveringen...")
    
    bot: OmbiEmbyBot = context.application.bot_data["bot_instance"]
    lines = ["📺 **Nieuwe afleveringen (laatste 7 dagen):**\n"]
    found_any = False
    
    for record in your_series[:5]:  # Limit to 5 series to avoid timeout
        title = record.get("title", "").split(" - S")[0]  # Remove season suffix if present
        
        new_episodes = await bot.emby_get_latest_episodes(title, days=7)
        
        if new_episodes:
            found_any = True
            lines.append(f"\n✅ **{title}**:")
            for ep in new_episodes[:3]:  # Max 3 episodes per series
                season = ep.get("ParentIndexNumber", "?")
                episode = ep.get("IndexNumber", "?")
                ep_name = ep.get("Name", "")
                lines.append(f"  • S{season}E{episode} - {ep_name}")
        else:
            lines.append(f"\n⏸️ {title} - geen nieuwe afleveringen")
    
    if not found_any:
        await update.message.reply_text("Geen nieuwe afleveringen in de laatste 7 dagen.")
    else:
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def register_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nieuwe gebruiker registratie"""
    user = update.effective_user
    
    # Check of al geregistreerd
    existing_user = get_user_by_telegram_id(user.id)
    if existing_user:
        if existing_user.get("approved"):
            await update.message.reply_text(
                f"✅ Je bent al goedgekeurd!\n\n"
                f"Emby gebruiker: {existing_user.get('emby_username')}"
            )
        else:
            await update.message.reply_text(
                "⏳ Je aanvraag wacht op goedkeuring van de admin.\n"
                "Je krijgt een bericht wanneer je toegang hebt!"
            )
        return
    
    # Nieuwe registratie
    users = load_users()
    new_user = {
        "telegram_user_id": user.id,
        "telegram_username": user.username or user.first_name,
        "telegram_first_name": user.first_name,
        "telegram_last_name": user.last_name,
        "registered_at": datetime.now().isoformat(),
        "approved": False,
        "emby_username": None,
        "emby_user_id": None,
        "episode_notifications": True  # Standaard aan
    }
    users.append(new_user)
    save_users(users)
    
    await update.message.reply_text(
        "✅ Registratie aanvraag verstuurd!\n\n"
        "De admin ontvangt nu een notificatie en kan je account koppelen aan Emby.\n"
        "Je krijgt een bericht zodra je bent goedgekeurd."
    )
    
    # Notificeer admin
    config = context.application.bot_data.get("config", {})
    admin_id = config.get("admin_telegram_id")
    
    if admin_id:
        admin_msg = (
            f"🆕 **Nieuwe registratie aanvraag**\n\n"
            f"Telegram ID: `{user.id}`\n"
            f"Naam: {user.first_name} {user.last_name or ''}\n"
            f"Username: @{user.username or 'geen'}\n\n"
            f"Gebruik: `/approve {user.id} <emby_username>`"
        )
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=admin_msg,
                parse_mode="Markdown"
            )
            logger.info(f"Admin notificatie gestuurd voor registratie van {user.id}")
        except Exception as e:
            logger.error(f"Kon admin niet notificeren: {e}")
    else:
        logger.warning("Geen admin_telegram_id geconfigureerd in config.yaml!")


async def approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command om gebruiker goed te keuren"""
    user = update.effective_user
    config = context.application.bot_data.get("config", {})
    admin_id = config.get("admin_telegram_id")
    
    # Check admin rechten
    if user.id != admin_id:
        await update.message.reply_text("❌ Alleen de admin kan gebruikers goedkeuren.")
        return
    
    # Parse argumenten: /approve <telegram_id> <emby_username>
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Gebruik: `/approve <telegram_id> <emby_username>`\n\n"
            "Voorbeeld: `/approve 123456789 john_doe`",
            parse_mode="Markdown"
        )
        return
    
    try:
        telegram_id = int(args[0])
        emby_username = args[1]
    except ValueError:
        await update.message.reply_text("❌ Telegram ID moet een nummer zijn.")
        return
    
    # Zoek gebruiker
    users = load_users()
    target_user = None
    for u in users:
        if u.get("telegram_user_id") == telegram_id:
            target_user = u
            break
    
    if not target_user:
        await update.message.reply_text(f"❌ Geen gebruiker gevonden met Telegram ID: {telegram_id}")
        return
    
    # TODO: Check of emby_username bestaat in Emby
    bot: OmbiEmbyBot = context.application.bot_data["bot_instance"]
    # Voor nu accepteren we gewoon de username
    
    # Update gebruiker
    target_user["approved"] = True
    target_user["emby_username"] = emby_username
    target_user["approved_at"] = datetime.now().isoformat()
    target_user["approved_by"] = user.id
    target_user["needs_notification"] = False  # Direct versturen via Telegram
    save_users(users)
    
    # Bevestig aan admin
    await update.message.reply_text(
        f"✅ Gebruiker goedgekeurd!\n\n"
        f"Telegram: {target_user.get('telegram_first_name')} ({telegram_id})\n"
        f"Emby: {emby_username}"
    )
    
    # Notificeer de gebruiker
    try:
        # Eerste bericht: goedkeuring
        await context.bot.send_message(
            chat_id=telegram_id,
            text=f"🎉 **Je account is goedgekeurd!**\n\n"
                 f"Je bent gekoppeld aan Emby gebruiker: **{emby_username}**\n\n",
            parse_mode="Markdown"
        )
        
        # Wacht even voor leesbaarheid
        await asyncio.sleep(1)
        
        # Tweede bericht: Welkom met features en hoe het werkt
        await context.bot.send_message(
            chat_id=telegram_id,
            text=f"🤖 Welkom {target_user.get('telegram_first_name')} bij de Emby Bot!\n\n"
                 "Fijn dat je er bent! Deze bot maakt het super makkelijk om films en series aan te vragen en af te spelen via Emby.\n\n"
                 "📚 **Wat kun je met deze bot?**\n"
                 "• 🎬 Films en series aanvragen\n"
                 "• ▶️ Direct afspelen op je apparaten\n"
                 "• 📺 Seizoenen en afleveringen kiezen\n"
                 "• 🔔 Automatische notificaties ontvangen\n"
                 "• 🆕 Update alerts voor nieuwe afleveringen\n\n"
                 "💡 **Hoe werkt het?**\n"
                 "Heel simpel - type gewoon de titel:\n"
                 "• \"Dune\"\n"
                 "• \"Breaking Bad\"\n"
                 "• \"The Matrix\"\n\n"
                 "De bot zoekt automatisch en toont resultaten met knoppen. Als content al beschikbaar is, kun je meteen afspelen!\n\n"
                 "🎯 **Series Afspelen:**\n"
                 "Voor series kun je exact kiezen:\n"
                 "1️⃣ Kies seizoen uit het menu\n"
                 "2️⃣ Kies aflevering\n"
                 "3️⃣ Selecteer je apparaat\n"
                 "4️⃣ Kijken maar! 🍿\n\n"
                 "📱 **Handige Commands:**\n"
                 "/help - Volledig overzicht\n"
                 "/status - Je aanvragen bekijken\n"
                 "/notifications - Aflevering alerts aan/uit",
            parse_mode="Markdown"
        )
        
        # Wacht 2 seconden
        await asyncio.sleep(2)
        
        # Derde bericht: Notificaties en commands
        await context.bot.send_message(
            chat_id=telegram_id,
            text="🔔 **Automatische Updates**\n\n"
                 "Je krijgt een bericht wanneer:\n"
                 "✅ Content beschikbaar is in Emby\n"
                 "🆕 Er nieuwe afleveringen zijn van series die je kijkt\n\n"
                 "_Notificaties uitzetten? Gebruik /notifications_\n\n"
                 "─────────────\n\n"
                 "⚙️ **Handige Commands:**\n\n"
                 "/help → Uitgebreide handleiding\n"
                 "/status → Bekijk je aanvragen\n"
                 "/recent → Laatst toegevoegd\n"
                 "/myshows → Jouw series\n\n"
                 "─────────────\n\n"
                 "🎬 **Start nu:** Stuur me een titel!\n\n"
                 "_Veel kijkplezier!_ 🍿",
            parse_mode="Markdown"
        )
        
        logger.info(f"Goedkeuringsnotificatie en handleiding gestuurd naar gebruiker {telegram_id}")
    except Exception as e:
        logger.error(f"Kon gebruiker {telegram_id} niet notificeren: {e}")
        # Zet flag zodat poller het later probeert
        target_user["needs_notification"] = True
        save_users(users)
        await update.message.reply_text(f"⚠️  Gebruiker goedgekeurd, maar kon geen notificatie sturen. Bot zal het later proberen.")


async def notifications_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle episode notifications voor gebruiker"""
    user = update.effective_user
    
    # Check if user is approved
    user_data = get_user_by_telegram_id(user.id)
    if not user_data or not user_data.get("approved"):
        await update.message.reply_text(
            "⚠️ Je moet eerst je account koppelen!\n\n"
            "Gebruik /register om een aanvraag in te dienen."
        )
        return
    
    # Toggle notification setting
    users = load_users()
    for u in users:
        if u.get("telegram_user_id") == user.id:
            current = u.get("episode_notifications", True)  # Default aan
            u["episode_notifications"] = not current
            save_users(users)
            
            if u["episode_notifications"]:
                await update.message.reply_text(
                    "🔔 **Episode notificaties ingeschakeld!**\n\n"
                    "Je ontvangt een bericht wanneer er nieuwe afleveringen zijn "
                    "voor series die je aan het kijken bent.",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    "🔕 **Episode notificaties uitgeschakeld**\n\n"
                    "Je ontvangt geen berichten meer over nieuwe afleveringen.\n"
                    "Gebruik /notifications opnieuw om ze weer in te schakelen.",
                    parse_mode="Markdown"
                )
            return
    
    await update.message.reply_text("❌ Gebruiker niet gevonden.")


async def show_result(context: ContextTypes.DEFAULT_TYPE, chat_id: int, result: dict, index: int, total: int, message_id: int = None, user=None):
    """Toon 1 resultaat met poster en ja/nee knoppen"""
    name = result.get("title", "Onbekend")
    year = (result.get("releaseDate", ""))[:4]
    overview = result.get("overview", "Geen beschrijving")[:300]
    available = result.get("available", False)
    media_type = result.get("mediaType", "movie").lower()
    type_icon = "📺" if media_type in ("tv", "series") else "🎬"
    
    status_text = "\u2705 Al beschikbaar" if available else "\u2b55 Nog niet beschikbaar"
    caption = f"{type_icon} **{name}** ({year})\n\n{overview}...\n\n{status_text}\n({index + 1}/{total})\n\nIs dit wat je zoekt?"
    
    # Log dit zoekresultaat
    if user:
        username = user.username or user.first_name
        log_text = f"{type_icon} {name} ({year})\n{status_text}\n({index + 1}/{total}) Is dit wat je zoekt?"
        log_bot_message("text", user.id, username, log_text, "sent")
    
    # Poster URL - Probeer alle mogelijke velden
    # Ombi kan verschillende veldnamen gebruiken: posterPath, banner, poster, background
    poster_path = (
        result.get("posterPath") or 
        result.get("banner") or 
        result.get("poster") or
        result.get("background")
    )
    
    # Als we een path hebben, gebruik TMDB CDN
    poster_url = None
    if poster_path:
        # Soms begint het al met http, anders is het een relative path
        if poster_path.startswith("http"):
            poster_url = poster_path
        else:
            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
    
    # Debug logging met alle relevante velden
    if not poster_url:
        logger.warning(f"No poster for '{name}'. Keys: {list(result.keys())}")
        logger.warning(f"  posterPath={result.get('posterPath')}, banner={result.get('banner')}, poster={result.get('poster')}, background={result.get('background')}")
    else:
        logger.info(f"Found poster for '{name}': {poster_url}")
    
    # Inline keyboard
    keyboard = [
        [
            InlineKeyboardButton("\u2705 Ja, deze!", callback_data=f"accept_{index}"),
            InlineKeyboardButton("\u274c Nee, volgende", callback_data=f"next_{index}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        if poster_url:
            if message_id:
                # Try to edit as photo/media - this works if previous was also photo
                try:
                    await context.bot.edit_message_media(
                        chat_id=chat_id,
                        message_id=message_id,
                        media={"type": "photo", "media": poster_url},
                        reply_markup=reply_markup
                    )
                    await context.bot.edit_message_caption(
                        chat_id=chat_id,
                        message_id=message_id, 
                        caption=caption,
                        reply_markup=reply_markup,
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    # Previous message was text, not photo - delete and send new
                    logger.warning(f"Could not edit as photo (previous was text): {e}")
                    await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    msg = await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=poster_url,
                        caption=caption,
                        reply_markup=reply_markup,
                        parse_mode="Markdown"
                    )
                    return msg.message_id
            else:
                msg = await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=poster_url,
                    caption=caption,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
                return msg.message_id
        else:
            if message_id:
                # Try to edit as text - this works if previous was also text
                try:
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=caption,
                        reply_markup=reply_markup,
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    # Previous message was photo, not text - delete and send new
                    logger.warning(f"Could not edit as text (previous was photo): {e}")
                    await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    msg = await context.bot.send_message(
                        chat_id=chat_id,
                        text=caption,
                        reply_markup=reply_markup,
                        parse_mode="Markdown"
                    )
                    return msg.message_id
            else:
                msg = await context.bot.send_message(
                    chat_id=chat_id,
                    text=caption,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
                return msg.message_id
    except Exception as e:
        logger.error(f"Unexpected error in show_result: {e}")
        # Last resort fallback - send new text message
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=caption,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return msg.message_id


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button presses"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    data = query.data
    
    # Handle access request button
    if data == "request_access":
        # Check if already registered
        existing_user = get_user_by_telegram_id(user.id)
        if existing_user:
            await query.edit_message_text(
                "⏳ Je aanvraag is al verstuurd!\n\n"
                "De admin ontvangt een notificatie en koppelt je account. "
                "Je krijgt een bericht zodra je bent goedgekeurd.",
                parse_mode="Markdown"
            )
            return
        
        # Register new user
        users = load_users()
        new_user = {
            "telegram_user_id": user.id,
            "telegram_username": user.username or user.first_name,
            "telegram_first_name": user.first_name,
            "telegram_last_name": user.last_name,
            "registered_at": datetime.now().isoformat(),
            "approved": False,
            "emby_username": None,
            "emby_user_id": None,
            "episode_notifications": True  # Default aan
        }
        users.append(new_user)
        save_users(users)
        
        await query.edit_message_text(
            "✅ **Registratie Verstuurd!**\n\n"
            "Je aanvraag is naar de admin gestuurd. Je krijgt een notificatie "
            "zodra je account gekoppeld is aan Emby.\n\n"
            "💡 Dit kan een paar minuten tot uren duren, afhankelijk van wanneer "
            "de admin tijd heeft.",
            parse_mode="Markdown"
        )
        
        # Notify admin
        config = context.application.bot_data.get("config", {})
        admin_id = config.get("admin_telegram_id")
        
        if admin_id:
            admin_msg = (
                f"🆕 **Nieuwe registratie aanvraag**\n\n"
                f"Telegram ID: `{user.id}`\n"
                f"Naam: {user.first_name} {user.last_name or ''}\n"
                f"Username: @{user.username or 'geen'}\n\n"
                f"Keur goed via:\n"
                f"`/approve {user.id} <emby_username>`\n\n"
                f"Of via de web interface: http://localhost:5000/users"
            )
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=admin_msg,
                    parse_mode="Markdown"
                )
                logger.info(f"Admin notificatie gestuurd voor registratie van {user.id}")
            except Exception as e:
                logger.error(f"Kon admin niet notificeren: {e}")
        return
    
    # Handle playback requests
    if data.startswith("play:"):
        parts = data.split(":")
        if len(parts) >= 2:
            item_id = parts[1]
            content_type = parts[2] if len(parts) > 2 else "Movie"
            
            # Check if user is linked
            user_data = get_user_by_telegram_id(user.id)
            if not user_data or not user_data.get("approved"):
                await query.edit_message_text(
                    "❌ Je account is niet gekoppeld aan Emby.\n\n"
                    "Gebruik /register om je aan te melden!"
                )
                return
            
            emby_username = user_data.get("emby_username")
            bot: OmbiEmbyBot = context.application.bot_data["bot_instance"]
            
            # Get Emby user ID
            emby_user = await bot.emby_get_user_by_name(emby_username)
            if not emby_user:
                await query.edit_message_text(f"❌ Emby gebruiker '{emby_username}' niet gevonden.")
                return
            
            emby_user_id = emby_user.get("Id")
            
            # Voor SERIES: toon seizoen keuze menu
            if content_type == "Series":
                await query.edit_message_text("🔍 Seizoenen ophalen...")
                seasons = await bot.emby_get_seasons(item_id)
                
                if not seasons:
                    await query.edit_message_text("❌ Geen seizoenen gevonden voor deze serie.")
                    return
                
                # Maak knoppen voor elk seizoen
                buttons = []
                for season in seasons:
                    season_name = season.get("Name", "Onbekend")
                    season_id = season.get("Id")
                    index_number = season.get("IndexNumber", 0)
                    
                    # Skip specials (seizoen 0) optioneel
                    if index_number == 0:
                        season_label = f"📺 {season_name}"
                    else:
                        season_label = f"📺 Seizoen {index_number}"
                    
                    buttons.append([InlineKeyboardButton(
                        season_label,
                        callback_data=f"season:{item_id}:{season_id}"
                    )])
                
                keyboard = InlineKeyboardMarkup(buttons)
                await query.edit_message_text(
                    "📺 **Kies een seizoen:**",
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
                return
            
            # Voor MOVIES: normale playback flow
            # Check playback state
            playstate = await bot.emby_get_item_playstate(emby_user_id, item_id)
            
            # Get user's devices
            devices = await bot.emby_get_user_devices(emby_user_id)
            
            if not devices:
                await query.edit_message_text(
                    "❌ Geen actieve Emby apparaten gevonden.\n\n"
                    "Zorg dat je bent ingelogd op minimaal één Emby client (app, browser, etc.)"
                )
                return
            
            # Filter devices that support remote control
            playable_devices = [d for d in devices if d.get("supports_remote_control")]
            
            if not playable_devices:
                await query.edit_message_text(
                    "❌ Je apparaten ondersteunen geen remote control.\n\n"
                    "Probeer de Emby app te openen en start handmatig af te spelen."
                )
                return
            
            # Check if there's existing progress
            if playstate and playstate.get("has_progress"):
                played_pct = playstate.get("played_percentage", 0)
                position_ticks = playstate.get("playback_position_ticks", 0)
                
                # Ask user: resume or restart?
                if len(playable_devices) == 1:
                    # Single device - ask resume/restart
                    session_id = playable_devices[0]["session_id"]
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton(f"▶️ Hervatten ({played_pct:.0f}%)", callback_data=f"resume:{session_id}:{item_id}:{position_ticks}")],
                        [InlineKeyboardButton("🔄 Opnieuw beginnen", callback_data=f"restart:{session_id}:{item_id}")]
                    ])
                    await query.edit_message_text(
                        f"📺 Je hebt deze content al voor {played_pct:.0f}% bekeken.\n\n"
                        "Wil je hervatten of opnieuw beginnen?",
                        reply_markup=keyboard
                    )
                else:
                    # Multiple devices - store playstate in callback data
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton(f"▶️ Hervatten ({played_pct:.0f}%)", callback_data=f"playchoice:resume:{item_id}:{position_ticks}")],
                        [InlineKeyboardButton("🔄 Opnieuw beginnen", callback_data=f"playchoice:restart:{item_id}")]
                    ])
                    await query.edit_message_text(
                        f"📺 Je hebt deze content al voor {played_pct:.0f}% bekeken.\n\n"
                        "Wil je hervatten of opnieuw beginnen?",
                        reply_markup=keyboard
                    )
                return
            
            # No existing progress - start normally
            # If only one device, start directly
            if len(playable_devices) == 1:
                device = playable_devices[0]
                success = await bot.emby_start_playback(device["session_id"], item_id)
                
                if success:
                    await query.edit_message_text(
                        f"▶️ **Afspelen gestart!**\n\n"
                        f"Apparaat: {device['device_name']} ({device['client']})",
                        parse_mode="Markdown"
                    )
                else:
                    await query.edit_message_text(
                        "❌ Kon afspelen niet starten. Probeer het handmatig in Emby."
                    )
                return
            
            # Multiple devices - let user choose
            buttons = []
            for device in playable_devices:
                device_label = f"{device['device_name']} ({device['client']})"
                if device.get('is_active'):
                    device_label += " 🟢"
                buttons.append([InlineKeyboardButton(
                    device_label,
                    callback_data=f"playdev:{device['session_id']}:{item_id}:0"
                )])
            
            keyboard = InlineKeyboardMarkup(buttons)
            await query.edit_message_text(
                "📱 **Kies een apparaat:**",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        return
    
    # Handle season selection (voor series)
    if data.startswith("season:"):
        parts = data.split(":")
        if len(parts) >= 3:
            series_id = parts[1]
            season_id = parts[2]
            
            bot: OmbiEmbyBot = context.application.bot_data["bot_instance"]
            await query.edit_message_text("🔍 Afleveringen ophalen...")
            
            episodes = await bot.emby_get_episodes(series_id, season_id)
            
            if not episodes:
                await query.edit_message_text("❌ Geen afleveringen gevonden voor dit seizoen.")
                return
            
            # Maak knoppen voor elke aflevering (max 20 om het overzichtelijk te houden)
            buttons = []
            for episode in episodes[:20]:  # Limit voor Telegram inline keyboard
                ep_name = episode.get("Name", "Onbekend")
                ep_id = episode.get("Id")
                ep_number = episode.get("IndexNumber", "?")
                
                ep_label = f"▶️ Aflevering {ep_number}: {ep_name[:30]}"
                
                buttons.append([InlineKeyboardButton(
                    ep_label,
                    callback_data=f"episode:{ep_id}"
                )])
            
            # Voeg terug knop toe
            buttons.append([InlineKeyboardButton("⬅️ Terug naar seizoenen", callback_data=f"play:{series_id}:Series")])
            
            keyboard = InlineKeyboardMarkup(buttons)
            await query.edit_message_text(
                "📺 **Kies een aflevering:**",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        return
    
    # Handle episode selection (start playback)
    if data.startswith("episode:"):
        parts = data.split(":")
        if len(parts) >= 2:
            episode_id = parts[1]
            
            # Check if user is linked
            user_data = get_user_by_telegram_id(user.id)
            if not user_data or not user_data.get("approved"):
                await query.edit_message_text("❌ Account niet gekoppeld.")
                return
            
            bot: OmbiEmbyBot = context.application.bot_data["bot_instance"]
            emby_username = user_data.get("emby_username")
            
            # Get Emby user ID
            emby_user = await bot.emby_get_user_by_name(emby_username)
            if not emby_user:
                await query.edit_message_text("❌ Emby gebruiker niet gevonden.")
                return
            
            emby_user_id = emby_user.get("Id")
            
            # Check playback state voor deze aflevering
            playstate = await bot.emby_get_item_playstate(emby_user_id, episode_id)
            
            # Get user's devices
            devices = await bot.emby_get_user_devices(emby_user_id)
            playable_devices = [d for d in devices if d.get("supports_remote_control")]
            
            if not playable_devices:
                await query.edit_message_text(
                    "❌ Geen actieve apparaten met remote control."
                )
                return
            
            # Check if there's existing progress
            if playstate and playstate.get("has_progress"):
                played_pct = playstate.get("played_percentage", 0)
                position_ticks = playstate.get("playback_position_ticks", 0)
                
                # Ask user: resume or restart?
                if len(playable_devices) == 1:
                    # Single device
                    session_id = playable_devices[0]["session_id"]
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton(f"▶️ Hervatten ({played_pct:.0f}%)", callback_data=f"resume:{session_id}:{episode_id}:{position_ticks}")],
                        [InlineKeyboardButton("🔄 Opnieuw beginnen", callback_data=f"restart:{session_id}:{episode_id}")]
                    ])
                    await query.edit_message_text(
                        f"📺 Je hebt deze aflevering al voor {played_pct:.0f}% bekeken.\n\n"
                        "Wil je hervatten of opnieuw beginnen?",
                        reply_markup=keyboard
                    )
                else:
                    # Multiple devices
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton(f"▶️ Hervatten ({played_pct:.0f}%)", callback_data=f"playchoice:resume:{episode_id}:{position_ticks}")],
                        [InlineKeyboardButton("🔄 Opnieuw beginnen", callback_data=f"playchoice:restart:{episode_id}")]
                    ])
                    await query.edit_message_text(
                        f"📺 Je hebt deze aflevering al voor {played_pct:.0f}% bekeken.\n\n"
                        "Wil je hervatten of opnieuw beginnen?",
                        reply_markup=keyboard
                    )
                return
            
            # No progress - choose device and start
            if len(playable_devices) == 1:
                # Single device - start direct
                device = playable_devices[0]
                success = await bot.emby_start_playback(device["session_id"], episode_id)
                
                if success:
                    await query.edit_message_text(
                        f"▶️ **Aflevering gestart!**\n\n"
                        f"Apparaat: {device['device_name']}",
                        parse_mode="Markdown"
                    )
                else:
                    await query.edit_message_text("❌ Kon afspelen niet starten.")
            else:
                # Multiple devices - let user choose
                buttons = []
                for device in playable_devices:
                    device_label = f"{device['device_name']} ({device['client']})"
                    if device.get('is_active'):
                        device_label += " 🟢"
                    buttons.append([InlineKeyboardButton(
                        device_label,
                        callback_data=f"playdev:{device['session_id']}:{episode_id}:0"
                    )])
                
                keyboard = InlineKeyboardMarkup(buttons)
                await query.edit_message_text(
                    "📱 **Kies een apparaat:**",
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
        return
    
    # Handle resume/restart decision followed by device selection
    if data.startswith("playchoice:"):
        parts = data.split(":")
        if len(parts) >= 3:
            choice = parts[1]  # "resume" or "restart"
            item_id = parts[2]
            position_ticks = int(parts[3]) if len(parts) > 3 and choice == "resume" else 0
            
            # Get user devices
            user_data = get_user_by_telegram_id(user.id)
            emby_username = user_data.get("emby_username")
            bot: OmbiEmbyBot = context.application.bot_data["bot_instance"]
            
            emby_user = await bot.emby_get_user_by_name(emby_username)
            if not emby_user:
                await query.edit_message_text("❌ Emby gebruiker niet gevonden.")
                return
            
            emby_user_id = emby_user.get("Id")
            devices = await bot.emby_get_user_devices(emby_user_id)
            playable_devices = [d for d in devices if d.get("supports_remote_control")]
            
            if not playable_devices:
                await query.edit_message_text("❌ Geen apparaten beschikbaar.")
                return
            
            # Show device selection with position included in callback
            buttons = []
            for device in playable_devices:
                device_label = f"{device['device_name']} ({device['client']})"
                if device.get('is_active'):
                    device_label += " 🟢"
                buttons.append([InlineKeyboardButton(
                    device_label,
                    callback_data=f"playdev:{device['session_id']}:{item_id}:{position_ticks}"
                )])
            
            keyboard = InlineKeyboardMarkup(buttons)
            action_text = "hervatten" if choice == "resume" else "opnieuw starten"
            await query.edit_message_text(
                f"📱 **Kies een apparaat om {action_text}:**",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        return
    
    # Handle resume decision (single device)
    if data.startswith("resume:"):
        parts = data.split(":")
        if len(parts) >= 4:
            session_id = parts[1]
            item_id = parts[2]
            position_ticks = int(parts[3])
            
            bot: OmbiEmbyBot = context.application.bot_data["bot_instance"]
            success = await bot.emby_start_playback(session_id, item_id, position_ticks)
            
            if success:
                await query.edit_message_text(
                    "▶️ **Hervatten gestart!**\n\n"
                    "Check je apparaat!",
                    parse_mode="Markdown"
                )
            else:
                await query.edit_message_text("❌ Kon afspelen niet starten.")
        return
    
    # Handle restart decision (single device)
    if data.startswith("restart:"):
        parts = data.split(":")
        if len(parts) >= 3:
            session_id = parts[1]
            item_id = parts[2]
            
            bot: OmbiEmbyBot = context.application.bot_data["bot_instance"]
            success = await bot.emby_start_playback(session_id, item_id, 0)
            
            if success:
                await query.edit_message_text(
                    "▶️ **Afspelen vanaf begin gestart!**\n\n"
                    "Check je apparaat!",
                    parse_mode="Markdown"
                )
            else:
                await query.edit_message_text("❌ Kon afspelen niet starten.")
        return
    
    # Handle device selection for playback
    if data.startswith("playdev:"):
        parts = data.split(":")
        if len(parts) >= 3:
            session_id = parts[1]  # Session ID van het gekozen apparaat
            item_id = parts[2]
            position_ticks = int(parts[3]) if len(parts) > 3 else 0
            
            bot: OmbiEmbyBot = context.application.bot_data["bot_instance"]
            
            success = await bot.emby_start_playback(session_id, item_id, position_ticks)
            
            if success:
                action_text = "hervat" if position_ticks > 0 else "gestart"
                await query.edit_message_text(
                    f"▶️ **Afspelen {action_text}!**\n\n"
                    "Check je apparaat!",
                    parse_mode="Markdown"
                )
            else:
                await query.edit_message_text(
                    "❌ Kon afspelen niet starten. Probeer het handmatig."
                )
        return
    
    pending = context.application.bot_data.setdefault("pending", {})
    state = pending.get(user.id)
    
    if not state or "results" not in state:
        # Check of het bericht een foto heeft (caption) of tekst is
        if query.message.photo:
            await query.edit_message_caption(caption="\u26a0\ufe0f Sessie verlopen. Probeer opnieuw te zoeken.")
        else:
            await query.edit_message_text(text="\u26a0\ufe0f Sessie verlopen. Probeer opnieuw te zoeken.")
        return
    
    results = state["results"]
    current_index = state.get("current_index", 0)
    
    if data.startswith("accept_"):
        # Gebruiker accepteert dit resultaat
        result = results[current_index]
        title = result.get('title') or result.get('name')
        
        # Check of het bericht een foto heeft (caption) of tekst is
        if query.message.photo:
            await query.edit_message_caption(caption=f"\u2705 Geselecteerd: {title}")
        else:
            await query.edit_message_text(text=f"\u2705 Geselecteerd: {title}")
        
        # Check of het een serie is
        media_type = result.get("mediaType", "").lower()
        content_type = "Series" if media_type in ("tv", "series") else "Movie"
        bot: OmbiEmbyBot = context.application.bot_data["bot_instance"]
        
        # Check Ombi's 'available' veld - Ombi weet al of content in Emby staat!
        is_available = result.get("available", False)
        
        if is_available:
            # AL BESCHIKBAAR in Emby volgens Ombi!
            await query.message.reply_text(f"🔍 '{title}' is beschikbaar, ophalen van Emby ID...")
            
            # Haal Emby item ID op voor playback
            emby_result = await bot.emby_search_smart(title, content_type=content_type)
            
            if emby_result and isinstance(emby_result, dict):
                items = emby_result.get("Items") or []
                if items:
                    item_id = items[0].get("Id")
                    
                    # Check if user is linked
                    user_data = get_user_by_telegram_id(user.id)
                    
                    if user_data and user_data.get("approved") and user_data.get("emby_username"):
                        keyboard = InlineKeyboardMarkup([[
                            InlineKeyboardButton("▶️ Start Nu", callback_data=f"play:{item_id}:{content_type}")
                        ]])
                        await query.message.reply_text(
                            f"✅ **'{title}' is al beschikbaar in Emby!**\n\n"
                            f"Type: {'🎬 Film' if content_type == 'Movie' else '📺 Serie'}",
                            parse_mode="Markdown",
                            reply_markup=keyboard
                        )
                    else:
                        await query.message.reply_text(
                            f"✅ **'{title}' is al beschikbaar in Emby!**\n\n"
                            f"Type: {'🎬 Film' if content_type == 'Movie' else '📺 Serie'}\n\n"
                            "💡 Gebruik /register om je account te koppelen voor direct afspelen!",
                            parse_mode="Markdown"
                        )
                    pending.pop(user.id, None)
                    return
            
            # Emby ID niet gevonden, maar Ombi zegt dat het beschikbaar is
            await query.message.reply_text(
                f"✅ **'{title}' is beschikbaar in Emby volgens Ombi!**\n\n"
                f"Type: {'🎬 Film' if content_type == 'Movie' else '📺 Serie'}\n\n"
                "⚠️ Let op: Ik kon het niet vinden in Emby. Probeer handmatig te zoeken.",
                parse_mode="Markdown"
            )
            pending.pop(user.id, None)
            return
        
        # Nog NIET in Emby - aanvragen bij Ombi
        if media_type in ("tv", "series"):
            # Vraag om seizoen keuze
            state["selected"] = result
            await query.message.reply_text(
                f"'{title}' staat nog niet in Emby.\n\n"
                f"Wil je alle seizoenen of een specifiek seizoen aanvragen?\n\n"
                "Reageer met:\n"
                "• 'all' voor alle seizoenen\n"
                "• Een nummer (bijv. '1' voor seizoen 1)"
            )
        else:
            # Film - direct aanvragen
            await query.message.reply_text(f"'{title}' staat nog niet in Emby. Aanvragen bij Ombi...")
            resp = await bot.ombi_request(result, media_type="movie")
            if resp:
                records = load_requests()
                records.append({
                    "telegram_user_id": user.id,
                    "telegram_username": user.username,
                    "title": title,
                    "content_type": "Movie",
                    "ombi_response": resp,
                    "requested_at": datetime.now(timezone.utc).isoformat(),
                    "notified": False
                })
                save_requests(records)
                await query.message.reply_text("\u2705 Aanvraag opgeslagen! Ik laat je weten als het in Emby staat.")
            else:
                await query.message.reply_text("\u274c Aanvragen mislukt. Check de bot logs.")
            pending.pop(user.id, None)
    
    elif data.startswith("next_"):
        # Volgende suggestie
        next_index = current_index + 1
        if next_index >= len(results):
            # Einde van resultaten - bied manual entry aan
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✍️ Handmatig opgeven", callback_data="manual_entry")],
                [InlineKeyboardButton("❌ Annuleren", callback_data="cancel")]
            ])
            
            if query.message.photo:
                await query.edit_message_caption(
                    caption="❌ Geen resultaten meer.\n\nWil je de titel handmatig opgeven?",
                    reply_markup=keyboard
                )
            else:
                await query.edit_message_text(
                    text="❌ Geen resultaten meer.\n\nWil je de titel handmatig opgeven?",
                    reply_markup=keyboard
                )
            return
        
        state["current_index"] = next_index
        await show_result(
            context,
            query.message.chat_id,
            results[next_index],
            next_index,
            len(results),
            query.message.message_id,
            user
        )
    
    elif data == "manual_entry":
        # Start manual entry flow - send NEW message for natural conversation
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎬 Film", callback_data="manual_movie")],
            [InlineKeyboardButton("📺 Serie", callback_data="manual_series")],
            [InlineKeyboardButton("❌ Annuleren", callback_data="cancel")]
        ])
        
        # Close old message
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except:
            pass
        
        # Send fresh message
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="📝 Is het een **film** of een **serie**?",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    elif data in ("manual_movie", "manual_series"):
        # User selected type - send NEW message asking for title
        media_type = "Movie" if data == "manual_movie" else "Series"
        type_icon = "🎬" if media_type == "Movie" else "📺"
        type_dutch = "film" if media_type == "Movie" else "serie"
        
        pending[user.id] = {
            "awaiting_manual_title": True,
            "manual_type": media_type
        }
        
        # Close old message
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except:
            pass
        
        # Send fresh message
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"{type_icon} Geef de **exacte titel** op van de {type_dutch}:",
            parse_mode="Markdown"
        )
    
    elif data == "cancel":
        # Cancel current operation
        pending.pop(user.id, None)
        
        # Close message cleanly
        try:
            if query.message.photo:
                await query.edit_message_caption(caption="❌ Geannuleerd.")
            else:
                await query.edit_message_text(text="❌ Geannuleerd.")
        except:
            pass


def extract_title_from_message(text: str) -> str | None:
    """Extract movie/TV title from natural language request using regex patterns"""
    text_clean = text.strip()
    text_lower = text_clean.lower()
    
    # Verwijder punctuatie aan het eind
    text_clean = re.sub(r'[.!?,]+$', '', text_clean)
    text_lower = text_clean.lower()
    
    # Request keywords - check as whole words only (not substrings)
    request_keywords = [
        "kijken", "zoeken", "toevoegen", "vind", "zoek", "wil", 
        "voeg", "toe", "zin", "graag",
        "watch", "add", "request", "find", "search"
    ]
    
    # Check if this looks like a request - using word boundaries to avoid false matches like "Baywatch"
    has_keyword = any(re.search(r'\b' + re.escape(kw) + r'\b', text_lower) for kw in request_keywords)
    
    # Als geen keywords, accepteer als directe titel (bijv. "Predator", "Baywatch")
    if not has_keyword:
        # Validatie: minimaal 2 karakters, geen commando's
        if len(text_clean) >= 2 and not text_lower.startswith("/"):
            # Geen stopwoorden als enkele titel
            stopwords = ["een", "de", "het", "film", "serie", "movie", "a", "the", "hi", "hallo", "hey", "hoi", "dag", "help"]
            if text_lower not in stopwords:
                logger.info(f"✓ Extracted direct title: '{text_clean}' from: '{text}'")
                return text_clean
            else:
                logger.info(f"Direct title is stopword: '{text}'")
        else:
            logger.info(f"Direct title validation failed for: '{text}' (len={len(text_clean)}, starts_with_slash={text_lower.startswith('/')})")
        return None
    
    # Patterns voor titel extractie (van specifiek naar algemeen)
    patterns = [
        # "Zoek [titel]", "vind [titel]", "ik zoek [titel]"
        r"^(?:ik\s+)?(?:zoek|vind|search|find)\s+(?:de\s+)?(?:film\s+|serie\s+)?(.+?)(?:\s+voor\s+me)?$",
        # "Ik wil [titel] kijken", "ik wil [titel] zien"
        r"^ik\s+wil\s+(?:graag\s+)?(.+?)(?:\s+(?:kijken|zien|watch))?$",
        # "Kan je [titel] toevoegen/opzoeken"
        r"^(?:kan|kun)\s+je\s+(.+?)(?:\s+(?:toevoegen|opzoeken|vinden|zoeken))?$",
        # "Voeg [titel] toe"
        r"^voeg\s+(.+?)\s+toe(?:voegen)?$",
        # "[titel] toevoegen"
        r"^(.+?)\s+toevoegen$",
        # "[titel] kijken/zoeken" (simpel patroon)
        r"^(.+?)\s+(?:kijken|zoeken|zien|watch|search)$",
    ]
    
    for pattern in patterns:
        match = re.match(pattern, text_lower, re.IGNORECASE)
        if match:
            title = match.group(1).strip()
            
            # Verwijder common filler woorden aan het eind (ook meerdere keren)
            while True:
                before = title
                title = re.sub(r"\s+(?:kijken|zien|zoeken|opzoeken|vinden|toevoegen|watch|search|voor\s+me)\.?$", "", title, flags=re.IGNORECASE)
                title = title.strip()
                if title == before:  # Geen verandering meer
                    break
            
            # Verwijder punctuatie aan het eind
            title = re.sub(r'[.!?,]+$', '', title).strip()
            
            # Validatie: geen enkele stopwoorden
            stopwords = ["een", "de", "het", "film", "serie", "movie", "a", "the"]
            if title.lower() in stopwords:
                continue
            
            # Validatie: minimaal 2 karakters
            if len(title) >= 2:
                logger.info(f"✓ Extracted title: '{title}' from: '{text}'")
                return title
    
    logger.info(f"Could not extract title from: '{text}'")
    return None


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages with Dutch NLP"""
    text = update.message.text.strip()
    user = update.effective_user

    # Log incoming text message
    log_bot_message("text", user.id, user.username or user.first_name, text, "received")

    pending = context.application.bot_data.setdefault("pending", {})
    state = pending.get(user.id)
    
    # Check if user is approved FIRST - voor ALLE berichten (altijd)
    user_data = get_user_by_telegram_id(user.id)
    
    # Niet geregistreerd of niet goedgekeurd - toon ALTIJD welkomstbericht
    if not user_data or not user_data.get("approved"):
        # Clear any pending state (gebruiker mag niet in flows zitten)
        if user.id in pending:
            pending.pop(user.id, None)
        
        if not user_data:
            # Nieuwe gebruiker - kort bericht over privé systeem
            await update.message.reply_text(
                "🔐 **Privé Media Bot**\n\n"
                "Deze bot is onderdeel van een gesloten media server voor uitgenodigde gebruikers.\n\n"
                "Heb je al een account bij deze Emby server? Dan kun je je Telegram koppelen.\n\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "📝 **Account Koppelen**\n\n"
                "Type dit commando in de chat:\n"
                "`/register`\n\n"
                "_(Kopieer en plak bovenstaande tekst inclusief de / en druk op versturen)_\n\n"
                "**Wat gebeurt er dan?**\n"
                "1️⃣ Je aanvraag wordt naar de beheerder gestuurd\n"
                "2️⃣ De beheerder koppelt je aan je Emby account\n"
                "3️⃣ Je krijgt een bevestiging als je goedgekeurd bent\n"
                "4️⃣ Dan kun je de bot gebruiken!\n\n"
                "⏱️ Dit kan enkele minuten tot uren duren.\n\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "❌ **Geen Emby Account?**\n"
                "Deze bot is niet voor openbaar gebruik. Neem contact op met de beheerder als je toegang wilt tot de Emby server.",
                parse_mode="Markdown"
            )
        else:
            # Al geregistreerd maar nog niet goedgekeurd
            await update.message.reply_text(
                "⏳ **Wachten op Goedkeuring**\n\n"
                f"Je registratie is verstuurd op **{user_data.get('registered_at', 'onbekend')[:10]}**.\n\n"
                "De beheerder ontvangt een notificatie en koppelt je account. "
                "Je krijgt automatisch een bericht zodra je bent goedgekeurd.\n\n"
                "💡 **Let op:** Dit is een privé systeem voor bestaande Emby gebruikers.",
                parse_mode="Markdown"
            )
        return
    
    # MANUAL ENTRY STATES - User manually specifying content details
    if state and state.get("awaiting_manual_title"):
        # User provided title
        manual_title = text.strip()
        
        if len(manual_title) < 2:
            await update.message.reply_text("⚠️ Titel is te kort. Geef een geldige titel.")
            return
        
        media_type = state.get("manual_type", "Movie")
        
        # Store title and move to year
        state["manual_title"] = manual_title
        state.pop("awaiting_manual_title")
        state["awaiting_manual_year"] = True
        
        await update.message.reply_text(
            f"✅ Titel: **{manual_title}**\n\n"
            "📅 In welk **jaar** is deze uitgebracht? (of typ 'skip' om over te slaan)",
            parse_mode="Markdown"
        )
        return
    
    if state and state.get("awaiting_manual_year"):
        # User provided year (or skip)
        year_text = text.strip().lower()
        manual_year = None
        
        if year_text != "skip":
            # Try to parse year
            if year_text.isdigit() and 1900 <= int(year_text) <= 2030:
                manual_year = int(year_text)
            else:
                await update.message.reply_text("⚠️ Ongeldig jaar. Geef een jaar tussen 1900-2030, of typ 'skip'.")
                return
        
        media_type = state.get("manual_type", "Movie")
        state["manual_year"] = manual_year
        state.pop("awaiting_manual_year")
        
        # For series, ask for season. For movies, ask for streaming service
        if media_type == "Series":
            state["awaiting_manual_season"] = True
            await update.message.reply_text(
                "📺 Welk **seizoen** wil je aanvragen?\n\n"
                "Typ een nummer (bijv. '1'), 'all' voor alle seizoenen, of 'skip' om over te slaan.",
                parse_mode="Markdown"
            )
        else:
            state["awaiting_manual_streaming"] = True
            await update.message.reply_text(
                "📡 Op welke **streamingdienst** is of was deze beschikbaar?\n\n"
                "(bijv. Netflix, Disney+, Prime Video)\n\n"
                "Of typ 'skip' om over te slaan.",
                parse_mode="Markdown"
            )
        return
    
    if state and state.get("awaiting_manual_season"):
        # User provided season (series only)
        season_text = text.strip().lower()
        manual_season = None
        
        if season_text != "skip":
            if season_text == "all":
                manual_season = "all"
            elif season_text.isdigit():
                manual_season = int(season_text)
            else:
                await update.message.reply_text("⚠️ Ongeldig seizoen. Typ een nummer, 'all', of 'skip'.")
                return
        
        state["manual_season"] = manual_season
        state.pop("awaiting_manual_season")
        state["awaiting_manual_streaming"] = True
        
        await update.message.reply_text(
            "📡 Op welke **streamingdienst** is of was deze beschikbaar?\n\n"
            "(bijv. Netflix, Disney+, Prime Video)\n\n"
            "Of typ 'skip' om over te slaan.",
            parse_mode="Markdown"
        )
        return
    
    if state and state.get("awaiting_manual_streaming"):
        # User provided streaming service (or skip) - final step
        streaming_text = text.strip()
        manual_streaming = None if streaming_text.lower() == "skip" else streaming_text
        
        # Collect all manual data
        manual_title = state.get("manual_title")
        manual_year = state.get("manual_year")
        manual_season = state.get("manual_season")
        media_type = state.get("manual_type", "Movie")
        
        # Save as manual request
        records = load_requests()
        
        request_entry = {
            "telegram_user_id": user.id,
            "telegram_username": user.username or user.first_name,
            "title": manual_title,
            "content_type": media_type,
            "manual_entry": True,
            "year": manual_year,
            "streaming_service": manual_streaming,
            "requested_at": datetime.now(timezone.utc).isoformat(),
            "notified": False
        }
        
        if media_type == "Series" and manual_season:
            request_entry["season"] = manual_season
        
        records.append(request_entry)
        save_requests(records)
        
        # Build confirmation message
        details = [f"📝 **{manual_title}**"]
        if manual_year:
            details.append(f"📅 {manual_year}")
        if media_type == "Series" and manual_season:
            season_text = "Alle seizoenen" if manual_season == "all" else f"Seizoen {manual_season}"
            details.append(f"📺 {season_text}")
        if manual_streaming:
            details.append(f"📡 {manual_streaming}")
        
        await update.message.reply_text(
            "✅ **Handmatige aanvraag opgeslagen!**\n\n" + "\n".join(details) + 
            "\n\n💡 Een admin zal dit handmatig verwerken en toevoegen.",
            parse_mode="Markdown"
        )
        
        pending.pop(user.id, None)
        return
    
    # STATE 1: Waiting for film/serie choice
    if state and state.get("awaiting_type"):
        text_lower = text.lower()
        title = state.get("title")
        
        # Detect film or serie
        media_type = None
        if any(word in text_lower for word in ["film", "movie"]):
            media_type = "movie"
        elif any(word in text_lower for word in ["serie", "series", "show", "tv"]):
            media_type = "tv"
        else:
            await update.message.reply_text("Ik begrijp niet of je een film of serie bedoelt. Reageer met 'film' of 'serie'.")
            return
        
        # Search in Ombi
        bot: OmbiEmbyBot = context.application.bot_data["bot_instance"]
        await update.message.reply_text(f"🔍 Zoeken naar {title}...")
        results = await bot.ombi_search(title)
        
        if not results:
            await update.message.reply_text("Sorry, ik kon dat niet vinden. Probeer het anders te formuleren.")
            pending.pop(user.id, None)
            return
        
        # Filter results by media type
        filtered = [r for r in results if r.get("mediaType", "").lower() in (media_type, "tv" if media_type == "tv" else "movie")]
        if not filtered:
            filtered = results  # Fallback to all results
        
        # Save results and show first one with poster
        state["results"] = filtered
        state["current_index"] = 0
        state.pop("awaiting_type", None)
        
        msg_id = await show_result(context, update.message.chat_id, filtered[0], 0, len(filtered), None)
        state["last_message_id"] = msg_id
        return
    
    # STATE 2: Waiting for season selection (TV shows)
    if state and state.get("selected"):
        sel = state["selected"]
        title = sel.get("title") or sel.get("name")
        bot: OmbiEmbyBot = context.application.bot_data["bot_instance"]
        
        # Check if content is available in Emby - but VERIFY completeness!
        is_available = sel.get("available", False)
        
        if is_available:
            # Ombi says it's available - but let's verify ALL seasons/episodes are present
            await update.message.reply_text(f"🔍 '{title}' controleren in Emby...")
            
            # Get detailed episode information from Emby
            details = await bot.emby_get_series_details(title)
            
            if details and details.get("episodes"):
                episodes = details["episodes"].get("Items", [])
                episode_count = len(episodes)
                series_data = details.get("series", {})
                item_id = series_data.get("Id")
                
                # Get number of seasons from Ombi or Emby
                ombi_seasons = sel.get("childRequests", [])
                total_requested_episodes = sum(len(req.get("seasonRequests", [])) for req in ombi_seasons)
                
                # Check if we have a reasonable amount of content
                # If requested specific seasons/episodes, verify we have most of them
                if total_requested_episodes > 0:
                    # User requested specific content - check if we have at least 70% of it
                    availability_ratio = episode_count / total_requested_episodes
                    
                    if availability_ratio < 0.7:
                        await update.message.reply_text(
                            f"⚠️ **'{title}' is GEDEELTELIJK beschikbaar in Emby**\n\n"
                            f"📊 Beschikbaar: {episode_count} van ~{total_requested_episodes} aangevraagde afleveringen\n\n"
                            f"💡 Tip: Je kunt alsnog specifieke seizoenen aanvragen. Typ 'all' voor alle seizoenen of een nummer voor een specifiek seizoen.",
                            parse_mode="Markdown"
                        )
                        return
                
                # Sufficient content available - show playback option
                user_data = get_user_by_telegram_id(user.id)
                
                if user_data and user_data.get("approved") and user_data.get("emby_username"):
                    keyboard = InlineKeyboardMarkup([[
                        InlineKeyboardButton("▶️ Start Nu", callback_data=f"play:{item_id}:Series")
                    ]])
                    await update.message.reply_text(
                        f"✅ **'{title}' is beschikbaar in Emby!**\n\n"
                        f"📺 Serie - {episode_count} afleveringen beschikbaar",
                        parse_mode="Markdown",
                        reply_markup=keyboard
                    )
                else:
                    await update.message.reply_text(
                        f"✅ **'{title}' is beschikbaar in Emby!**\n\n"
                        f"📺 Serie - {episode_count} afleveringen beschikbaar\n\n"
                        "💡 Gebruik /register om je account te koppelen voor direct afspelen!",
                        parse_mode="Markdown"
                    )
                pending.pop(user.id, None)
                return
            
            # Series found in Ombi but couldn't get episode details from Emby
            # Fall back to basic availability
            emby_result = await bot.emby_search_smart(title, content_type="Series")
            
            if emby_result and isinstance(emby_result, dict):
                items = emby_result.get("Items") or []
                if items:
                    item_id = items[0].get("Id")
                    user_data = get_user_by_telegram_id(user.id)
                    
                    if user_data and user_data.get("approved") and user_data.get("emby_username"):
                        keyboard = InlineKeyboardMarkup([[
                            InlineKeyboardButton("▶️ Start Nu", callback_data=f"play:{item_id}:Series")
                        ]])
                        await update.message.reply_text(
                            f"✅ **'{title}' is beschikbaar in Emby!**\n\n"
                            f"📺 Serie\n\n"
                            "⚠️ Let op: Ik kon niet verifiëren hoeveel afleveringen beschikbaar zijn.",
                            parse_mode="Markdown",
                            reply_markup=keyboard
                        )
                    else:
                        await update.message.reply_text(
                            f"✅ **'{title}' is beschikbaar in Emby!**\n\n"
                            f"📺 Serie\n\n"
                            "⚠️ Let op: Ik kon niet verifiëren hoeveel afleveringen beschikbaar zijn.\n\n"
                            "💡 Gebruik /register om je account te koppelen voor direct afspelen!",
                            parse_mode="Markdown"
                        )
                    pending.pop(user.id, None)
                    return
            
            # Emby ID niet gevonden, maar Ombi zegt dat het beschikbaar is
            await update.message.reply_text(
                f"⚠️ **'{title}' staat als beschikbaar in Ombi**\n\n"
                "Maar ik kon het niet vinden in Emby. Probeer handmatig te zoeken of vraag het opnieuw aan.",
                parse_mode="Markdown"
            )
            pending.pop(user.id, None)
            return
        
        # Nog NIET in Emby - aanvragen bij Ombi
        if text.lower() == "all":
            # Request all seasons
            await update.message.reply_text(f"'{title}' staat nog niet in Emby. Aanvragen bij Ombi...")
            resp = await bot.ombi_request(sel, media_type="tv", requested_seasons=None)
            if resp:
                records = load_requests()
                records.append({
                    "telegram_user_id": user.id,
                    "telegram_username": user.username,
                    "title": title,
                    "content_type": "Series",
                    "ombi_response": resp,
                    "requested_at": datetime.now(timezone.utc).isoformat(),
                    "notified": False
                })
                save_requests(records)
                await update.message.reply_text("✅ Serie aangevraagd! Ik laat je weten als het in Emby staat.")
            else:
                await update.message.reply_text("❌ Serie aanvragen bij Ombi mislukt.")
            pending.pop(user.id, None)
            return

        if text.isdigit():
            season_num = int(text)
            await update.message.reply_text(f"Aanvragen van seizoen {season_num} van '{title}' bij Ombi...")
            resp = await bot.ombi_request(sel, media_type="tv", requested_seasons=[season_num])
            if resp:
                records = load_requests()
                records.append({
                    "telegram_user_id": user.id,
                    "telegram_username": user.username,
                    "title": f"{title} - S{season_num}",
                    "content_type": "Series",
                    "ombi_response": resp,
                    "requested_at": datetime.now(timezone.utc).isoformat(),
                    "notified": False
                })
                save_requests(records)
                await update.message.reply_text("✅ Seizoen aangevraagd! Ik laat je weten als het in Emby staat.")
            else:
                await update.message.reply_text("❌ Seizoen aanvragen bij Ombi mislukt.")
            pending.pop(user.id, None)
            return
    
    # NEW REQUEST: Extract title from message (regex)
    title = extract_title_from_message(text)
    
    if title:
        # Zoek direct in Ombi om te zien wat voor resultaten we hebben
        bot: OmbiEmbyBot = context.application.bot_data["bot_instance"]
        await update.message.reply_text(f"🔍 Zoeken naar '{title}'...")
        results = await bot.ombi_search(title)
        
        if not results:
            # Geen resultaten - bied manual entry aan
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✍️ Handmatig opgeven", callback_data="manual_entry")],
                [InlineKeyboardButton("❌ Annuleren", callback_data="cancel")]
            ])
            
            await update.message.reply_text(
                f"❌ Geen resultaten gevonden voor '{title}'.\n\n"
                "Wil je de gegevens handmatig opgeven?",
                reply_markup=keyboard
            )
            
            # Store original search title for context
            pending[user.id] = {"original_search": title}
            return
        
        # Analyseer welke types in de resultaten zitten
        has_movies = any(r.get("mediaType", "").lower() in ("movie",) for r in results)
        has_series = any(r.get("mediaType", "").lower() in ("tv", "series") for r in results)
        
        if has_movies and has_series:
            # Beide types gevonden - vraag gebruiker
            pending[user.id] = {"title": title, "awaiting_type": True}
            await update.message.reply_text(
                f"🎬 Gevonden titel: **{title}**\n\n"
                "Ik vond zowel films als series met deze naam.\n"
                "Zoek je een **film** of een **serie**?",
                parse_mode="Markdown"
            )
            return
        elif has_movies:
            # Alleen films - filter en toon direct
            filtered = [r for r in results if r.get("mediaType", "").lower() == "movie"]
        elif has_series:
            # Alleen series - filter en toon direct
            filtered = [r for r in results if r.get("mediaType", "").lower() in ("tv", "series")]
        else:
            # Onbekend type - toon alles
            filtered = results
        
        # Toon eerste resultaat direct
        pending[user.id] = {
            "results": filtered,
            "current_index": 0
        }
        msg_id = await show_result(context, update.message.chat_id, filtered[0], 0, len(filtered), None)
        pending[user.id]["last_message_id"] = msg_id
        return
    
    # Casual replies (Nederlands)
    low = text.lower()
    if any(g in low for g in ("hi", "hallo", "hey", "hoi", "dag", "goedemorgen", "goedemiddag", "goedenavond")):
        await update.message.reply_text(f"Hey {update.effective_user.first_name}! Stuur me de titel van een film of serie die je wilt kijken.")
        return
    if "dank" in low or "bedankt" in low or "thanks" in low:
        await update.message.reply_text("Graag gedaan! Veel kijkplezier! 🎬")
        return
    if "help" in low or "wat kun je" in low or "hoe werkt" in low:
        await update.message.reply_text("Stuur me alleen de titel van een film of serie!\n\nVoorbeelden:\n• Inception\n• Breaking Bad\n• The Matrix\n\nOf gebruik /help voor meer info.")
        return
    
    # Standaard onduidelijk bericht
    await update.message.reply_text("🤔 Ik begreep dat niet helemaal.\n\n💡 Stuur me alleen de titel van een film of serie!\n\nVoorbeelden:\n• Predator\n• Inception\n• Stranger Things\n\nOf gebruik /help voor hulp.")


async def send_pending_messages(application):
    """Check en verstuur pending messages uit de webinterface"""
    try:
        messages = load_pending_messages()
        if not messages:
            return
        
        updated_messages = []
        for msg in messages:
            if msg.get('sent'):
                continue
            
            telegram_id = msg.get('telegram_user_id')
            message_text = msg.get('message')
            
            if not telegram_id or not message_text:
                continue
            
            try:
                await application.bot.send_message(
                    chat_id=telegram_id,
                    text=message_text,
                    parse_mode="Markdown"
                )
                msg['sent'] = True
                msg['sent_at'] = datetime.now(timezone.utc).isoformat()
                
                # Log manual message
                user_data = get_user_by_telegram_id(telegram_id)
                username = user_data.get('telegram_username') or user_data.get('telegram_first_name') if user_data else str(telegram_id)
                log_bot_message("manual", telegram_id, username, message_text, "sent")
                
                logger.info(f"✅ Sent manual message to user {telegram_id}")
            except Exception as e:
                logger.error(f"Failed to send manual message to {telegram_id}: {e}")
                # Keep in queue for retry
                updated_messages.append(msg)
        
        # Clean up sent messages older than 24 hours
        cutoff = datetime.now(timezone.utc) - timedelta(days=1)
        messages = [m for m in messages if not m.get('sent') or 
                   (m.get('sent_at') and datetime.fromisoformat(m['sent_at'].replace('Z', '+00:00')) > cutoff)]
        
        save_pending_messages(messages)
    except Exception as e:
        logger.error(f"Error processing pending messages: {e}")


async def background_poller(application):
    bot: OmbiEmbyBot = application.bot_data["bot_instance"]
    while True:
        try:
            # Check en verstuur pending messages uit webinterface
            await send_pending_messages(application)
            
            records = load_requests()
            changed = False
            
            # Group notifications by user and series to prevent spam
            user_notifications = {}  # {user_id: {series_name: [episodes]}}
            
            for r in records:
                if r.get("notified"):
                    continue
                
                title = r.get("title")
                ctype = r.get("content_type") or "Movie"
                ombi_response = r.get("ombi_response")
                uid = r.get("telegram_user_id")
                
                # Check voor handmatige entries - die hebben geen Ombi request ID
                if r.get("manual_entry"):
                    logger.info(f"Skipping manual entry: {title}")
                    continue
                
                # Haal request ID uit ombi_response
                if not ombi_response:
                    logger.warning(f"No ombi_response for request: {title}")
                    continue
                
                request_id = ombi_response.get("requestId") or ombi_response.get("id")
                if not request_id:
                    logger.warning(f"No request ID in ombi_response for: {title}")
                    logger.debug(f"ombi_response keys: {list(ombi_response.keys())}")
                    continue
                
                # Check Ombi voor actuele status
                ombi_status = await bot.ombi_get_request_by_id(request_id, media_type=ctype.lower())
                
                if not ombi_status:
                    logger.warning(f"Could not fetch Ombi status for request {request_id} ('{title}')")
                    continue
                
                # Voor series: controleer of ALLE AANGEVRAAGDE seizoenen beschikbaar zijn
                if ctype == "Series":
                    # Haal requested seasons data uit Ombi
                    child_requests = ombi_status.get("childRequests", [])
                    all_season_requests = []
                    
                    logger.debug(f"[{title}] childRequests found: {len(child_requests)}")
                    
                    for child in child_requests:
                        season_requests = child.get("seasonRequests", [])
                        all_season_requests.extend(season_requests)
                        logger.debug(f"[{title}] Added {len(season_requests)} season requests from child")
                    
                    logger.info(f"[{title}] Total season_requests: {len(all_season_requests)}")
                    
                    # Check of ALLE aangevraagde seizoenen beschikbaar zijn
                    if all_season_requests:
                        all_seasons_available = True
                        unavailable_seasons = []
                        
                        for season in all_season_requests:
                            season_num = season.get("seasonNumber")
                            episodes = season.get("episodes", [])
                            
                            # Check episode-level availability (seasonAvailable is niet betrouwbaar in Ombi)
                            total_episodes = len(episodes)
                            available_episodes = sum(1 for ep in episodes if ep.get("available", False))
                            
                            logger.info(f"[{title}] Season {season_num}: {available_episodes}/{total_episodes} episodes available")
                            
                            # Seizoen is beschikbaar als ALLE episodes beschikbaar zijn
                            if total_episodes > 0 and available_episodes < total_episodes:
                                all_seasons_available = False
                                unavailable_seasons.append(season_num)
                                logger.debug(f"[{title}] Season {season_num}: NOT fully available")
                            else:
                                logger.debug(f"[{title}] Season {season_num}: FULLY available")
                        
                        if not all_seasons_available:
                            logger.info(f"⏳ '{title}' (Request {request_id}) - Wacht op seizoen(en): {unavailable_seasons}")
                            continue
                        
                        logger.info(f"✅ '{title}' (Request {request_id}) - ALLE aangevraagde seizoenen beschikbaar volgens Ombi!")
                    else:
                        # Geen season details - check het algemene available veld
                        logger.warning(f"[{title}] No season_requests found! Checking parent available field")
                        if not ombi_status.get("available", False):
                            logger.debug(f"'{title}' nog niet beschikbaar volgens Ombi")
                            continue
                        logger.info(f"✅ '{title}' is beschikbaar volgens Ombi!")
                else:
                    # Voor movies: check het normale available veld
                    is_available = ombi_status.get("available", False)
                    
                    if not is_available:
                        logger.debug(f"'{title}' nog niet beschikbaar volgens Ombi")
                        continue
                    
                    logger.info(f"✅ '{title}' is beschikbaar volgens Ombi!")
                
                # Content is available! Nu verificatie doen
                # Voor series: check episode counts PER SEIZOEN
                if ctype == "Series":
                    # all_season_requests is al gevuld hierboven
                    
                    if all_season_requests:
                        # Verifieer per-seizoen in Emby
                        is_complete, series_emby_id, verify_msg = await bot.emby_verify_series_seasons(
                            title, 
                            all_season_requests
                        )
                        
                        if not is_complete:
                            logger.info(f"'{title}' nog niet compleet: {verify_msg}")
                            continue  # Wacht tot alle seizoenen voldoende episodes hebben
                        
                        item_id = series_emby_id
                        logger.info(f"'{title}' verificatie geslaagd - alle seizoenen compleet!")
                    else:
                        # Geen season details in Ombi - fallback naar Emby search
                        logger.info(f"Geen seizoen data in Ombi voor '{title}', gebruik Emby search")
                        emby_res = await bot.emby_search_smart(title, content_type="Series")
                        if emby_res and emby_res.get("Items"):
                            item_id = emby_res["Items"][0].get("Id")
                        else:
                            logger.warning(f"Kon geen Emby ID vinden voor '{title}'")
                            continue
                else:
                    # Movie - vertrouw volledig op Ombi available status
                    logger.info(f"Movie '{title}' beschikbaar, zoek Emby ID")
                    emby_res = await bot.emby_search_smart(title, content_type="Movie")
                    if emby_res and emby_res.get("Items"):
                        item_id = emby_res["Items"][0].get("Id")
                    else:
                        logger.warning(f"Kon geen Emby ID vinden voor movie '{title}'")
                        continue
                
                # Content is beschikbaar en geverifieerd - markeer voor notificatie
                r["notified"] = True
                changed = True
                
                # Group by user and series
                if uid not in user_notifications:
                    user_notifications[uid] = {}
                
                # Extract base series name (remove season info like "- S01")
                base_title = re.sub(r'\s*-\s*S\d+\s*$', '', title)
                
                if base_title not in user_notifications[uid]:
                    user_notifications[uid][base_title] = {
                        "type": ctype,
                        "item_id": item_id,
                        "episodes": []
                    }
                
                # Extract season number if present
                season_match = re.search(r'S(\d+)', title)
                if season_match:
                    user_notifications[uid][base_title]["episodes"].append(season_match.group(1))
            
            # Send consolidated notifications
            for uid, series_dict in user_notifications.items():
                user = get_user_by_telegram_id(uid)
                
                for series_title, data in series_dict.items():
                    ctype = data["type"]
                    item_id = data["item_id"]
                    episodes = data["episodes"]
                    
                    try:
                        # Create inline keyboard with playback button
                        keyboard = None
                        if user and user.get("approved") and user.get("emby_username"):
                            keyboard = InlineKeyboardMarkup([[
                                InlineKeyboardButton("▶️ Start Nu", callback_data=f"play:{item_id}:{ctype}")
                            ]])
                        
                        # Build message based on whether it's multiple episodes or single
                        if ctype == "Series" and episodes:
                            if len(episodes) > 1:
                                seasons_text = ", ".join([f"S{s}" for s in sorted(set(episodes))])
                                message = (
                                    f"🎉 **'{series_title}' seizoenen beschikbaar in Emby!**\n\n"
                                    f"📺 Nieuwe seizoenen: {seasons_text}"
                                )
                            else:
                                message = (
                                    f"🎉 **'{series_title}' is nu beschikbaar in Emby!**\n\n"
                                    f"📺 Serie - Seizoen {episodes[0]}"
                                )
                        else:
                            message = (
                                f"🎉 **'{series_title}' is nu beschikbaar in Emby!**\n\n"
                                f"Type: {'🎬 Film' if ctype == 'Movie' else '📺 Serie'}"
                            )
                        
                        if keyboard:
                            await application.bot.send_message(
                                chat_id=uid, 
                                text=message,
                                parse_mode="Markdown",
                                reply_markup=keyboard
                            )
                            username = user.get("telegram_username") or user.get("emby_username") or str(uid)
                            log_bot_message("notification", uid, username, message, "sent")
                        else:
                            full_message = message + "\n\n💡 Gebruik /register om je account te koppelen voor direct afspelen!"
                            await application.bot.send_message(
                                chat_id=uid, 
                                text=full_message,
                                parse_mode="Markdown"
                            )
                            username = user.get("telegram_username") if user else str(uid)
                            log_bot_message("notification", uid, username, full_message, "sent")
                    except Exception:
                        logger.exception("Failed to send notification to %s", uid)
            
            if changed:
                save_requests(records)
            
            # Check voor pending approval notifications (van web UI)
            users = load_users()
            users_changed = False
            for user in users:
                if user.get("needs_notification") and user.get("approved"):
                    telegram_id = user.get("telegram_user_id")
                    emby_username = user.get("emby_username")
                    
                    try:
                        # Eerste bericht: goedkeuring
                        await application.bot.send_message(
                            chat_id=telegram_id,
                            text=f"🎉 **Je account is goedgekeurd!**\n\n"
                                 f"Je bent gekoppeld aan Emby gebruiker: **{emby_username}**\n\n"
                                 f"Je kunt nu films en series aanvragen!",
                            parse_mode="Markdown"
                        )
                        
                        # Wacht even voor leesbaarheid
                        await asyncio.sleep(1)
                        
                        # Tweede bericht: Welkom met features en hoe het werkt
                        await application.bot.send_message(
                            chat_id=telegram_id,
                            text=f"🤖 Welkom {user.get('telegram_first_name')} bij de Emby Bot!\n\n"
                                 "Fijn dat je er bent! Deze bot maakt het super makkelijk om films en series aan te vragen en af te spelen via Emby.\n\n"
                                 "📚 **Wat kun je met deze bot?**\n"
                                 "• 🎬 Films en series aanvragen\n"
                                 "• ▶️ Direct afspelen op je apparaten\n"
                                 "• 📺 Seizoenen en afleveringen kiezen\n"
                                 "• 🔔 Automatische notificaties ontvangen\n"
                                 "• 🆕 Update alerts voor nieuwe afleveringen\n\n"
                                 "💡 **Hoe werkt het?**\n"
                                 "Heel simpel - type gewoon de titel:\n"
                                 "• \"Dune\"\n"
                                 "• \"Breaking Bad\"\n"
                                 "• \"The Matrix\"\n\n"
                                 "De bot zoekt automatisch en toont resultaten met knoppen. Als content al beschikbaar is, kun je meteen afspelen!\n\n"
                                 "🎯 **Series Afspelen:**\n"
                                 "Voor series kun je exact kiezen:\n"
                                 "1️⃣ Kies seizoen uit het menu\n"
                                 "2️⃣ Kies aflevering\n"
                                 "3️⃣ Selecteer je apparaat\n"
                                 "4️⃣ Kijken maar! 🍿\n\n"
                                 "📱 **Handige Commands:**\n"
                                 "/help - Volledig overzicht\n"
                                 "/status - Je aanvragen bekijken\n"
                                 "/notifications - Aflevering alerts aan/uit",
                            parse_mode="Markdown"
                        )
                        
                        # Wacht 2 seconden
                        await asyncio.sleep(2)
                        
                        # Derde bericht: Notificaties en commands
                        await application.bot.send_message(
                            chat_id=telegram_id,
                            text="🔔 **Automatische Updates**\n\n"
                                 "Je krijgt een bericht wanneer:\n"
                                 "✅ Content beschikbaar is in Emby\n"
                                 "🆕 Er nieuwe afleveringen zijn van series die je kijkt\n\n"
                                 "_Notificaties uitzetten? Gebruik /notifications_\n\n"
                                 "─────────────\n\n"
                                 "⚙️ **Handige Commands:**\n\n"
                                 "/help → Uitgebreide handleiding\n"
                                 "/status → Bekijk je aanvragen\n"
                                 "/recent → Laatst toegevoegd\n"
                                 "/myshows → Jouw series\n\n"
                                 "─────────────\n\n"
                                 "🎬 **Start nu:** Stuur me een titel!\n\n"
                                 "_Veel kijkplezier!_ 🍿",
                            parse_mode="Markdown"
                        )
                        
                        user["needs_notification"] = False
                        users_changed = True
                        logger.info(f"Approval notificatie en handleiding gestuurd naar gebruiker {telegram_id}")
                    except Exception as e:
                        logger.error(f"Kon approval notificatie niet sturen naar {telegram_id}: {e}")
            
            if users_changed:
                save_users(users)
            
            # Check voor nieuwe afleveringen van series die gebruikers aan het kijken zijn
            episode_notifs = load_episode_notifications()
            episode_notifs_changed = False
            
            # Voor elke goedgekeurde gebruiker met Emby account
            for user in users:
                if not user.get("approved") or not user.get("emby_username"):
                    continue
                
                # Check of gebruiker episode notificaties aan heeft (default True)
                if not user.get("episode_notifications", True):
                    continue
                
                telegram_id = user.get("telegram_user_id")
                emby_username = user.get("emby_username")
                
                try:
                    # Get Emby user ID
                    emby_user = await bot.emby_get_user_by_name(emby_username)
                    if not emby_user:
                        continue
                    
                    emby_user_id = emby_user.get("Id")
                    
                    # Get series this user is watching
                    watching_series = await bot.emby_get_user_continue_watching(emby_user_id)
                    
                    for series in watching_series:
                        series_id = series.get("id")
                        series_name = series.get("name")
                        
                        # Check for latest episode (within last 48 hours)
                        latest_ep = await bot.emby_get_latest_episode(series_id, max_age_hours=48)
                        
                        if latest_ep:
                            episode_id = latest_ep.get("id")
                            
                            # Check if we already notified this user about this episode
                            notif_key = f"{telegram_id}:{episode_id}"
                            
                            if notif_key not in episode_notifs:
                                # Send notification
                                ep_name = latest_ep.get("name")
                                season = latest_ep.get("season")
                                episode_num = latest_ep.get("episode")
                                overview = latest_ep.get("overview", "")[:200]
                                
                                message = (
                                    f"📺 **Nieuwe aflevering beschikbaar!**\n\n"
                                    f"**{series_name}**\n"
                                    f"S{season}E{episode_num}: {ep_name}\n\n"
                                    f"{overview}{'...' if len(overview) >= 200 else ''}"
                                )
                                
                                # Add play button
                                keyboard = InlineKeyboardMarkup([[
                                    InlineKeyboardButton("▶️ Nu Afspelen", callback_data=f"episode:{episode_id}")
                                ]])
                                
                                try:
                                    await application.bot.send_message(
                                        chat_id=telegram_id,
                                        text=message,
                                        parse_mode="Markdown",
                                        reply_markup=keyboard
                                    )
                                    
                                    # Mark as notified
                                    episode_notifs[notif_key] = {
                                        "notified_at": datetime.now(timezone.utc).isoformat(),
                                        "series_name": series_name,
                                        "episode_name": ep_name,
                                        "season": season,
                                        "episode": episode_num
                                    }
                                    episode_notifs_changed = True
                                    logger.info(f"Sent new episode notification to user {telegram_id}: {series_name} S{season}E{episode_num}")
                                except Exception as e:
                                    logger.error(f"Failed to send episode notification to {telegram_id}: {e}")
                
                except Exception as e:
                    logger.error(f"Error checking episodes for user {telegram_id}: {e}")
            
            if episode_notifs_changed:
                save_episode_notifications(episode_notifs)
                
        except Exception:
            logger.exception("Error in poller")
        await asyncio.sleep(bot.poll_interval)


def load_config(path: str = "config.yaml") -> dict:
    """Load config, creating config/config.yaml if needed"""
    import shutil
    
    # Always use config/ directory for consistency
    config_path = "config/config.yaml"
    
    # Auto-create from example if missing
    if not os.path.exists(config_path):
        try:
            os.makedirs("config", exist_ok=True)
            if os.path.exists("config.example.yaml"):
                shutil.copyfile("config.example.yaml", config_path)
                print(f"✓ Created {config_path} from config.example.yaml")
            else:
                # Create minimal placeholder
                with open(config_path, "w", encoding="utf-8") as f:
                    f.write(
                        "admin_telegram_id: 0\n"
                        "emby_api_key: \"\"\n"
                        "emby_url: \"http://127.0.0.1:8096\"\n"
                        "ombi_api_key: \"\"\n"
                        "ombi_api_key_header: ApiKey\n"
                        "ombi_url: \"http://127.0.0.1:3579\"\n"
                        "poll_interval_seconds: 60\n"
                        "telegram_token: \"\"\n"
                        "web_ui_port: 5000\n"
                    )
                print(f"✓ Created placeholder {config_path}")
        except Exception as e:
            print(f"⚠ Failed to create {config_path}: {e}")
    
    # Load config from config/ directory
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    
    return {}


def main():
    config = load_config()
    token = config.get("telegram_token") or os.environ.get("TELEGRAM_TOKEN")
    # Check for missing or placeholder tokens
    if not token or token in ["YOUR_TELEGRAM_BOT_TOKEN", ""]:
        print("⚠️  Telegram token missing or placeholder. Set telegram_token in config.yaml or TELEGRAM_TOKEN env var.")
        print("⚠️  Bot will not start until token is configured.")
        # Sleep indefinitely to prevent supervisor restart loop
        import time
        while True:
            time.sleep(3600)

    bot_instance = OmbiEmbyBot(config)

    # MONKEY PATCH: Auto-log all replies
    from telegram import Message
    from telegram import Bot
    from functools import wraps
    
    # Wrap Message.reply_text
    original_reply_text = Message.reply_text
    
    @wraps(original_reply_text)
    async def logged_reply_text(self, *args, **kwargs):
        # Call original
        result = await original_reply_text(self, *args, **kwargs)
        # Log it
        try:
            user = self.from_user or self.chat
            text = args[0] if args else kwargs.get('text', '')
            username = user.username or user.first_name if hasattr(user, 'first_name') else str(user.id)
            # Strip markdown for logging
            clean_text = text.replace("**", "").replace("__", "").replace("*", "").replace("_", "")
            log_bot_message("text", user.id, username, clean_text[:500], "sent")
        except Exception as e:
            logger.warning(f"Failed to log reply: {e}")
        return result
    
    Message.reply_text = logged_reply_text
    
    # Wrap Bot.send_message
    original_send_message = Bot.send_message
    
    @wraps(original_send_message)
    async def logged_send_message(self, chat_id, text, *args, **kwargs):
        # Call original
        result = await original_send_message(self, chat_id, text, *args, **kwargs)
        # Log it
        try:
            # Get username from user data if possible
            user_data = get_user_by_telegram_id(chat_id)
            username = user_data.get('telegram_username') if user_data else str(chat_id)
            # Strip markdown for logging
            clean_text = text.replace("**", "").replace("__", "").replace("*", "").replace("_", "")
            log_bot_message("text", chat_id, username, clean_text[:500], "sent")
        except Exception as e:
            logger.warning(f"Failed to log send_message: {e}")
        return result
    
    Bot.send_message = logged_send_message
    
    app = ApplicationBuilder().token(token).build()
    app.bot_data["bot_instance"] = bot_instance
    app.bot_data["config"] = config  # Voor access tot admin_telegram_id

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("request", request_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("recent", recent_command))
    app.add_handler(CommandHandler("myshows", myshows_command))
    app.add_handler(CommandHandler("updates", updates_command))
    app.add_handler(CommandHandler("register", register_command))
    app.add_handler(CommandHandler("notifications", notifications_command))
    app.add_handler(CommandHandler("approve", approve_command))
    app.add_handler(CommandHandler("approve", approve_command))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    async def on_startup(application):
        await bot_instance.ensure_session()
        application.create_task(background_poller(application))

    app.post_init = on_startup

    print("Starting bot — press Ctrl-C to stop")
    app.run_polling()


if __name__ == "__main__":
    main()
