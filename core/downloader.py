"""Online driver download logic — supports vendor direct URLs and custom CDN."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

from core.logger import logger

try:
    import requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False
    logger.error("requests module not available -- online mode disabled")


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


def load_settings() -> dict:
    settings_path = get_base_dir() / "config" / "settings.json"
    try:
        with open(settings_path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


_download_state: dict = {
    "active": False,
    "total_files": 0,
    "downloaded_files": 0,
    "current_file": "",
    "current_bytes": 0,
    "current_total": 0,
    "error": None,
    "done": False,
}
_state_lock = threading.Lock()


def get_download_state() -> dict:
    with _state_lock:
        return dict(_download_state)


def _set_state(**kwargs) -> None:
    with _state_lock:
        _download_state.update(kwargs)


def check_connectivity(test_url: str = "https://www.google.com") -> bool:
    if not _REQUESTS_AVAILABLE:
        return False
    try:
        resp = requests.get(test_url, timeout=5)
        return resp.status_code < 400
    except Exception:
        return False


def fetch_remote_manifest(url: str) -> Optional[dict]:
    """Fetch an updated manifest from a remote URL (optional)."""
    if not _REQUESTS_AVAILABLE or not url:
        return None
    try:
        logger.info("Fetching remote manifest: %s", url)
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning("Could not fetch remote manifest: %s", exc)
        return None


def _local_file_exists(dest_dir: Path, download_url: str) -> Optional[Path]:
    """Return the existing local file path if the driver was already downloaded."""
    if not dest_dir.exists():
        return None
    filename = download_url.rstrip("/").split("/")[-1]
    candidate = dest_dir / filename
    if candidate.exists() and candidate.stat().st_size > 0:
        return candidate
    # Also check any .exe / .zip in the directory
    for f in dest_dir.iterdir():
        if f.suffix.lower() in (".exe", ".zip", ".7z") and f.stat().st_size > 0:
            return f
    return None


def _download_file(
    url: str,
    dest: Path,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> bool:
    if not _REQUESTS_AVAILABLE:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        with requests.get(url, stream=True, timeout=120, headers=headers) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        _set_state(current_bytes=downloaded, current_total=total)
                        if on_progress:
                            on_progress(downloaded, total)
        return True
    except Exception as exc:
        logger.error("Download failed (%s): %s", url, exc)
        if dest.exists():
            dest.unlink()
        return False


def _collect_download_tasks(
    manifest: dict,
    drivers_dir: Path,
    cdn_base: str,
    keep_versions: int,
) -> list[tuple[str, Path, str, str]]:
    """
    Return list of (url, dest_path, driver_id, version) tuples for drivers
    that need to be downloaded (not yet present locally).
    """
    tasks: list[tuple[str, Path, str, str]] = []

    for driver_entry in manifest.get("drivers", []):
        driver_id = driver_entry.get("id", "")
        versions = driver_entry.get("versions", [])[:keep_versions]

        for ver_info in versions:
            version = ver_info.get("version", "")
            rel_path = ver_info.get("path", "").strip("/")
            download_url = ver_info.get("download_url", "").strip()
            inf = ver_info.get("inf", "")

            if not rel_path:
                continue

            dest_dir = drivers_dir / rel_path

            # If an INF-based driver, check for the INF file
            if inf:
                if (dest_dir / inf).exists():
                    logger.info("Already present: %s v%s", driver_id, version)
                    continue

            # If vendor EXE, check if the EXE already exists locally
            if _local_file_exists(dest_dir, download_url or ""):
                logger.info("Already downloaded: %s v%s", driver_id, version)
                continue

            # Determine URL and destination
            if download_url:
                # Vendor direct URL — filename from URL
                filename = download_url.rstrip("/").split("/")[-1]
                dest = dest_dir / filename
                tasks.append((download_url, dest, driver_id, version))
            elif cdn_base:
                # Custom CDN fallback
                url = f"{cdn_base.rstrip('/')}/{rel_path}"
                dest = dest_dir / rel_path.split("/")[-1]
                tasks.append((url, dest, driver_id, version))
            else:
                logger.warning(
                    "No download_url and no cdn_base_url for %s v%s -- skipped",
                    driver_id, version,
                )

    return tasks


def download_driver_db(
    on_progress: Optional[Callable[[dict], None]] = None,
) -> bool:
    """
    Download missing driver packages.

    Priority:
    1. version entry's download_url (vendor direct link)
    2. cdn_base_url + path (custom CDN fallback)

    Optionally fetches an updated manifest from remote_manifest_url first.
    """
    settings = load_settings()
    remote_manifest_url: str = settings.get("remote_manifest_url", "").strip()
    cdn_base: str = settings.get("cdn_base_url", "").strip()
    keep_versions: int = settings.get("keep_versions", 3)
    base_dir = get_base_dir()
    drivers_dir = base_dir / settings.get("download_path", "drivers")
    local_manifest_path = drivers_dir / "manifest.json"

    # Load local manifest
    local_manifest: dict = {"schema_version": "1.0", "drivers": []}
    if local_manifest_path.exists():
        try:
            with open(local_manifest_path, encoding="utf-8") as f:
                local_manifest = json.load(f)
        except Exception as exc:
            logger.error("Failed to load local manifest: %s", exc)

    # Optionally merge a remote manifest update
    if remote_manifest_url:
        remote = fetch_remote_manifest(remote_manifest_url)
        if remote:
            local_by_id = {d["id"]: d for d in local_manifest.get("drivers", [])}
            for entry in remote.get("drivers", []):
                did = entry.get("id")
                if did:
                    local_by_id[did] = entry
            local_manifest["drivers"] = list(local_by_id.values())
            from datetime import datetime
            local_manifest["last_updated"] = datetime.now().strftime("%Y-%m-%d")
            drivers_dir.mkdir(parents=True, exist_ok=True)
            with open(local_manifest_path, "w", encoding="utf-8") as f:
                json.dump(local_manifest, f, indent=2, ensure_ascii=False)
            logger.info("Remote manifest merged successfully")

    # Collect what needs downloading
    tasks = _collect_download_tasks(local_manifest, drivers_dir, cdn_base, keep_versions)
    total = len(tasks)

    if total == 0:
        logger.info("All drivers already present locally -- nothing to download")
        _set_state(active=False, done=True, total_files=0, downloaded_files=0, error=None)
        if on_progress:
            on_progress(get_download_state())
        return True

    logger.info("Starting download: %d driver package(s) to fetch", total)
    _set_state(active=True, total_files=total, downloaded_files=0, done=False, error=None)

    if on_progress:
        on_progress(get_download_state())

    success_count = 0
    for idx, (url, dest, driver_id, version) in enumerate(tasks):
        filename = dest.name
        _set_state(current_file=filename, current_bytes=0, current_total=0)
        logger.info("[%d/%d] %s v%s -> %s", idx + 1, total, driver_id, version, filename)

        ok = _download_file(url, dest)
        if ok:
            success_count += 1
            logger.info("Downloaded OK: %s", filename)
        else:
            logger.error("Failed: %s v%s", driver_id, version)

        _set_state(downloaded_files=idx + 1)
        if on_progress:
            on_progress(get_download_state())

    all_ok = success_count == total
    _set_state(
        active=False,
        done=True,
        current_file="",
        error=None if all_ok else f"{total - success_count}개 파일 다운로드 실패",
    )
    logger.info(
        "Download complete: %d/%d succeeded", success_count, total
    )
    return all_ok


def start_download_thread(on_progress: Optional[Callable[[dict], None]] = None) -> threading.Thread:
    t = threading.Thread(target=download_driver_db, args=(on_progress,), daemon=True)
    t.start()
    return t
