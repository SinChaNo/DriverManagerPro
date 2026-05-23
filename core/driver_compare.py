"""
Compare installed driver versions against manifest entries.

수정 이력:
  - 2026-05-22: device_class가 빈 값일 때 manifest의 class 필드를 fallback으로 사용하도록 수정
  - 2026-05-22: NVIDIA 버전 형식 정규화 추가 (Windows 4-part → NVIDIA 2-part 변환)
               _hardware_ids_match에 VEN-only HWID 매칭 추가
               퍼지 매칭 키워드에서 "intel" 제거 (과다 매칭 방지)
  - 2026-05-23: 보안 취약점 패치
               - load_manifest(): _validate_manifest_schema()로 스키마 검증 추가
               - _hardware_ids_match(): _MAX_HWID_LEN 길이 제한 및 ReDoS 방지 패턴 적용
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from core.logger import logger


def _parse_version(version_str: str) -> tuple[int, ...]:
    """버전 문자열을 비교 가능한 int 튜플로 변환한다."""
    cleaned = re.sub(r"[^\d.]", "", version_str.strip())
    parts = cleaned.split(".")
    result: list[int] = []
    for part in parts:
        try:
            result.append(int(part))
        except ValueError:
            result.append(0)
    while len(result) < 4:
        result.append(0)
    return tuple(result)


def version_gt(a: str, b: str) -> bool:
    """Return True if version a is greater than b."""
    return _parse_version(a) > _parse_version(b)


def version_eq(a: str, b: str) -> bool:
    return _parse_version(a) == _parse_version(b)


def _nvidia_win_to_nvidia_ver(win_ver: str) -> Optional[str]:
    """Windows 4-part NVIDIA 드라이버 버전을 NVIDIA 표기 버전으로 변환한다.

    예: '32.0.15.7283' → '572.83'
    변환 공식: major = (parts[2] % 10) * 100 + parts[3] // 100
              minor = parts[3] % 100
    """
    parts = win_ver.split(".")
    if len(parts) != 4:
        return None
    try:
        p2, p3 = int(parts[2]), int(parts[3])
        major = (p2 % 10) * 100 + p3 // 100
        minor = p3 % 100
        return f"{major}.{minor:02d}"
    except ValueError:
        return None


def _normalize_installed_version(installed_ver: str, latest_ver: str, vendor: str) -> str:
    """설치된 버전을 manifest 버전 형식에 맞게 정규화한다.

    NVIDIA는 WMI가 Windows 4-part 형식(32.0.15.7283)을 반환하지만
    manifest는 NVIDIA 2-part 형식(572.83)으로 저장한다.
    manifest가 2-part이고 installed가 4-part인 NVIDIA 드라이버의 경우 변환한다.
    """
    if vendor.lower() != "nvidia":
        return installed_ver
    latest_parts = latest_ver.split(".")
    installed_parts = installed_ver.split(".")
    if len(latest_parts) == 2 and len(installed_parts) == 4:
        converted = _nvidia_win_to_nvidia_ver(installed_ver)
        if converted:
            return converted
    return installed_ver


# 하드웨어 ID 최대 허용 길이 — 초과 시 ReDoS 공격 가능성 있으므로 건너뜀
_MAX_HWID_LEN = 256


def _hardware_ids_match(device_hwids: list[str], driver_hwids: list[str]) -> bool:
    """기기 HardwareID 목록과 드라이버 HardwareID 목록 간 일치 여부를 반환한다.

    지원 형식:
      - PCI: VEN_XXXX&DEV_XXXX (완전/부분 일치)
      - PCI: VEN_XXXX (VEN-only, 벤더 전체 대상)
      - USB: VID_XXXX&PID_XXXX (완전/부분 일치)
    """
    device_upper = {h.upper() for h in device_hwids}
    for hwid in driver_hwids:
        # 과도하게 긴 HWID는 ReDoS 위험이 있으므로 건너뜀
        if len(hwid) > _MAX_HWID_LEN:
            logger.warning("하드웨어 ID가 최대 길이를 초과합니다, 건너뜀: %s", hwid[:50])
            continue

        # 완전 일치
        if hwid.upper() in device_upper:
            return True

        # PCI VEN+DEV 부분 일치 — [^&]* 로 ReDoS 방지 (& 구분자 경계 제한)
        pci_match = re.search(r"VEN_([0-9A-Fa-f]{4})[^&]*DEV_([0-9A-Fa-f]{4})", hwid)
        if pci_match:
            ven, dev = pci_match.group(1).upper(), pci_match.group(2).upper()
            for d_hwid in device_upper:
                if f"VEN_{ven}" in d_hwid and f"DEV_{dev}" in d_hwid:
                    return True
            continue

        # USB VID+PID 부분 일치 — [^&]* 로 ReDoS 방지 (예: USB\VID_8087&PID_0026)
        usb_match = re.search(r"VID_([0-9A-Fa-f]{4})[^&]*PID_([0-9A-Fa-f]{4})", hwid)
        if usb_match:
            vid, pid = usb_match.group(1).upper(), usb_match.group(2).upper()
            for d_hwid in device_upper:
                if f"VID_{vid}" in d_hwid and f"PID_{pid}" in d_hwid:
                    return True
            continue

        # VEN-only 매칭: 드라이버가 벤더 전체를 대상으로 하는 경우 (예: PCI\VEN_10DE)
        ven_only = re.search(r"VEN_([0-9A-Fa-f]{4})", hwid)
        if ven_only and "&" not in hwid:
            ven = ven_only.group(1).upper()
            for d_hwid in device_upper:
                if f"VEN_{ven}" in d_hwid:
                    return True

    return False


def _class_matches(device_class: str, driver_class: str) -> bool:
    return device_class.lower() == driver_class.lower()


def _validate_manifest_schema(data: dict) -> None:
    """매니페스트 데이터의 기본 스키마를 검증한다. 이상 시 ValueError를 발생시킨다."""
    if not isinstance(data, dict):
        raise ValueError("매니페스트는 딕셔너리여야 합니다")
    if not isinstance(data.get("drivers", []), list):
        raise ValueError("drivers 필드는 리스트여야 합니다")
    for driver in data.get("drivers", []):
        if not isinstance(driver, dict):
            continue
        for version in driver.get("versions", []):
            if not isinstance(version, dict):
                continue
            # 경로 순회 시퀀스가 포함된 path 필드 차단
            path = version.get("path", "")
            if isinstance(path, str) and (".." in path or path.startswith("/")):
                raise ValueError(f"매니페스트 경로에 경로 순회가 감지되었습니다: {path}")


def load_manifest(manifest_path: Path) -> dict:
    try:
        with open(manifest_path, encoding="utf-8") as f:
            data = json.load(f)
        _validate_manifest_schema(data)
        return data
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to load manifest: %s", exc)
        return {"schema_version": "1.0", "drivers": []}
    except ValueError as exc:
        logger.error("매니페스트 스키마 검증 실패: %s", exc)
        return {"schema_version": "1.0", "drivers": []}


def compare_device_to_manifest(device: dict, manifest: dict) -> Optional[dict]:
    """
    Match a detected device against the manifest and return comparison result.

    Returns dict with update info, or None if no matching driver found.
    """
    installed_version = device.get("driver_version", "0.0.0.0")
    device_hwids = device.get("hardware_ids", [])
    device_class = device.get("device_class", "")
    device_name = device.get("device_name", "")

    for driver_entry in manifest.get("drivers", []):
        driver_hwids = driver_entry.get("hardware_ids", [])
        driver_class = driver_entry.get("class", "")

        matched = False
        if device_hwids and driver_hwids:
            matched = _hardware_ids_match(device_hwids, driver_hwids)
        elif device_class and driver_class:
            matched = _class_matches(device_class, driver_class)

        if not matched:
            # 이름 기반 퍼지 매칭 (HWID 매칭 실패 시 fallback)
            # "intel"은 칩셋/ME/WiFi 등 모든 Intel 기기에 과다 매칭되므로 제외
            driver_name_lower = driver_entry.get("name", "").lower()
            device_name_lower = device_name.lower()
            vendor = driver_entry.get("vendor", "").lower()
            if vendor and vendor in device_name_lower:
                for kw in ["geforce", "radeon", "realtek", "bluetooth", "wi-fi", "wifi", "audio", "lan"]:
                    if kw in driver_name_lower and kw in device_name_lower:
                        matched = True
                        break

        if not matched:
            continue

        versions = driver_entry.get("versions", [])
        if not versions:
            continue

        latest_version_entry = versions[0]
        latest_version = latest_version_entry.get("version", "0.0.0.0")
        vendor_name = driver_entry.get("vendor", "")

        # 벤더별 버전 형식 정규화 후 비교 (예: NVIDIA Windows 4-part → NVIDIA 2-part)
        normalized_installed = _normalize_installed_version(installed_version, latest_version, vendor_name)
        update_available = version_gt(latest_version, normalized_installed)

        # device_class가 비어있으면 manifest의 class를 fallback으로 사용
        final_class = device_class if device_class else driver_entry.get("class", "Other")

        return {
            "driver_id": driver_entry.get("id"),
            "driver_name": driver_entry.get("name"),
            "vendor": vendor_name,
            "device_name": device_name,
            "device_class": final_class,
            "installed_version": normalized_installed,
            "latest_bundled": latest_version,
            "latest_path": latest_version_entry.get("path", ""),
            "latest_inf": latest_version_entry.get("inf", ""),
            "download_url": latest_version_entry.get("download_url", ""),
            "update_available": update_available,
            "all_versions": [v.get("version") for v in versions],
        }

    return None


def get_update_list(devices: list[dict], manifest: dict) -> list[dict]:
    """
    Cross-reference detected devices with manifest.
    Returns list of comparison results where update_available=True or matched.
    """
    results: list[dict] = []

    for device in devices:
        comparison = compare_device_to_manifest(device, manifest)
        if comparison:
            results.append(comparison)

    updates = [r for r in results if r["update_available"]]
    logger.info(
        "Version comparison complete: %d matches, %d updates available",
        len(results),
        len(updates),
    )
    return results
