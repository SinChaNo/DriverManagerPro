"""Driver Manager Pro — Entry point.

수정 이력:
  2026-05-22 - onefile EXE 실행 시 UI 경로 오류 수정
               sys._MEIPASS(내장 리소스)와 EXE 폴더(쓰기 데이터)를 분리
  2026-05-23 - _ensure_manifest(): 최초 실행 시 번들 manifest 자동 복사 추가
"""

from __future__ import annotations

import json
import shutil
import sys
import threading
from pathlib import Path


def get_base_dir() -> Path:
    """쓰기 가능한 앱 데이터 경로 반환 (config, drivers, logs 등)."""
    if getattr(sys, "frozen", False):
        # onefile/onedir 모두 EXE 옆 폴더를 데이터 루트로 사용
        return Path(sys.executable).parent
    return Path(__file__).parent


def get_resource_dir() -> Path:
    """읽기 전용 내장 리소스 경로 반환 (ui, 번들 manifest 등).

    onefile 빌드 시 PyInstaller는 리소스를 sys._MEIPASS 임시 폴더에 압축 해제한다.
    onedir 빌드나 소스 실행 시에는 BASE_DIR과 동일하다.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).parent


BASE_DIR = get_base_dir()
RESOURCE_DIR = get_resource_dir()

# Ensure core is importable when running from source
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.logger import logger, get_all_log_lines
from core.hardware_detect import scan_hardware, get_system_summary
from core.driver_compare import load_manifest, get_update_list
from core.driver_install import (
    run_install_queue,
    abort_install,
    get_progress,
    get_install_results,
    check_admin,
    relaunch_as_admin,
)
from core.downloader import (
    check_connectivity,
    download_driver_db,
    get_download_state,
    start_download_thread,
)
from core.selfupdate import check_app_update, apply_update


def _load_settings() -> dict:
    try:
        with open(BASE_DIR / "config" / "settings.json", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_settings(data: dict) -> None:
    path = BASE_DIR / "config" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _manifest_path() -> Path:
    settings = _load_settings()
    return BASE_DIR / settings.get("download_path", "drivers") / "manifest.json"


def _has_driver_db() -> bool:
    mp = _manifest_path()
    if not mp.exists():
        return False
    try:
        with open(mp, encoding="utf-8") as f:
            data = json.load(f)
        return bool(data.get("drivers"))
    except Exception:
        return False


def _ensure_manifest() -> None:
    """최초 실행 시 번들 manifest를 쓰기 가능한 데이터 디렉토리로 복사한다.

    PyInstaller onedir 빌드 시 manifest는 _internal/(RESOURCE_DIR)에 번들되지만
    앱은 EXE 옆 drivers/(BASE_DIR)를 참조한다. 파일이 없으면 스캔 불가.
    """
    settings = _load_settings()
    download_path = settings.get("download_path", "drivers")
    dest = BASE_DIR / download_path / "manifest.json"
    if not dest.exists():
        src = RESOURCE_DIR / download_path / "manifest.json"
        if src.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            logger.info("번들 manifest를 데이터 디렉토리로 복사: %s", dest)


class API:
    """PyWebView JS bridge — all methods callable from window.pywebview.api."""

    # ── Hardware ──────────────────────────────────────────────────────────────

    def scan_hardware(self) -> list[dict]:
        logger.info("API: scan_hardware()")
        try:
            return scan_hardware()
        except Exception as exc:
            logger.error("scan_hardware error: %s", exc)
            return []

    def get_system_summary(self) -> dict:
        try:
            return get_system_summary()
        except Exception as exc:
            logger.error("get_system_summary error: %s", exc)
            return {}

    # ── Driver comparison ─────────────────────────────────────────────────────

    def get_update_list(self) -> list[dict]:
        logger.info("API: get_update_list()")
        try:
            devices = scan_hardware()
            manifest = load_manifest(_manifest_path())
            return get_update_list(devices, manifest)
        except Exception as exc:
            logger.error("get_update_list error: %s", exc)
            return []

    # ── Installation ──────────────────────────────────────────────────────────

    def start_install(self, driver_ids: list) -> None:
        logger.info("API: start_install(%s)", driver_ids)
        try:
            settings = _load_settings()
            # manifest.json이 위치한 폴더 이름 (기본값: "drivers")
            download_path = settings.get("download_path", "drivers")

            manifest = load_manifest(_manifest_path())
            devices = scan_hardware()
            all_updates = get_update_list(devices, manifest)

            if driver_ids:
                raw_queue = [d for d in all_updates if d.get("driver_id") in driver_ids]
            else:
                raw_queue = [d for d in all_updates if d.get("update_available")]

            # latest_path에 download_path 프리픽스 추가
            # manifest path 예: "nvidia/geforce/desktop/v572.83"
            # 실제 경로 필요: "drivers/nvidia/geforce/desktop/v572.83"
            queue = []
            for item in raw_queue:
                d = dict(item)
                raw = d.get("latest_path", "")
                if raw:
                    d["latest_path"] = str(Path(download_path) / raw)
                queue.append(d)

            def _run():
                run_install_queue(queue)

            t = threading.Thread(target=_run, daemon=True)
            t.start()
        except Exception as exc:
            logger.error("start_install error: %s", exc)

    def abort_install(self) -> None:
        abort_install()

    def get_progress(self) -> dict:
        return get_progress()

    # ── Online / DB download ─────────────────────────────────────────────────

    def check_online_updates(self) -> dict:
        logger.info("API: check_online_updates()")
        online = check_connectivity()
        db_exists = _has_driver_db()
        return {
            "online": online,
            "db_exists": db_exists,
            "download_state": get_download_state(),
        }

    def download_driver_db(self) -> None:
        logger.info("API: download_driver_db()")
        start_download_thread()

    def get_download_state(self) -> dict:
        return get_download_state()

    # ── Logs ──────────────────────────────────────────────────────────────────

    def get_log_lines(self) -> list[str]:
        return get_all_log_lines()

    # ── Settings ──────────────────────────────────────────────────────────────

    def get_settings(self) -> dict:
        return _load_settings()

    def save_settings(self, settings: dict) -> None:
        logger.info("API: save_settings()")
        _save_settings(settings)

    # ── App self-update ───────────────────────────────────────────────────────

    def check_app_update(self) -> dict:
        logger.info("API: check_app_update()")
        try:
            return check_app_update()
        except Exception as exc:
            logger.error("check_app_update error: %s", exc)
            return {"update_available": False, "error": str(exc)}

    def get_install_results(self) -> list[dict]:
        return get_install_results()

    def reboot_system(self) -> None:
        import subprocess
        logger.info("Initiating system reboot in 30 seconds...")
        subprocess.Popen(["shutdown", "/r", "/t", "30"], creationflags=subprocess.CREATE_NO_WINDOW)

    def apply_app_update(self, download_url: str) -> bool:
        logger.info("API: apply_app_update()")
        return apply_update(download_url)

    # ── State queries ─────────────────────────────────────────────────────────

    def has_driver_db(self) -> bool:
        return _has_driver_db()

    def is_online(self) -> bool:
        return check_connectivity()

    def get_app_version(self) -> str:
        # EXE 옆 config를 우선 확인하고, 없으면 번들 내장 파일 사용
        for base in (BASE_DIR, RESOURCE_DIR):
            try:
                with open(base / "config" / "app_version.json", encoding="utf-8") as f:
                    return json.load(f).get("version", "1.0.0")
            except Exception:
                continue
        return "1.0.0"


def _find_ui() -> Path:
    """번들 내장 UI 파일 경로 반환 (RESOURCE_DIR 기준)."""
    ui_path = RESOURCE_DIR / "ui" / "index.html"
    if not ui_path.exists():
        raise FileNotFoundError(f"UI not found at {ui_path}")
    return ui_path


def main() -> None:
    logger.info("Driver Manager Pro starting...")

    # UAC check
    if not check_admin():
        logger.warning("Not running as administrator — relaunching with UAC...")
        relaunch_as_admin()
        return

    # 최초 실행 시 번들 manifest를 쓰기 가능한 데이터 디렉토리로 복사
    _ensure_manifest()

    try:
        import webview  # type: ignore
    except ImportError:
        logger.error("pywebview not installed. Run: pip install pywebview")
        sys.exit(1)

    api = API()
    ui_path = _find_ui()

    window = webview.create_window(
        title="Driver Manager Pro",
        url=str(ui_path),
        js_api=api,
        width=1280,
        height=800,
        min_size=(900, 600),
        resizable=True,
        background_color="#101622",
    )

    logger.info("Launching UI window...")
    # pythonnet 없이 동작하는 EdgeChromium(WebView2) 백엔드 명시
    webview.start(gui="edgechromium", debug=False)


if __name__ == "__main__":
    main()
