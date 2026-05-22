"""
Hardware and driver detection using WMI and pnputil.

수정 이력:
  - 2026-05-22: WMI DeviceClass 정규화(_normalize_class, _infer_class_from_name) 추가
                BIOS 버전 조회(get_bios_info) 및 get_system_summary에 통합
                _detect_via_wmi에 클래스 정규화/추론 적용
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field, asdict
from typing import Optional

from core.logger import logger

try:
    import wmi  # type: ignore
    _WMI_AVAILABLE = True
except ImportError:
    _WMI_AVAILABLE = False
    logger.warning("wmi module not available — falling back to pnputil only")


# WMI DeviceClass 값을 JS CAT 키로 정규화하는 매핑 테이블
_CLASS_NORMALIZE: dict[str, str] = {
    "display": "Display",
    "videocontroller": "Display",
    "net": "Net",
    "netclient": "Net",
    "netservice": "Net",
    "nettrans": "Net",
    "media": "Media",
    "audioendpoint": "AudioEndpoint",
    "sound": "Media",
    "system": "System",
    "computer": "System",
    "firmware": "System",
    "bluetooth": "Bluetooth",
    "usb": "USB",
    "usbdevice": "USB",
    "hidclass": "HIDClass",
    "mouse": "HIDClass",
    "keyboard": "HIDClass",
    "processor": "Processor",
    "diskdrive": "Storage",
    "hdc": "Storage",
    "scsiadapter": "Storage",
    "cdrom": "Storage",
    "volume": "Storage",
    "securitydevices": "Security",
    "biometric": "Security",
    "smartcard": "Security",
}


def _normalize_class(raw: str) -> str:
    """WMI DeviceClass 원시 값을 JS CAT 키로 정규화한다."""
    if not raw:
        return ""
    return _CLASS_NORMALIZE.get(raw.strip().lower(), raw.strip())


def _infer_class_from_name(name: str, hwid: str) -> str:
    """장치 이름/HardwareID 키워드로 클래스를 추론한다 (DeviceClass가 비어있을 때 사용)."""
    n = (name or "").lower()
    if any(k in n for k in ["geforce", "radeon", "graphics", "display", "gpu", "quadro", "firepro", "uhd", "iris"]):
        return "Display"
    if any(k in n for k in ["wi-fi", "wifi", "wireless lan", "ethernet", "network controller", "lan controller", "gigabit network"]):
        return "Net"
    if any(k in n for k in ["audio", "sound", "high definition audio", "realtek hd", "ac97", "hdaudio"]):
        return "Media"
    if "bluetooth" in n:
        return "Bluetooth"
    if "usb" in n and "controller" in n:
        return "USB"
    if any(k in n for k in ["management engine", "mei", "chipset device", "pch"]):
        return "System"
    return ""


@dataclass
class DeviceInfo:
    device_name: str
    vendor_id: str
    device_id: str
    driver_version: str
    driver_date: str
    device_class: str
    inf_name: str
    hardware_ids: list[str] = field(default_factory=list)
    manufacturer: str = ""
    status: str = "OK"

    def to_dict(self) -> dict:
        return asdict(self)


def _run(cmd: list[str]) -> str:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        return result.stdout
    except Exception as exc:
        logger.debug("Command %s failed: %s", cmd, exc)
        return ""


def _parse_version(raw: str) -> str:
    if not raw:
        return "0.0.0.0"
    cleaned = raw.strip().split(" ")[0]
    return cleaned if re.match(r"[\d.]+", cleaned) else "0.0.0.0"


def _parse_date(raw: str) -> str:
    if not raw:
        return ""
    raw = raw.strip()
    # WMI returns dates like "20240101000000.000000+000"
    if len(raw) >= 8 and raw[:8].isdigit():
        d = raw[:8]
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    return raw


def _detect_via_wmi() -> list[DeviceInfo]:
    """Win32_PnPSignedDriver로 설치된 드라이버 목록을 수집한다."""
    devices: list[DeviceInfo] = []
    try:
        c = wmi.WMI()
        for drv in c.Win32_PnPSignedDriver():
            try:
                raw_class = drv.DeviceClass or ""
                # DeviceClass 정규화 후, 빈 값이면 이름 키워드로 추론
                normalized = _normalize_class(raw_class)
                if not normalized:
                    normalized = _infer_class_from_name(
                        drv.DeviceName or "", drv.HardWareID or ""
                    )
                dev = DeviceInfo(
                    device_name=drv.DeviceName or "Unknown Device",
                    vendor_id=_extract_id(drv.HardWareID or "", "VEN_", "VID_"),
                    device_id=_extract_id(drv.HardWareID or "", "DEV_", "PID_"),
                    driver_version=_parse_version(drv.DriverVersion or ""),
                    driver_date=_parse_date(drv.DriverDate or ""),
                    device_class=normalized,
                    inf_name=drv.InfName or "",
                    hardware_ids=[drv.HardWareID] if drv.HardWareID else [],
                    manufacturer=drv.Manufacturer or "",
                )
                devices.append(dev)
            except Exception:
                continue
    except Exception as exc:
        logger.error("WMI scan error: %s", exc)
    return devices


def _extract_id(hwid: str, *prefixes: str) -> str:
    upper = hwid.upper()
    for prefix in prefixes:
        idx = upper.find(prefix)
        if idx != -1:
            start = idx + len(prefix)
            token = upper[start:start + 4]
            if len(token) == 4:
                return token
    return ""


def _detect_gpu_wmi() -> list[DeviceInfo]:
    if not _WMI_AVAILABLE:
        return []
    devices: list[DeviceInfo] = []
    try:
        c = wmi.WMI()
        for gpu in c.Win32_VideoController():
            dev = DeviceInfo(
                device_name=gpu.Name or "Unknown GPU",
                vendor_id=_extract_id(gpu.PNPDeviceID or "", "VEN_"),
                device_id=_extract_id(gpu.PNPDeviceID or "", "DEV_"),
                driver_version=_parse_version(gpu.DriverVersion or ""),
                driver_date=_parse_date(gpu.DriverDate or ""),
                device_class="Display",
                inf_name="",
                hardware_ids=[gpu.PNPDeviceID] if gpu.PNPDeviceID else [],
                manufacturer=gpu.AdapterCompatibility or "",
            )
            devices.append(dev)
    except Exception as exc:
        logger.debug("GPU WMI error: %s", exc)
    return devices


def _detect_via_pnputil() -> list[DeviceInfo]:
    """Fallback using pnputil /enum-drivers."""
    output = _run(["pnputil", "/enum-drivers"])
    devices: list[DeviceInfo] = []
    current: dict[str, str] = {}

    for line in output.splitlines():
        line = line.strip()
        if not line:
            if current:
                dev = DeviceInfo(
                    device_name=current.get("Original Name", current.get("Published Name", "Unknown")),
                    vendor_id="",
                    device_id="",
                    driver_version=_parse_version(current.get("Driver Version", "")),
                    driver_date="",
                    device_class=current.get("Class Name", ""),
                    inf_name=current.get("Published Name", ""),
                    manufacturer=current.get("Provider Name", ""),
                )
                devices.append(dev)
                current = {}
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            current[key.strip()] = val.strip()

    return devices


def scan_hardware() -> list[dict]:
    """Main entry point: return list of device dicts."""
    logger.info("Starting hardware scan...")

    devices: list[DeviceInfo] = []

    if _WMI_AVAILABLE:
        devices = _detect_via_wmi()
        # Supplement with explicit GPU scan
        gpu_devs = _detect_gpu_wmi()
        existing_names = {d.device_name for d in devices}
        for gpu in gpu_devs:
            if gpu.device_name not in existing_names:
                devices.append(gpu)
    else:
        devices = _detect_via_pnputil()

    # Filter out system/firmware entries with no version
    meaningful = [d for d in devices if d.device_class not in ("", "Unknown") or d.driver_version != "0.0.0.0"]

    logger.info("Hardware scan complete - %d devices found", len(meaningful))
    return [d.to_dict() for d in meaningful]


def get_bios_info() -> dict:
    """Win32_BIOS에서 BIOS 버전 및 제조사 정보를 반환한다."""
    if not _WMI_AVAILABLE:
        return {}
    try:
        c = wmi.WMI()
        bios_list = c.Win32_BIOS()
        if bios_list:
            b = bios_list[0]
            return {
                "version": (b.SMBIOSBIOSVersion or b.Version or "").strip() or "Unknown",
                "manufacturer": (b.Manufacturer or "").strip(),
                "date": _parse_date(b.ReleaseDate or ""),
            }
    except Exception as exc:
        logger.debug("BIOS info error: %s", exc)
    return {}


def get_system_summary() -> dict:
    """CPU / GPU / RAM / BIOS 요약 정보를 반환한다."""
    summary: dict[str, str] = {}

    try:
        import psutil
        ram_gb = round(psutil.virtual_memory().total / (1024 ** 3), 1)
        summary["ram"] = f"{ram_gb} GB"
    except Exception:
        summary["ram"] = "Unknown"

    if _WMI_AVAILABLE:
        try:
            c = wmi.WMI()
            cpus = c.Win32_Processor()
            if cpus:
                summary["cpu"] = cpus[0].Name.strip()
            # 통합 그래픽이 있는 경우 첫 번째 GPU를 표시 (내장 → 외장 순서)
            gpus = c.Win32_VideoController()
            if gpus:
                summary["gpu"] = gpus[0].Name.strip()
        except Exception:
            pass

    # BIOS 버전 추가
    bios = get_bios_info()
    if bios:
        summary["bios_version"] = bios.get("version", "Unknown")
        summary["bios_date"] = bios.get("date", "")
        summary["bios_manufacturer"] = bios.get("manufacturer", "")

    return summary
