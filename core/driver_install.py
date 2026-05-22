"""
Silent driver installation via pnputil / vendor setup EXE.

수정 이력:
  - 2026-05-22: 로컬 파일 미존재 시 download_url에서 자동 다운로드 후 설치 로직 추가
                _progress에 stage(downloading/installing), download_pct 필드 추가
                latest_path 경로 버그 수정 (main.py에서 download_path 프리픽스 전달)
  - 2026-05-22: 로그 수집 강화 및 버그 수정
                - 설치 전 driver_info 전체 DEBUG 로깅
                - subprocess stdout/stderr 전문 DEBUG 기록
                - _download_driver() Referer 헤더 적용 (403 방지)
                - 벤더별 사일런트 플래그 분기 (_VENDOR_SILENT_FLAGS)
                - EXE 타임아웃 300 → 600초
                - run_install_queue() 세션 구분선 로깅 추가
                - 예외 발생 시 exc_info=True 로깅
  - 2026-05-22: _download_driver() 0바이트 파일 검증 추가 (WinError 1392 예방)
                _run_vendor_exe() MZ 헤더 검증 추가 (손상된 EXE 실행 차단)
"""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

from core.logger import logger, log_session_start, log_session_end


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


# ── 다운로드 헤더 ─────────────────────────────────────────────────────────────

# 도메인별 Referer 매핑 (downloader.py와 동일 정책 유지)
_REFERER_MAP: dict[str, str] = {
    "downloadmirror.intel.com":          "https://www.intel.com/",
    "download.intel.com":                "https://www.intel.com/",
    "us.download.nvidia.com":            "https://www.nvidia.com/",
    "international.download.nvidia.com": "https://www.nvidia.com/",
    "drivers.amd.com":                   "https://www.amd.com/",
    "www.realtek.com":                   "https://www.realtek.com/",
}

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _build_request_headers(url: str) -> dict[str, str]:
    """URL 도메인에 맞는 HTTP 요청 헤더를 반환한다."""
    domain = urlparse(url).netloc.lower()
    headers: dict[str, str] = {
        "User-Agent": _USER_AGENT,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    }
    referer = _REFERER_MAP.get(domain, "")
    if referer:
        headers["Referer"] = referer
    return headers


# ── 벤더별 사일런트 플래그 ─────────────────────────────────────────────────────

# 벤더마다 자체 설치 프로그램 플래그 규격이 다름
_VENDOR_SILENT_FLAGS: dict[str, list[str]] = {
    "nvidia":  ["-s", "-noeula", "-noreboot"],
    "amd":     ["--silent", "--noreboot"],
    "intel":   ["-s", "-norestart", "-q"],
    "realtek": ["/s"],
}

_DEFAULT_SILENT_FLAGS = ["/s", "/quiet", "/norestart"]


def _get_silent_flags(vendor: str) -> list[str]:
    """벤더 이름에 맞는 사일런트 설치 플래그를 반환한다."""
    return _VENDOR_SILENT_FLAGS.get(vendor.lower().strip(), _DEFAULT_SILENT_FLAGS)


# ── 공통 상태 ─────────────────────────────────────────────────────────────────

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


# ── subprocess 실행 헬퍼 ──────────────────────────────────────────────────────

def _log_subprocess_output(label: str, stdout: str, stderr: str) -> None:
    """subprocess 결과를 DEBUG 레벨로 전문 기록한다."""
    if stdout and stdout.strip():
        logger.debug("[%s] stdout:\n%s", label, stdout.strip())
    if stderr and stderr.strip():
        logger.debug("[%s] stderr:\n%s", label, stderr.strip())


def _run_pnputil(inf_path: Path) -> tuple[bool, str, bool]:
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
        _log_subprocess_output("pnputil", proc.stdout, proc.stderr)
        output = proc.stdout + proc.stderr
        success = proc.returncode in (0, 3010)  # 3010 = success + reboot needed
        reboot = proc.returncode == 3010 or "reboot" in output.lower()
        logger.debug("pnputil exit code: %d", proc.returncode)
        return success, output, reboot
    except subprocess.TimeoutExpired:
        logger.error("pnputil timeout for %s", inf_path)
        return False, "Timeout during pnputil install", False
    except Exception as exc:
        logger.error("pnputil error: %s", exc, exc_info=True)
        return False, str(exc), False


def _run_vendor_exe(exe_path: Path, vendor: str = "") -> tuple[bool, str, bool]:
    """벤더별 사일런트 플래그를 적용하여 드라이버 EXE를 실행한다."""
    # MZ 헤더 검증 — 0바이트 또는 손상된 파일 실행 방지 (WinError 1392 예방)
    try:
        with open(exe_path, "rb") as f:
            header = f.read(2)
        if header != b"MZ":
            size = exe_path.stat().st_size
            msg = f"EXE 파일이 유효하지 않습니다 (MZ 헤더 없음, {size}바이트): {exe_path.name}"
            logger.error(msg)
            return False, msg, False
    except OSError as exc:
        logger.error("EXE 파일 읽기 실패: %s", exc)
        return False, f"EXE 파일 읽기 실패: {exc}", False

    silent_flags = _get_silent_flags(vendor)
    cmd = [str(exe_path)] + silent_flags
    logger.info("Vendor EXE [%s]: %s", vendor or "unknown", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 300 → 600초 (대용량 드라이버 설치 대응)
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        _log_subprocess_output(f"vendor_exe/{vendor or 'unknown'}", proc.stdout, proc.stderr)
        output = proc.stdout + proc.stderr
        logger.debug("Vendor EXE exit code: %d", proc.returncode)
        success = proc.returncode in (0, 3010, 1641)
        reboot = proc.returncode in (3010, 1641) or "reboot" in output.lower()
        return success, output, reboot
    except subprocess.TimeoutExpired:
        logger.error("Vendor EXE timeout (600s): %s", exe_path)
        return False, "Timeout during vendor EXE install", False
    except Exception as exc:
        logger.error("Vendor EXE error: %s", exc, exc_info=True)
        return False, str(exc), False


# ── 다운로드 ──────────────────────────────────────────────────────────────────

def _download_driver(url: str, dest_dir: Path, driver_name: str) -> tuple[bool, str]:
    """
    download_url에서 드라이버 EXE를 dest_dir로 다운로드한다.
    도메인별 Referer 헤더를 포함하여 403 오류를 방지한다.
    Returns: (success, file_path_or_error_message)
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

        headers = _build_request_headers(url)
        logger.info("Downloading %s -> %s", url, dest_file)
        logger.debug("Download headers: %s", {k: v for k, v in headers.items() if k != "User-Agent"})
        _set_progress(stage="downloading", download_pct=0, current_driver=driver_name)

        resp = requests.get(url, stream=True, timeout=600, headers=headers)
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

        # 다운로드 후 파일 크기 검증 — 0바이트는 손상 파일로 간주
        final_size = dest_file.stat().st_size if dest_file.exists() else 0
        if final_size == 0:
            logger.error("Download produced empty file (0 bytes): %s", url)
            dest_file.unlink(missing_ok=True)
            return False, "다운로드 실패: 파일 크기가 0바이트입니다 (서버 오류 또는 URL 만료)"

        logger.info("Download complete: %s (%d bytes)", dest_file.name, final_size)
        return True, str(dest_file)

    except Exception as exc:
        logger.error("Download failed [%s]: %s", url, exc, exc_info=True)
        return False, f"다운로드 실패: {exc}"


# ── 단일 드라이버 설치 ────────────────────────────────────────────────────────

def install_driver(driver_info: dict) -> dict:
    """
    단일 드라이버를 설치한다.
    로컬 파일이 없으면 download_url에서 자동 다운로드 후 설치한다.

    driver_info keys: driver_id, driver_name, vendor, latest_path, latest_inf, download_url
    Returns: { success, message, reboot_required }
    """
    base = get_base_dir()
    driver_path = base / driver_info.get("latest_path", "")
    inf_name    = driver_info.get("latest_inf", "")
    driver_name = driver_info.get("driver_name", "Unknown Driver")
    driver_id   = driver_info.get("driver_id", "")
    vendor      = driver_info.get("vendor", "")
    download_url = driver_info.get("download_url", "")

    # 설치 시작 전 전체 정보 DEBUG 기록 (원인 분석용)
    logger.debug(
        "install_driver called | id=%s name=%s vendor=%s path=%s inf=%s url=%s",
        driver_id, driver_name, vendor, driver_path, inf_name or "(none)", download_url or "(none)",
    )

    logger.info("Installing: %s (path=%s)", driver_name, driver_path)
    _set_progress(current_driver=driver_name, stage="installing", download_pct=0)

    # 로컬 드라이버 폴더가 없으면 download_url에서 다운로드
    if not driver_path.exists():
        logger.info("Local path not found — attempting download: %s", download_url or "(no url)")
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
        logger.info("Trying pnputil install: %s", inf_path)
        success, output, reboot = _run_pnputil(inf_path)
        if success:
            logger.info("pnputil install OK: %s", driver_name)
            return {"success": True, "message": output, "reboot_required": reboot}
        logger.warning("pnputil failed for %s (exit output logged above), trying vendor EXE fallback", driver_name)

    # ── Fallback: 폴더 내 EXE 파일 실행 ──
    # 플레이스홀더(1KB 미만) EXE 제외, 실제 파일만 선택
    exe_files = [f for f in driver_path.glob("*.exe") if f.stat().st_size > 1024]
    logger.debug("EXE candidates in %s: %s", driver_path, [f.name for f in exe_files])

    if exe_files:
        exe = exe_files[0]
        logger.info("Running vendor EXE: %s (vendor=%s)", exe.name, vendor or "unknown")
        success, output, reboot = _run_vendor_exe(exe, vendor)
        if success:
            logger.info("Vendor EXE install OK: %s", driver_name)
            return {"success": True, "message": output, "reboot_required": reboot}
        logger.error("Vendor EXE failed for %s (see DEBUG log for details)", driver_name)
        return {"success": False, "message": output, "reboot_required": False}

    msg = f"설치 가능한 파일을 찾을 수 없습니다: {driver_path}"
    logger.error(msg)
    return {"success": False, "message": msg, "reboot_required": False}


# ── 큐 실행 ───────────────────────────────────────────────────────────────────

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

    driver_names = [d.get("driver_name", d.get("driver_id", "?")) for d in driver_list]
    log_session_start(f"드라이버 설치 {total}건: {', '.join(driver_names)}")

    _set_progress(total=total, installed=0, percent=0, status="running", reboot_required=False)
    results: list[dict] = []
    success_count = 0

    for idx, driver_info in enumerate(driver_list):
        if _abort_flag.is_set():
            logger.warning("Install queue aborted at %d/%d", idx, total)
            _set_progress(status="aborted")
            break

        logger.info("─── [%d/%d] 시작 ─────────────────────────", idx + 1, total)
        result = install_driver(driver_info)
        result["driver_id"]         = driver_info.get("driver_id")
        result["driver_name"]       = driver_info.get("driver_name")
        result["device_class"]      = driver_info.get("device_class", "")
        result["installed_version"] = driver_info.get("installed_version", "")
        result["latest_bundled"]    = driver_info.get("latest_bundled", "")
        results.append(result)
        _install_results.append(result)

        if result["success"]:
            success_count += 1

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
    log_session_end("드라이버 설치", success_count=success_count, total=len(results))
    return results


# ── 관리자 권한 ───────────────────────────────────────────────────────────────

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
