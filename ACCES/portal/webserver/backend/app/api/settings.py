from __future__ import annotations

import json
import time

import httpx
from fastapi import APIRouter

from app.core.config import get_settings
from app.core.logging import get_logger
from app.jobqueue import default_queue
from app.models.job import JobType

router = APIRouter(prefix="/api/settings", tags=["settings"])
settings = get_settings()
logger = get_logger("settings_api")

_SERVER_INFO_TTL = 3600  # IP/hosting rarely changes — avoid hammering the geolocation API
_server_info_cache: dict | None = None
_server_info_cached_at: float = 0.0


def _status_path():
    return settings.storage_root / "tool_status.json"


@router.post("/tools/check")
def trigger_tool_check():
    """Section 7: the "APK-Lab Environment" status check must run on the
    worker (it has the Android tooling; the API container deliberately
    does not), so this enqueues a job rather than shelling out here."""
    job_id = default_queue.enqueue(JobType.TOOL_CHECK, None, {})
    return {"job_id": job_id}


@router.get("/tools")
def tool_status():
    path = _status_path()
    if not path.exists():
        return {"tools": [], "checked_at": None, "message": "Run POST /api/settings/tools/check first"}
    return json.loads(path.read_text())


@router.get("/server-info")
def server_info():
    """Where this server is actually hosted — public IP, region/city,
    provider and country (for the flag) — detected server-side via IP
    geolocation so it reflects the server's own location, not the
    visiting browser's. Cached in-process for an hour since this barely
    ever changes and the lookup hits a free third-party rate-limited API."""
    global _server_info_cache, _server_info_cached_at

    now = time.time()
    if _server_info_cache and (now - _server_info_cached_at) < _SERVER_INFO_TTL:
        return _server_info_cache

    try:
        resp = httpx.get(
            "http://ip-api.com/json/?fields=status,message,country,countryCode,regionName,city,isp,query",
            timeout=5.0,
        )
        data = resp.json()
        if data.get("status") != "success":
            raise ValueError(data.get("message", "lookup failed"))
        result = {
            "ok": True,
            "ip": data.get("query", ""),
            "country": data.get("country", ""),
            "country_code": data.get("countryCode", ""),
            "region": data.get("regionName", ""),
            "city": data.get("city", ""),
            "isp": data.get("isp", ""),
        }
    except Exception as exc:
        logger.warning("server-info lookup failed: %s", exc)
        result = {"ok": False, "ip": "", "country": "", "country_code": "", "region": "", "city": "", "isp": ""}

    _server_info_cache = result
    _server_info_cached_at = now
    return result
