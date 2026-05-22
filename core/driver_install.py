"""Silent driver installation via pnputil / vendor setup EXE."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

from core.logger import logger


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


_abort_flag = threading.Event()
_progress: dict = {
    "percent": 0,
    "current_driver": "",
    "installed": 0,
    "total": 0,
    "status": "idle",
    "reboot_required": False,
}
_install_results: list[dict] = []
_progress_lock = threading.Lock()


def get_progress() -> dict:
    with _progress_lock:
        return dict(_progress)


def _set_progress(**kwargs) -> None:
    with _progress_lock:
        _progress.update(kwargs)


def get_install_results() -> list[dict]:
    return list(_install_results)


def clear_install_results() -> None:
    global _install_results
    _install_results = []


def abort_install() -> None:
    _abort_flag.set()
    logger.warning("Install abort requested by user")


def reset_abort() -> None:
    _abort_flag.clear()


def _run_pnputil(inf_path: Path) -> tuple[bool, str]:
    cmd = ["pnputil", "/add-driver", str(inf_path), "/install", "/subdirs"]
    logger.info("pnputil: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        output = proc.stdout + proc.stderr
        success = proc.returncode in (0, 3010)  # 3010 = success + reboot needed
        reboot = proc.returncode == 3010 or "reboot" in output.lower()
        return success, output, reboot
    except subprocess.TimeoutExpired:
        return False, "Timeout during pnputil install", False
    except Exception as exc:
        return False, str(exc), False


def _run_vendor_exe(exe_path: Path) -> tuple[bool, str, bool]:
    silent_flags = ["/s", "/silent", "/quiet", "/norestart"]
    cmd = [str(exe_path)] + silent_flags
    logger.info("Vendor EXE: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        output = proc.stdout + proc.stderr
        success = proc.returncode in (0, 3010, 1641)
        reboot = proc.returncode in (3010, 1641) or "reboot" in output.lower()
        return success, output, reboot
    except subprocess.TimeoutExpired:
        return False, "Timeout during vendor EXE install", False
    except Exception as exc:
        return False, str(exc), False


def install_driver(driver_info: dict) -> dict:
    """
    Install a single driver.

    driver_info keys: driver_id, driver_name, latest_path, latest_inf
    Returns: { success, message, reboot_required }
    """
    base = get_base_dir()
    driver_path = base / driver_info.get("latest_path", "")
    inf_name = driver_info.get("latest_inf", "")
    driver_name = driver_info.get("driver_name", "Unknown Driver")

    logger.info("Installing: %s (path=%s)", driver_name, driver_path)
    _set_progress(current_driver=driver_name, status="installing")

    if not driver_path.exists():
        msg = f"Driver path not found: {driver_path}"
        logger.error(msg)
        return {"success": False, "message": msg, "reboot_required": False}

    # Try INF-based install first
    inf_path = driver_path / inf_name if inf_name else None
    if inf_path and inf_path.exists():
        success, output, reboot = _run_pnputil(inf_path)
        if success:
            logger.info("pnputil install OK: %s", driver_name)
            return {"success": True, "message": output, "reboot_required": reboot}
        logger.warning("pnputil failed for %s, trying vendor EXE fallback", driver_name)

    # Fallback: look for setup EXE
    exe_files = list(driver_path.glob("*.exe"))
    if exe_files:
        success, output, reboot = _run_vendor_exe(exe_files[0])
        if success:
            logger.info("Vendor EXE install OK: %s", driver_name)
            return {"success": True, "message": output, "reboot_required": reboot}
        logger.error("Vendor EXE failed for %s: %s", driver_name, output)
        return {"success": False, "message": output, "reboot_required": False}

    msg = f"No installable file found in {driver_path}"
    logger.error(msg)
    return {"success": False, "message": msg, "reboot_required": False}


def run_install_queue(
    driver_list: list[dict],
    on_progress: Optional[Callable[[dict], None]] = None,
) -> list[dict]:
    """
    Install all drivers in queue sequentially.
    Calls on_progress(progress_dict) after each install.
    """
    reset_abort()
    clear_install_results()
    total = len(driver_list)
    _set_progress(total=total, installed=0, percent=0, status="running", reboot_required=False)
    results: list[dict] = []

    for idx, driver_info in enumerate(driver_list):
        if _abort_flag.is_set():
            logger.warning("Install queue aborted at %d/%d", idx, total)
            _set_progress(status="aborted")
            break

        result = install_driver(driver_info)
        result["driver_id"] = driver_info.get("driver_id")
        result["driver_name"] = driver_info.get("driver_name")
        result["device_class"] = driver_info.get("device_class", "")
        result["installed_version"] = driver_info.get("installed_version", "")
        result["latest_bundled"] = driver_info.get("latest_bundled", "")
        results.append(result)
        _install_results.append(result)

        installed = idx + 1
        percent = int((installed / total) * 100)
        reboot_so_far = _progress.get("reboot_required", False) or result.get("reboot_required", False)
        _set_progress(
            installed=installed,
            percent=percent,
            reboot_required=reboot_so_far,
        )

        if on_progress:
            on_progress(get_progress())

    _set_progress(status="done", current_driver="")
    logger.info("Install queue complete: %d results", len(results))
    return results


def check_admin() -> bool:
    """Return True if running with administrator privileges."""
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> None:
    """Re-launch the current process with UAC elevation."""
    import ctypes
    exe = sys.executable
    params = " ".join(sys.argv)
    ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
    sys.exit(0)
