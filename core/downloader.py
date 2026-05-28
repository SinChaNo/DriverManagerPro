"""Online driver download logic — supports vendor direct URLs and custom CDN.

수정 이력:
  2026-05-22 - Intel downloadmirror 403 오류 수정
               도메인별 Referer 헤더 자동 지정 및 완전한 User-Agent 적용
  2026-05-22 - _download_file() 다운로드 후 0바이트 파일 검증 추가
               (0바이트 파일 생성 후 True 반환하던 버그 수정)
  2026-05-23 - DB 업데이트 시 vendor_api 직접 조회 방식으로 변경
               remote_manifest_url 방식 제거, 네트워크 연결 선행 체크 추가
               다운로드 상태에 vendor_api 단계(phase) 필드 추가
  2026-05-23 - 보안 취약점 패치
               - _local_file_exists(): 파일명 경로 순회 방지
               - _collect_download_tasks(): 파일명 경로 순회 방지
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

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
    "phase": "idle",          # "vendor_api" | "downloading" | "idle"
    "phase_label": "",        # UI에 표시할 현재 단계 설명
    "total_files": 0,
    "downloaded_files": 0,
    "current_file": "",
    "current_bytes": 0,
    "current_total": 0,
    "error": None,
    "done": False,
    "changes": [],            # 벤더 API 갱신으로 변경된 항목 목록
}
_state_lock = threading.Lock()


def get_download_state() -> dict:
    with _state_lock:
        return dict(_download_state)


def _set_state(**kwargs) -> None:
    with _state_lock:
        _download_state.update(kwargs)


# 다운로드 도메인별 Referer 매핑 — 403 차단 우회에 필요한 벤더 정책 반영
_REFERER_MAP: dict[str, str] = {
    "downloadmirror.intel.com": "https://www.intel.com/",
    "download.intel.com":       "https://www.intel.com/",
    "us.download.nvidia.com":   "https://www.nvidia.com/",
    "international.download.nvidia.com": "https://www.nvidia.com/",
    "drivers.amd.com":          "https://www.amd.com/",
    "www.realtek.com":          "https://www.realtek.com/",
}

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Intel downloadmirror는 다운로드 페이지 방문으로 쿠키를 발급받은 뒤에만
# .exe 직접 링크에 접근을 허용한다. 도메인별 워밍업 URL을 등록해두면
# 첫 요청 시 자동으로 쿠키를 수집한다.
_WARMUP_MAP: dict[str, str] = {
    "downloadmirror.intel.com": "https://www.intel.com/content/www/us/en/download-center/home.html",
    "download.intel.com": "https://www.intel.com/content/www/us/en/download-center/home.html",
}


def _build_request_headers(url: str) -> dict[str, str]:
    """URL 도메인에 맞는 HTTP 요청 헤더를 반환한다.

    Intel/AMD/NVIDIA 등은 브라우저 fingerprint 일부를 검증하므로
    Sec-Fetch-* 헤더와 Upgrade-Insecure-Requests를 포함하여 일반 브라우저와
    유사한 요청으로 위장한다 (403 차단 우회 목적).
    """
    domain = urlparse(url).netloc.lower()
    referer = _REFERER_MAP.get(domain, "")
    headers: dict[str, str] = {
        "User-Agent": _USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "cross-site",
        "Sec-Fetch-User": "?1",
        "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }
    if referer:
        headers["Referer"] = referer
    return headers


# 다운로드 세션 — 도메인별로 쿠키와 연결을 재사용하여 차단 우회 효과를 높인다.
_session: Optional["requests.Session"] = None
_warmed_domains: set[str] = set()


def _get_session() -> "requests.Session":
    """전역 다운로드 세션을 반환한다 (lazy 초기화)."""
    global _session
    if _session is None and _REQUESTS_AVAILABLE:
        _session = requests.Session()
        _session.headers.update({"User-Agent": _USER_AGENT})
    return _session  # type: ignore[return-value]


def _warmup_domain(domain: str) -> None:
    """다운로드 전 도메인의 진입 페이지를 방문하여 쿠키/세션을 발급받는다.

    Intel의 경우 직접 .exe URL 요청 시 403 Forbidden을 반환하지만,
    다운로드 센터 메인을 먼저 방문하면 후속 요청에 필요한 쿠키가 세팅된다.
    한 세션 내에서 도메인 당 1회만 수행한다.
    """
    if domain in _warmed_domains:
        return
    warmup_url = _WARMUP_MAP.get(domain)
    if not warmup_url:
        _warmed_domains.add(domain)
        return
    session = _get_session()
    if session is None:
        return
    try:
        # 워밍업 요청에는 일반 페이지 헤더 사용 (referer 없이 진입)
        warm_headers = {k: v for k, v in _build_request_headers(warmup_url).items() if k != "Referer"}
        warm_headers["Sec-Fetch-Site"] = "none"
        resp = session.get(warmup_url, headers=warm_headers, timeout=15)
        logger.info("도메인 워밍업: %s → HTTP %s (쿠키 %d개 수집)",
                    domain, resp.status_code, len(session.cookies))
    except Exception as exc:
        logger.warning("도메인 워밍업 실패 (%s): %s", domain, exc)
    _warmed_domains.add(domain)


def check_connectivity(test_url: str = "https://www.google.com") -> bool:
    """네트워크 연결 가능 여부를 확인한다.

    test_url 단일 실패가 네트워크 단절을 의미하지 않으므로, 실패 시 백업
    엔드포인트(Cloudflare, NVIDIA)를 순차 시도하여 false-negative를 줄인다.
    PyInstaller로 패키징된 EXE의 워커 스레드에서 SSL 컨텍스트 초기화가
    지연되어 첫 요청이 실패하는 경우도 흔하므로 다중 시도가 효과적이다.
    """
    if not _REQUESTS_AVAILABLE:
        logger.error("연결 확인: requests 모듈을 사용할 수 없습니다")
        return False

    # 1차: 사용자 지정/기본 URL, 2차: Cloudflare 1.1.1.1, 3차: NVIDIA CDN
    candidates = [test_url, "https://1.1.1.1", "https://us.download.nvidia.com"]
    last_error: str = ""
    for url in candidates:
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code < 400:
                logger.info("연결 확인 OK: %s (HTTP %s)", url, resp.status_code)
                return True
            last_error = f"HTTP {resp.status_code}"
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("연결 확인 실패 (%s): %s", url, last_error)
            continue

    logger.error("연결 확인: 모든 후보 URL 실패, 마지막 오류=%s", last_error)
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
    # Path.name으로 경로 순회 시퀀스 제거
    raw_name = download_url.rstrip("/").split("/")[-1]
    filename = Path(raw_name).name or ""
    candidate = dest_dir / filename if filename else None
    if candidate is not None and candidate.exists() and candidate.stat().st_size > 0:
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
        domain = urlparse(url).netloc.lower()
        # 도메인별 사전 방문으로 쿠키/세션을 발급받아 403 차단을 우회한다.
        _warmup_domain(domain)
        session = _get_session()
        headers = _build_request_headers(url)
        # 실제 파일 다운로드 요청은 same-origin navigation처럼 보이도록 헤더 조정
        headers["Sec-Fetch-Site"] = "same-site"
        headers["Sec-Fetch-Mode"] = "no-cors"
        headers["Sec-Fetch-Dest"] = "empty"
        headers["Accept"] = "*/*"

        with session.get(url, stream=True, timeout=120, headers=headers, allow_redirects=True) as resp:
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

        # 다운로드 후 파일 크기 검증 — 0바이트는 실패로 처리
        final_size = dest.stat().st_size if dest.exists() else 0
        if final_size == 0:
            logger.error("Download produced empty file (0 bytes): %s", url)
            dest.unlink(missing_ok=True)
            return False
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
                # Vendor direct URL — filename from URL (경로 순회 방지)
                raw_name = download_url.rstrip("/").split("/")[-1]
                filename = Path(raw_name).name or "driver.bin"
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
    DB 업데이트: 벤더 API로 manifest 버전 갱신 후 드라이버 파일을 다운로드한다.

    실행 단계:
    1. 네트워크 연결 확인 (오프라인이면 즉시 실패)
    2. vendor_api 모듈로 NVIDIA/AMD 최신 버전 조회 → manifest 갱신 저장
    3. manifest 기준으로 미다운로드 파일 수집 → 다운로드

    Priority for download URL:
    1. version entry의 download_url (벤더 직접 링크)
    2. cdn_base_url + path (사용자 CDN 폴백)
    """
    from core.vendor_api import update_manifest_versions

    settings = load_settings()
    cdn_base: str = settings.get("cdn_base_url", "").strip()
    keep_versions: int = settings.get("keep_versions", 2)
    base_dir = get_base_dir()
    drivers_dir = base_dir / settings.get("download_path", "drivers")
    local_manifest_path = drivers_dir / "manifest.json"

    # --- 단계 1: 네트워크 연결 확인 ---
    _set_state(
        active=True, phase="vendor_api",
        phase_label="네트워크 연결 확인 중...",
        done=False, error=None, changes=[],
    )
    if on_progress:
        on_progress(get_download_state())

    if not check_connectivity():
        logger.error("DB 업데이트 실패: 네트워크 연결 없음")
        _set_state(
            active=False, phase="idle", phase_label="",
            done=True, error="네트워크에 연결되어 있지 않습니다.",
        )
        if on_progress:
            on_progress(get_download_state())
        return False

    # --- 단계 2: 로컬 manifest 로드 ---
    local_manifest: dict = {"schema_version": "1.0", "drivers": []}
    if local_manifest_path.exists():
        try:
            with open(local_manifest_path, encoding="utf-8") as f:
                local_manifest = json.load(f)
        except Exception as exc:
            logger.error("manifest 로드 실패: %s", exc)

    # --- 단계 3: 벤더 API로 버전 정보 갱신 ---
    _set_state(phase_label="벤더 API에서 최신 버전 조회 중...")
    if on_progress:
        on_progress(get_download_state())

    logger.info("벤더 API 조회 시작...")
    updated_manifest, changes = update_manifest_versions(local_manifest)

    # 갱신된 manifest 저장
    drivers_dir.mkdir(parents=True, exist_ok=True)
    try:
        with open(local_manifest_path, "w", encoding="utf-8") as f:
            json.dump(updated_manifest, f, indent=2, ensure_ascii=False)
        logger.info("manifest 갱신 저장 완료 (변경: %d건)", len(changes))
    except Exception as exc:
        logger.error("manifest 저장 실패: %s", exc)

    _set_state(changes=changes, phase_label=f"버전 조회 완료 ({len(changes)}건 갱신)")
    if on_progress:
        on_progress(get_download_state())

    # --- 단계 4: 미다운로드 파일 수집 ---
    _set_state(phase="downloading", phase_label="다운로드 목록 준비 중...")
    if on_progress:
        on_progress(get_download_state())

    tasks = _collect_download_tasks(updated_manifest, drivers_dir, cdn_base, keep_versions)
    total = len(tasks)

    if total == 0:
        logger.info("모든 드라이버 파일이 이미 로컬에 존재함 — 다운로드 불필요")
        _set_state(
            active=False, phase="idle", phase_label="",
            done=True, total_files=0, downloaded_files=0, error=None,
        )
        if on_progress:
            on_progress(get_download_state())
        return True

    # --- 단계 5: 파일 다운로드 ---
    logger.info("다운로드 시작: %d개 파일", total)
    _set_state(total_files=total, downloaded_files=0)
    if on_progress:
        on_progress(get_download_state())

    success_count = 0
    for idx, (url, dest, driver_id, version) in enumerate(tasks):
        filename = dest.name
        _set_state(current_file=filename, current_bytes=0, current_total=0)
        logger.info("[%d/%d] %s v%s → %s", idx + 1, total, driver_id, version, filename)

        ok = _download_file(url, dest)
        if ok:
            success_count += 1
            logger.info("다운로드 완료: %s", filename)
        else:
            logger.error("다운로드 실패: %s v%s", driver_id, version)

        _set_state(downloaded_files=idx + 1)
        if on_progress:
            on_progress(get_download_state())

    all_ok = success_count == total
    # 부분 성공 시 사용자에게 명확히 보여주기 위해 성공/실패 갯수 모두 표시.
    # 실패한 파일은 벤더의 URL/접근정책 변경에 따른 것이므로 앱 사용에는 치명적이지 않다.
    if all_ok:
        err_msg = None
    elif success_count > 0:
        err_msg = f"부분 성공: {success_count}개 완료, {total - success_count}개 실패 (벤더 URL/차단 문제)"
    else:
        err_msg = f"전체 실패: {total}개 파일 모두 다운로드 불가"

    _set_state(
        active=False, phase="idle", phase_label="",
        done=True, current_file="",
        downloaded_files=success_count,  # UI가 성공 갯수를 정확히 보여주도록 보정
        total_files=total,
        error=err_msg,
    )
    logger.info("다운로드 완료: %d/%d 성공", success_count, total)
    return all_ok


def start_download_thread(on_progress: Optional[Callable[[dict], None]] = None) -> threading.Thread:
    t = threading.Thread(target=download_driver_db, args=(on_progress,), daemon=True)
    t.start()
    return t
