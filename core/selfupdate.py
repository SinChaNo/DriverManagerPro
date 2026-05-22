"""App self-update: check GitHub Releases and replace the running EXE."""

from __future__ import annotations

import json
import os
import shutil
import sys
import threading
from pathlib import Path
from typing import Optional

from core.logger import logger

try:
    import requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


def _load_settings() -> dict:
    try:
        with open(get_base_dir() / "config" / "settings.json", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _load_app_version() -> str:
    try:
        with open(get_base_dir() / "config" / "app_version.json", encoding="utf-8") as f:
            return json.load(f).get("version", "0.0.0")
    except Exception:
        return "0.0.0"


def _version_tuple(v: str) -> tuple[int, ...]:
    parts = v.strip().lstrip("v").split(".")
    result = []
    for p in parts:
        try:
            result.append(int(p))
        except ValueError:
            result.append(0)
    return tuple(result)


def check_app_update() -> dict:
    """
    Query GitHub Releases API for a newer version.
    Returns: { update_available, current_version, latest_version, download_url, release_notes }
    """
    current = _load_app_version()
    settings = _load_settings()
    update_url: str = settings.get("app_update_url", "")

    result = {
        "update_available": False,
        "current_version": current,
        "latest_version": current,
        "download_url": "",
        "release_notes": "",
    }

    if not update_url or not _REQUESTS_AVAILABLE:
        return result

    try:
        logger.info("Checking for app updates at: %s", update_url)
        resp = requests.get(update_url, timeout=15, headers={"Accept": "application/vnd.github.v3+json"})
        resp.raise_for_status()
        data = resp.json()

        latest = data.get("tag_name", "").lstrip("v")
        notes = data.get("body", "")

        # Find Windows EXE asset
        download_url = ""
        for asset in data.get("assets", []):
            name: str = asset.get("name", "")
            if name.endswith(".exe") and "win" in name.lower():
                download_url = asset.get("browser_download_url", "")
                break

        if not download_url:
            for asset in data.get("assets", []):
                name = asset.get("name", "")
                if name.endswith(".exe"):
                    download_url = asset.get("browser_download_url", "")
                    break

        if latest and _version_tuple(latest) > _version_tuple(current):
            result.update({
                "update_available": True,
                "latest_version": latest,
                "download_url": download_url,
                "release_notes": notes,
            })
            logger.info("App update available: %s → %s", current, latest)
        else:
            logger.info("App is up to date (v%s)", current)

    except Exception as exc:
        logger.warning("App update check failed: %s", exc)

    return result


def apply_update(download_url: str, on_progress: Optional[callable] = None) -> bool:
    """
    Download the new EXE, back up the old one, replace it, and restart.
    Works only when running as a frozen EXE (PyInstaller).
    """
    if not getattr(sys, "frozen", False):
        logger.warning("Self-update skipped: not running as frozen EXE")
        return False

    if not _REQUESTS_AVAILABLE:
        logger.error("requests not available — cannot download update")
        return False

    current_exe = Path(sys.executable)
    backup_exe = current_exe.with_suffix(".exe.bak")
    new_exe = current_exe.with_suffix(".exe.new")

    logger.info("Downloading update from: %s", download_url)
    try:
        with requests.get(download_url, stream=True, timeout=300) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            with open(new_exe, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if on_progress and total:
                            on_progress(downloaded, total)
    except Exception as exc:
        logger.error("Update download failed: %s", exc)
        if new_exe.exists():
            new_exe.unlink()
        return False

    # Backup → replace
    try:
        if backup_exe.exists():
            backup_exe.unlink()
        shutil.copy2(current_exe, backup_exe)
        logger.info("Backup created: %s", backup_exe)

        # On Windows we can't replace a running EXE directly —
        # write a small batch script that does the swap after exit.
        bat_path = current_exe.parent / "_update_apply.bat"
        bat_content = (
            "@echo off\n"
            "timeout /t 2 /nobreak > nul\n"
            f'move /y "{new_exe}" "{current_exe}"\n'
            f'start "" "{current_exe}"\n'
            f'del "%~f0"\n'
        )
        bat_path.write_text(bat_content, encoding="ascii")
        logger.info("Update will apply on next launch via: %s", bat_path)

        # Launch the batch and exit
        os.startfile(str(bat_path))
        return True

    except Exception as exc:
        logger.error("Failed to stage update: %s", exc)
        if new_exe.exists():
            new_exe.unlink()
        return False


def start_update_thread(download_url: str, on_progress=None) -> threading.Thread:
    t = threading.Thread(target=apply_update, args=(download_url, on_progress), daemon=True)
    t.start()
    return t
