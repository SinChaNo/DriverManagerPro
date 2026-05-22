"""
Hardware and driver detection using WMI and pnputil.

수정 이력:
  - 2026-05-22: WMI DeviceClass 정규화(_normalize_class, _infer_class_from_name) 추가
                BIOS 버전 조회(get_bios_info) 및 get_system_summary에 통합
                _detect_via_wmi에 클래스 정규화/추론 적용
  - 2026-05-23: pnputil 한국어 로케일 필드명 매핑 추가 (_PNPUTIL_KEY_MAP)
                _parse_pnputil_version 추가: "MM/DD/YYYY 버전" 형식에서 순수 버전 번호 추출
                _detect_via_pnputil에 다국어 키 정규화 및 버전 파싱 적용
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


# pnputil /enum-drivers 필드명 정규화: 영어/한국어 로케일 모두 지원
_PNPUTIL_DRIVERS_KEY_MAP: dict[str, str] = {
    "Published Name": "Published Name",
    "Original Name": "Original Name",
    "Provider Name": "Provider Name",
    "Class Name": "Class Name",
    "Driver Version": "Driver Version",
    # 한국어
    "게시된 이름": "Published Name",
    "원래 이름": "Original Name",
    "공급자 이름": "Provider Name",
    "클래스 이름": "Class Name",
    "드라이버 버전": "Driver Version",
}

# pnputil /enum-devices /ids 필드명 정규화: 영어/한국어 로케일 모두 지원
_PNPUTIL_DEVICES_KEY_MAP: dict[str, str] = {
    "Instance ID": "Instance ID",
    "Device Description": "Device Description",
    "Class Name": "Class Name",
    "Class GUID": "Class GUID",
    "Manufacturer Name": "Manufacturer Name",
    "Status": "Status",
    "Driver Name": "Driver Name",
    "Hardware IDs": "Hardware IDs",
    "Compatible IDs": "Compatible IDs",
    # 한국어
    "인스턴스 ID": "Instance ID",
    "장치 설명": "Device Description",
    "클래스 이름": "Class Name",
    "클래스 GUID": "Class GUID",
    "제조업체 이름": "Manufacturer Name",
    "상태": "Status",
    "드라이버 이름": "Driver Name",
    "하드웨어 ID": "Hardware IDs",
    "호환 가능 ID": "Compatible IDs",
}


def _parse_pnputil_version(raw: str) -> str:
    """pnputil Driver Version 필드에서 순수 버전 번호를 추출한다.

    pnputil은 'MM/DD/YYYY VersionNumber' 형식으로 반환한다.
    슬래시가 포함된 날짜 토큰을 건너뛰고 숫자·점만으로 구성된 토큰을 반환한다.
    """
    if not raw:
        return "0.0.0.0"
    for token in raw.strip().split():
        # 숫자와 점만으로 구성된 토큰이 버전 번호
        if re.match(r"^\d[\d.]*$", token):
            return token
    return "0.0.0.0"


def _build_pnputil_version_map() -> dict[str, str]:
    """pnputil /enum-drivers로 {oem#.inf: version} 버전 맵을 빌드한다."""
    output = _run(["pnputil", "/enum-drivers"])
    result: dict[str, str] = {}
    current: dict[str, str] = {}

    for line in output.splitlines():
        line = line.strip()
        if not line:
            if current:
                pub_name = current.get("Published Name", "")
                ver = _parse_pnputil_version(current.get("Driver Version", ""))
                if pub_name:
                    result[pub_name] = ver
                current = {}
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            normalized_key = _PNPUTIL_DRIVERS_KEY_MAP.get(key.strip(), key.strip())
            current[normalized_key] = val.strip()

    return result


def _detect_via_pnputil() -> list[DeviceInfo]:
    """Fallback: pnputil /enum-devices /ids와 /enum-drivers를 사용해 장치 목록을 수집한다.

    /enum-devices /ids: 실제 장치명, Hardware ID, 클래스, 제조사 정보
    /enum-drivers: oem#.inf별 드라이버 버전 정보
    두 결과를 Driver Name(oem#.inf)으로 조인한다.
    """
    # 버전 맵 먼저 구축 {oem#.inf → version}
    version_map = _build_pnputil_version_map()

    output = _run(["pnputil", "/enum-devices", "/ids"])
    devices: list[DeviceInfo] = []
    current: dict[str, str] = {}
    hwids: list[str] = []
    last_key: str = ""

    def _flush() -> None:
        """현재 블록을 DeviceInfo로 변환하여 devices 리스트에 추가한다."""
        if not current:
            return
        driver_name = current.get("Driver Name", "")
        version = version_map.get(driver_name, "0.0.0.0")
        class_raw = current.get("Class Name", "")
        normalized_class = _normalize_class(class_raw)
        if not normalized_class:
            # 정규화 실패 시 원본 클래스명 유지
            normalized_class = class_raw
        primary_hwid = hwids[0] if hwids else ""
        dev = DeviceInfo(
            device_name=current.get("Device Description", "Unknown Device"),
            vendor_id=_extract_id(primary_hwid, "VEN_", "VID_"),
            device_id=_extract_id(primary_hwid, "DEV_", "PID_"),
            driver_version=version,
            driver_date="",
            device_class=normalized_class,
            inf_name=driver_name,
            hardware_ids=hwids[:],
            manufacturer=current.get("Manufacturer Name", ""),
        )
        devices.append(dev)

    for line in output.splitlines():
        # 들여쓰기로 시작하는 라인 = 이전 필드의 연속값 (Hardware IDs 등)
        if line and line[0] == " ":
            val = line.strip()
            if val and last_key == "Hardware IDs":
                hwids.append(val)
            continue

        stripped = line.strip()
        if not stripped:
            _flush()
            current = {}
            hwids = []
            last_key = ""
            continue

        if ":" in stripped:
            key, _, val = stripped.partition(":")
            normalized_key = _PNPUTIL_DEVICES_KEY_MAP.get(key.strip(), key.strip())
            val = val.strip()
            current[normalized_key] = val
            last_key = normalized_key
            # Hardware IDs 첫 번째 값은 키와 같은 라인에 있음
            if normalized_key == "Hardware IDs" and val:
                hwids.append(val)

    # 마지막 블록 처리 (출력 끝에 빈 줄이 없을 경우 대비)
    _flush()

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
