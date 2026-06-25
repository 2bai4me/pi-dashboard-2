"""GitHub-Service (User-Direktive 24.06.2026).

Haelt eine kleine In-Memory Cache der GitHub-API-Responses (1 Stunde),
damit nicht bei jedem Klick auf eine Kachel eine neue HTTP-Request entsteht.

Unterstuetzt:
- Repo-Info (Stars, Forks, License, Default-Branch, Updated-At, ...)
- Cache mit TTL (default 1h)
- Fehlertolerant (API-Limit, 404, Netzwerkfehler)
- Optional mit GitHub-Token (60 req/h ohne, 5000 mit)
"""
from __future__ import annotations

import json as _json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("pi-dashboard-2.github")


# In-Memory Cache (1 Stunde TTL)
_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_CACHE_TTL_SEC = 3600.0


def _get_cached(url: str) -> Optional[Dict[str, Any]]:
    """Holt eine URL aus dem Cache (None wenn abgelaufen)."""
    entry = _CACHE.get(url)
    if not entry:
        return None
    expires_at, data = entry
    if time.time() > expires_at:
        del _CACHE[url]
        return None
    return data


def _set_cached(url: str, data: Dict[str, Any]) -> None:
    """Setzt einen Cache-Eintrag (TTL 1 Stunde)."""
    _CACHE[url] = (time.time() + _CACHE_TTL_SEC, data)


def _get_github_token() -> Optional[str]:
    """Holt den GitHub-Token (optional, aus ENV)."""
    return os.environ.get("GITHUB_TOKEN") or None


def _format_stars(n: int) -> str:
    """Formatiert Star-Count (1030 -> '1k', 1234 -> '1.2k')."""
    if n < 1000:
        return str(n)
    if n < 10000:
        return f"{n / 1000:.1f}k"
    if n < 1000000:
        return f"{int(n / 1000)}k"
    return f"{n / 1000000:.1f}M"


def fetch_repo_info(github_url: str, use_cache: bool = True) -> Dict[str, Any]:
    """Holt Repo-Infos von der GitHub-API.

    Args:
        github_url: z.B. "https://github.com/2bai4me/pi-dashboard-2"
        use_cache: Cache nutzen (default: True)

    Returns:
        Dict mit allen Feldern oder leeres Dict bei Fehler
    """
    if not github_url:
        return {}

    # Normalisiere URL
    github_url = github_url.rstrip("/").removesuffix(".git")
    api_url = github_url.replace("https://github.com/", "https://api.github.com/repos/")

    # Cache-Lookup
    if use_cache:
        cached = _get_cached(api_url)
        if cached is not None:
            return cached

    # API-Request
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "PI-Dashboard-2.0",
    }
    token = _get_github_token()
    if token:
        headers["Authorization"] = f"token {token}"

    try:
        req = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read()
            data = _json.loads(raw)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            logger.warning(f"GitHub 404: {github_url}")
            return {"error": "not_found", "url": github_url}
        if e.code == 403:
            logger.warning(f"GitHub 403 (rate limit?): {github_url}")
            return {"error": "rate_limited", "url": github_url}
        logger.warning(f"GitHub HTTP {e.code}: {github_url}")
        return {"error": f"http_{e.code}", "url": github_url}
    except (urllib.error.URLError, TimeoutError, _json.JSONDecodeError, OSError) as e:
        logger.warning(f"GitHub network error for {github_url}: {e}")
        return {"error": "network", "url": github_url}

    if "message" in data and isinstance(data["message"], str) and "Not Found" in data["message"]:
        return {"error": "not_found", "url": github_url}

    # Standardisierte Felder extrahieren
    result = {
        "url": github_url,
        "full_name": data.get("full_name", ""),
        "description": (data.get("description") or "")[:500],
        "stars": data.get("stargazers_count", 0),
        "stars_label": _format_stars(data.get("stargazers_count", 0)),
        "forks": data.get("forks_count", 0),
        "forks_label": _format_stars(data.get("forks_count", 0)),
        "watchers": data.get("watchers_count", 0),
        "open_issues": data.get("open_issues_count", 0),
        "default_branch": data.get("default_branch", "main"),
        "language": data.get("language") or "unknown",
        "size_kb": data.get("size", 0),
        "license": (data.get("license") or {}).get("spdx_id", "none") if data.get("license") else "none",
        "topics": data.get("topics", []),
        "visibility": data.get("visibility", "public"),
        "private": data.get("private", False),
        "archived": data.get("archived", False),
        "disabled": data.get("disabled", False),
        "created_at": data.get("created_at", ""),
        "updated_at": data.get("updated_at", ""),
        "pushed_at": data.get("pushed_at", ""),
        "fetched_at": _iso_now(),
    }

    # Cache (1 Stunde)
    if use_cache:
        _set_cached(api_url, result)

    return result


def _iso_now() -> str:
    """Aktuelle Zeit als ISO-String."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def update_project_from_github(db, project_id: str) -> Dict[str, Any]:
    """Holt die neuesten GitHub-Daten und aktualisiert das Project.

    Returns:
        Dict mit update_info (gefetchte Felder, success-Status)
    """
    from app.models.project import Project
    from app.models.history import TaskHistory
    from datetime import datetime, timezone
    from sqlalchemy import select
    import json

    p = db.get(Project, project_id)
    if not p:
        return {"success": False, "error": "project_not_found"}

    if not p.github_url:
        return {"success": False, "error": "no_github_url"}

    # Cache umgehen fuer explizites Update
    data = fetch_repo_info(p.github_url, use_cache=False)
    if "error" in data:
        return {"success": False, **data}

    # Project aktualisieren
    p.github_stars = data.get("stars", 0)
    p.github_forks = data.get("forks", 0)
    p.github_default_branch = data.get("default_branch", "main")
    p.github_size_kb = data.get("size_kb", 0)
    p.github_license = data.get("license", "none")
    p.github_topics = json.dumps(data.get("topics", []))
    p.github_description = data.get("description", "")
    p.github_stars_label = data.get("stars_label", "0")
    p.github_language = data.get("language", "unknown")
    p.github_fetched_at = datetime.now(timezone.utc)

    if data.get("updated_at"):
        try:
            p.github_updated_at = datetime.fromisoformat(
                data["updated_at"].replace("Z", "+00:00")
            )
        except (ValueError, TypeError):
            pass

    # History-Eintrag (kein Task-Bezug, da Project-bezogen)
    h = TaskHistory(
        task_id=project_id,  # Pseudo-Referenz (project_id statt task_id)
        event="project_github_updated",
        agent="system",
        details={
            "kind": "project_github_update",
            "project_id": project_id,
            "project_name": p.name,
            "stars": data.get("stars", 0),
            "forks": data.get("forks", 0),
            "default_branch": data.get("default_branch", "main"),
            "language": data.get("language", "unknown"),
        },
    )
    db.add(h)
    db.commit()

    return {
        "success": True,
        "project_id": project_id,
        "project_name": p.name,
        "github_url": p.github_url,
        "fetched_at": p.github_fetched_at.isoformat(),
        "stars": p.github_stars,
        "forks": p.github_forks,
        "default_branch": p.github_default_branch,
        "language": p.github_language,
        "size_kb": p.github_size_kb,
        "license": p.github_license,
        "topics": data.get("topics", []),
    }


def clear_cache() -> int:
    """Leert den Cache. Returns Anzahl geloeschter Eintraege."""
    global _CACHE
    count = len(_CACHE)
    _CACHE = {}
    return count


def get_cache_stats() -> Dict[str, Any]:
    """Cache-Statistiken."""
    return {
        "entries": len(_CACHE),
        "ttl_sec": _CACHE_TTL_SEC,
        "urls": list(_CACHE.keys())[:10],
    }
