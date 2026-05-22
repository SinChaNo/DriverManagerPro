"""
Silent driver installation via pnputil / vendor setup EXE.

수정 이력:
  - 2026-05-22: 로컬 파일 미존재 시 download_url에서 자동 다운로드 후 설치 로직 추가
                _progress에 stage(downloading/installing), download_pct 필드 추가
                latest_path 경로 버그 수정 (main.py에서 download_path 프리픽스 전달)
"""

from __future__ import annotations

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
    # 현재 단계: idle | downloading | installing
    "stage": "idle",
    # 현재 파일 다운로드 진행률 (0~100)
    "download_pct": 0,
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


def _download_driver(url: str, dest_dir: Path, driver_name: str) -> tuple[bool, str]:
    """
    download_url에서 드라이버 EXE를 dest_dir로 다운로드한다.
    다운로드 진행률을 _progress.download_pct에 실시간 반영한다.
    Returns: (success, message_or_filepath)
    """
    try:
        import requests  # 런타임 임포트로 선택적 의존성 처리
    except ImportError:
        return False, "requests 모듈이 설치되지 않았습니다. pip install requests"

    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        # URL 마지막 세그먼트를 파일명으로 사용
        filename = url.rstrip("/").split("/")[-1]
        if not filename.endswith(".exe"):
            filename = filename + ".exe"
        dest_file = dest_dir / filename

        logger.info("Downloading %s -> %s", url, dest_file)
        _set_progress(stage="downloading", download_pct=0, current_driver=driver_name)

        resp = requests.get(url, stream=True, timeout=600)
        resp.raise_for_status()

        total_size = int(resp.headers.get("content-length", 0))
        downloaded = 0

        with open(dest_file, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):  # 1 MB 단위
                if _abort_flag.is_set():
                    dest_file.unlink(missing_ok=True)
                    return False, "사용자에 의해 다운로드가 중단되었습니다"
                f.write(chunk)
                downloaded += len(chunk)
                if total_size > 0:
                    pct = int(downloaded / total_size * 100)
                    _set_progress(download_pct=pct)

        logger.info("Download complete: %s (%d bytes)", dest_file.name, downloaded)
        return True, str(dest_file)

    except Exception as exc:
        msg = f"다운로드 실패: {exc}"
        logger.error(msg)
        return False, msg


def install_driver(driver_info: dict) -> dict:
    """
    단일 드라이버를 설치한다.
    로컬 파일이 없으면 download_url에서 자동 다운로드 후 설치한다.

    driver_info keys: driver_id, driver_name, latest_path, latest_inf, download_url
    Returns: { success, message, reboot_required }
    """
    base = get_base_dir()
    driver_path = base / driver_info.get("latest_path", "")
    inf_name = driver_info.get("latest_inf", "")
    driver_name = driver_info.get("driver_name", "Unknown Driver")
    download_url = driver_info.get("download_url", "")

    logger.info("Installing: %s (path=%s)", driver_name, driver_path)
    _set_progress(current_driver=driver_name, stage="installing", download_pct=0)

    # 로컬 드라이버 폴더가 없으면 download_url에서 다운로드
    if not driver_path.exists():
        if not download_url:
            msg = f"드라이버 경로를 찾을 수 없고 다운로드 URL도 없습니다: {driver_path}"
            logger.error(msg)
            return {"success": False, "message": msg, "reboot_required": False}

        ok, result = _download_driver(download_url, driver_path, driver_name)
        if not ok:
            return {"success": False, "message": result, "reboot_required": False}

        # 다운로드 완료 후 설치 단계로 전환
        _set_progress(stage="installing", download_pct=100, current_driver=driver_name)

    # ── INF 기반 설치 우선 시도 ──
    inf_path = driver_path / inf_name if inf_name else None
    if inf_path and inf_path.exists():
        success, output, reboot = _run_pnputil(inf_path)
        if success:
            logger.info("pnputil install OK: %s", driver_name)
            return {"success": True, "message": output, "reboot_required": reboot}
        logger.warning("pnputil failed for %s, trying vendor EXE fallback", driver_name)

    # ── Fallback: 폴더 내 EXE 파일 실행 ──
    # 플레이스홀더(0바이트) EXE 제외, 실제 파일만 선택
    exe_files = [f for f in driver_path.glob("*.exe") if f.stat().st_size > 1024]
    if exe_files:
        success, output, reboot = _run_vendor_exe(exe_files[0])
        if success:
            logger.info("Vendor EXE install OK: %s", driver_name)
            return {"success": True, "message": output, "reboot_required": reboot}
        logger.error("Vendor EXE failed for %s: %s", driver_name, output)
        return {"success": False, "message": output, "reboot_required": False}

    msg = f"설치 가능한 파일을 찾을 수 없습니다: {driver_path}"
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
