"""
Compare installed driver versions against manifest entries.

수정 이력:
  - 2026-05-22: device_class가 빈 값일 때 manifest의 class 필드를 fallback으로 사용하도록 수정
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from core.logger import logger


def _parse_version(version_str: str) -> tuple[int, ...]:
    """Convert version string to comparable int tuple."""
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


def _hardware_ids_match(device_hwids: list[str], driver_hwids: list[str]) -> bool:
    """Check if any hardware ID from device matches driver's hardware ID list."""
    device_upper = {h.upper() for h in device_hwids}
    for hwid in driver_hwids:
        if hwid.upper() in device_upper:
            return True
        # Partial match on VEN+DEV
        match = re.search(r"VEN_([0-9A-Fa-f]{4}).*DEV_([0-9A-Fa-f]{4})", hwid)
        if match:
            ven, dev = match.group(1).upper(), match.group(2).upper()
            for d_hwid in device_upper:
                if f"VEN_{ven}" in d_hwid and f"DEV_{dev}" in d_hwid:
                    return True
    return False


def _class_matches(device_class: str, driver_class: str) -> bool:
    return device_class.lower() == driver_class.lower()


def load_manifest(manifest_path: Path) -> dict:
    try:
        with open(manifest_path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to load manifest: %s", exc)
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
            # Name-based fuzzy fallback
            driver_name_lower = driver_entry.get("name", "").lower()
            device_name_lower = device_name.lower()
            vendor = driver_entry.get("vendor", "").lower()
            if vendor and vendor in device_name_lower:
                for kw in ["geforce", "radeon", "intel", "realtek", "bluetooth", "wi-fi", "wifi", "audio", "lan"]:
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

        update_available = version_gt(latest_version, installed_version)

        # device_class가 비어있으면 manifest의 class를 fallback으로 사용
        final_class = device_class if device_class else driver_entry.get("class", "Other")

        return {
            "driver_id": driver_entry.get("id"),
            "driver_name": driver_entry.get("name"),
            "vendor": driver_entry.get("vendor"),
            "device_name": device_name,
            "device_class": final_class,
            "installed_version": installed_version,
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
