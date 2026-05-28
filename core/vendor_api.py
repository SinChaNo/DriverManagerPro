"""Vendor API fetchers — queries official vendor endpoints to get the latest driver versions.
Called only when the user explicitly requests a DB update (not on app start).

수정 이력:
  2026-05-23 - 신규 생성: 벤더 API 직접 조회 방식 구현 (NVIDIA GFE API, AMD release JSON)
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from core.logger import logger

try:
    import requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False

_TIMEOUT = 15  # 벤더 API 조회 제한 시간 (초)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

# NVIDIA GeForce Experience 드라이버 조회 API (JSON 응답)
_NVIDIA_GFE_API = (
    "https://gfwsl.geforce.com/services_toolkit/services/com/nvidia/services/"
    "AjaxDriverService.php"
)

# NVIDIA 드라이버 제품군 ID — driver_id → (pfid, path_template)
_NVIDIA_DRIVER_CONFIG: dict[str, tuple[str, str]] = {
    "nvidia-geforce-desktop-dch": ("816", "nvidia/geforce/desktop/v{version}"),
    "nvidia-geforce-notebook-dch": ("851", "nvidia/geforce/notebook/v{version}"),
}

# AMD Radeon 릴리스 JSON 엔드포인트
_AMD_API = "https://www.amd.com/apps/optamd/release-notes.json"

# AMD 드라이버 다운로드 URL 패턴 (API에 URL 없을 때 재구성용)
_AMD_URL_PATTERN = (
    "https://drivers.amd.com/drivers/installer/{major_minor}/whql/"
    "amd-software-adrenalin-edition-{version}-minimalsetup-{date_compact}_web.exe"
)


def _get(url: str, params: Optional[dict] = None) -> Optional["requests.Response"]:
    """표준 헤더로 GET 요청. 오류 시 None 반환."""
    if not _REQUESTS_AVAILABLE:
        return None
    try:
        resp = requests.get(url, headers=_HEADERS, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp
    except Exception as exc:
        logger.warning("Vendor API request failed (%s): %s", url, exc)
        return None


def _make_version_entry(
    version: str,
    date_str: str,
    tag: str,
    path_tpl: str,
    download_url: str,
    size_mb: int = 0,
) -> dict:
    """manifest.json 형식의 버전 항목 딕셔너리를 생성한다."""
    return {
        "version": version,
        "date": date_str,
        "tag": tag,
        "path": path_tpl.format(version=version),
        "download_url": download_url,
        "inf": "",
        "size_mb": size_mb,
        "os": ["win10", "win11"],
        "arch": "x64",
    }


def _parse_nvidia_date(dt_str: str) -> str:
    """NVIDIA 날짜 문자열 '2025/02/27 00:00:00' → 'YYYY-MM-DD' 변환."""
    try:
        return datetime.strptime(dt_str.strip(), "%Y/%m/%d %H:%M:%S").strftime("%Y-%m-%d")
    except ValueError:
        return datetime.now().strftime("%Y-%m-%d")


def _inject_previous(
    entries: list[dict],
    current_versions: list[dict],
    new_latest_ver: str,
) -> list[dict]:
    """
    API 결과가 1개뿐일 때 기존 manifest의 이전 버전을 previous로 추가한다.
    새 latest와 버전이 다른 첫 번째 항목을 previous로 사용.
    """
    if len(entries) >= 2 or not current_versions:
        return entries
    for cv in current_versions:
        if cv.get("version") != new_latest_ver:
            prev = dict(cv)
            prev["tag"] = "previous"
            entries.append(prev)
            break
    return entries


def fetch_nvidia_versions(driver_id: str, current_versions: list[dict]) -> Optional[list[dict]]:
    """
    NVIDIA GFE API로 최신 드라이버 버전 2개(latest, previous)를 조회한다.
    실패 시 None 반환 — 호출자는 기존 manifest를 유지한다.
    """
    config = _NVIDIA_DRIVER_CONFIG.get(driver_id)
    if not config:
        logger.warning("NVIDIA: driver_id=%s 에 대한 pfid 설정 없음", driver_id)
        return None

    pfid, path_tpl = config
    params = {
        "func": "DriverManualLookup",
        "pfid": pfid,
        "osID": "135",        # Windows 10/11 x64
        "languageCode": "1033",
        "isWHQL": "1",
        "dch": "1",
        "ctk": "0",
        "ModID": "1",
        "driverOS": "4",
        "isUpgradeNew": "1",
        "isCRD": "0",
        "qnf": "0",
        "sort1": "0",
        "numberOfResults": "2",
    }

    logger.info("NVIDIA API 호출: pfid=%s", pfid)
    resp = _get(_NVIDIA_GFE_API, params=params)
    if not resp:
        logger.error("NVIDIA API: HTTP 응답 없음 (pfid=%s)", pfid)
        return None

    logger.info("NVIDIA API: HTTP %s 수신 (pfid=%s)", resp.status_code, pfid)
    try:
        data = resp.json()
    except Exception as exc:
        logger.warning("NVIDIA API: JSON 파싱 실패: %s — 본문 일부: %s", exc, resp.text[:200])
        return None

    ids = data.get("IDS", [])
    if not ids:
        logger.warning("NVIDIA API: pfid=%s 에 대한 결과 없음. 응답 키: %s", pfid, list(data.keys()))
        return None

    logger.info("NVIDIA API: pfid=%s → %d개 결과 수신", pfid, len(ids))

    entries: list[dict] = []
    for idx, item in enumerate(ids[:2]):
        # NVIDIA API는 응답 구조가 자주 변경되므로 여러 위치에서 필드를 탐색한다.
        # downloadInfo 외에 항목 자체에 직접 들어있는 경우도 있음.
        info = item.get("downloadInfo") or item or {}

        # Version: Version / version / DriverVersion 등 다양한 키 시도
        version = (
            info.get("Version") or info.get("version")
            or info.get("DriverVersion") or item.get("Version") or ""
        )
        version = str(version).strip()

        # DownloadURL: DownloadURL / downloadUrl / DownloadURLFileSize 인접 위치 등
        url = (
            info.get("DownloadURL") or info.get("downloadUrl")
            or info.get("Download_URL") or info.get("download_url")
            or item.get("DownloadURL") or ""
        )
        url = str(url).strip()

        date_raw = (
            info.get("ReleaseDateTime") or info.get("ReleaseDate")
            or item.get("ReleaseDateTime") or ""
        )
        size_raw = info.get("Size") or info.get("size") or "0"

        if not version or not url:
            # 첫 항목 누락 시 응답 구조 진단용 키 목록을 로그에 남김 (1회만)
            if idx == 0:
                logger.warning(
                    "NVIDIA 파싱 누락: version='%s' url='%s' info 키=%s item 키=%s",
                    version, url[:80] if url else "",
                    list(info.keys())[:20], list(item.keys())[:20],
                )
            continue

        tag = "latest" if not entries else "previous"
        date_str = _parse_nvidia_date(date_raw)
        try:
            size_mb = int(float(size_raw))
        except (ValueError, TypeError):
            size_mb = 0

        entries.append(_make_version_entry(version, date_str, tag, path_tpl, url, size_mb))

    if not entries:
        logger.warning("NVIDIA API: pfid=%s 에서 유효한 항목 없음. 첫 항목 raw=%s",
                       pfid, str(ids[0])[:300] if ids else "")
        return None

    # API가 1건만 반환 시 기존 manifest의 previous를 보존
    new_latest = entries[0]["version"]
    entries = _inject_previous(entries, current_versions, new_latest)

    logger.info("NVIDIA %s: API에서 %d개 버전 조회 완료", driver_id, len(entries))
    return entries


def fetch_amd_versions(driver_id: str, current_versions: list[dict]) -> Optional[list[dict]]:
    """
    AMD release-notes JSON으로 최신 Radeon 드라이버 버전 2개를 조회한다.
    실패 시 None 반환 — 호출자는 기존 manifest를 유지한다.
    """
    path_tpl = "amd/radeon/v{version}"

    resp = _get(_AMD_API)
    if not resp:
        return None

    try:
        data = resp.json()
    except Exception as exc:
        logger.warning("AMD API: JSON 파싱 실패: %s", exc)
        return None

    # AMD release-notes.json 구조 — releases 키 또는 루트 배열 모두 지원
    releases: list = (
        data if isinstance(data, list)
        else data.get("releases", data.get("data", []))
    )
    if not releases:
        logger.warning("AMD API: 릴리스 데이터 없음")
        return None

    entries: list[dict] = []
    for rel in releases[:2]:
        # 다양한 필드명 패턴 대응
        version = (
            rel.get("version") or rel.get("Version")
            or rel.get("driverVersion") or rel.get("ReleaseVersion", "")
        ).strip()

        if not version:
            continue

        url = (
            rel.get("download_url") or rel.get("downloadUrl")
            or rel.get("url") or rel.get("URL", "")
        ).strip()

        date_raw = (
            rel.get("date") or rel.get("releaseDate")
            or rel.get("ReleaseDate", "")
        ).strip()

        # 날짜 파싱 (여러 형식 시도)
        date_str = datetime.now().strftime("%Y-%m-%d")
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
            try:
                date_str = datetime.strptime(date_raw, fmt).strftime("%Y-%m-%d")
                break
            except ValueError:
                continue

        # URL 없을 때 AMD 다운로드 URL 패턴으로 재구성
        if not url:
            parts = version.split(".")
            if len(parts) >= 2:
                major_minor = f"{parts[0]}.{parts[1]}"
                date_compact = date_str.replace("-", "")[2:]  # YYMMDD
                url = _AMD_URL_PATTERN.format(
                    major_minor=major_minor,
                    version=version,
                    date_compact=date_compact,
                )

        tag = "latest" if not entries else "previous"
        entries.append(_make_version_entry(version, date_str, tag, path_tpl, url))

    if not entries:
        logger.warning("AMD API: 유효한 버전 항목 파싱 실패")
        return None

    # API가 1건만 반환 시 기존 manifest의 previous를 보존
    new_latest = entries[0]["version"]
    entries = _inject_previous(entries, current_versions, new_latest)

    logger.info("AMD %s: API에서 %d개 버전 조회 완료", driver_id, len(entries))
    return entries


def update_manifest_versions(manifest: dict) -> tuple[dict, list[str]]:
    """
    manifest의 모든 드라이버를 순회하며 벤더 API로 버전 정보를 갱신한다.
    - NVIDIA, AMD: 벤더 API 조회 (실패 시 기존 유지)
    - Intel, Realtek: 정적 유지 (공개 API 없음)
    각 드라이버는 최대 2개 버전(latest, previous)만 보존.

    Returns:
        (갱신된 manifest dict, 변경 사항 설명 리스트)
    """
    changes: list[str] = []
    updated_drivers: list[dict] = []

    for driver in manifest.get("drivers", []):
        driver_id: str = driver.get("id", "")
        vendor: str = driver.get("vendor", "").upper()
        current_versions: list[dict] = driver.get("versions", [])
        current_latest = current_versions[0].get("version", "") if current_versions else ""

        new_versions: Optional[list[dict]] = None

        if vendor == "NVIDIA":
            logger.info("NVIDIA %s API 조회 중...", driver_id)
            new_versions = fetch_nvidia_versions(driver_id, current_versions)
        elif vendor == "AMD":
            logger.info("AMD %s API 조회 중...", driver_id)
            new_versions = fetch_amd_versions(driver_id, current_versions)
        else:
            # Intel, Realtek 등 — 공개 API 없어 정적 유지, 2개 초과분만 제거
            driver = dict(driver)
            driver["versions"] = current_versions[:2]
            updated_drivers.append(driver)
            continue

        driver = dict(driver)

        if new_versions:
            new_latest = new_versions[0].get("version", "")
            if new_latest and new_latest != current_latest:
                changes.append(f"{driver_id}: {current_latest} → {new_latest}")
                logger.info("버전 갱신: %s  %s → %s", driver_id, current_latest, new_latest)
            else:
                logger.info("%s: 이미 최신 버전 (%s)", driver_id, current_latest)
            driver["versions"] = new_versions[:2]
        else:
            # API 실패 — 기존 버전 유지, 2개 초과분 제거
            logger.warning("%s: API 조회 실패, 기존 버전 유지", driver_id)
            driver["versions"] = current_versions[:2]

        updated_drivers.append(driver)

    updated = dict(manifest)
    updated["drivers"] = updated_drivers
    updated["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    return updated, changes
