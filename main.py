"""Driver Manager Pro — Entry point.

수정 이력:
  2026-05-22 - onefile EXE 실행 시 UI 경로 오류 수정
               sys._MEIPASS(내장 리소스)와 EXE 폴더(쓰기 데이터)를 분리
  2026-05-23 - _ensure_manifest(): 최초 실행 시 번들 manifest 자동 복사 추가
  2026-05-27 - GUI 백엔드를 pywebview → PyQt6 QtWebEngine + QtWebChannel로 교체.
               외부 런타임(.NET, WebView2) 의존성 제거. API 클래스를 QObject로 전환,
               각 메서드는 @pyqtSlot 데코레이터로 JS에서 호출 가능하게 등록.
               긴 블로킹 작업은 별도 QThread에서 실행하여 GUI 응답성 유지.
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

from PyQt6.QtCore import QObject, QThread, QUrl, pyqtSlot
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication, QMainWindow


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


def _jdump(value) -> str:
    """JS 측에서 자동 파싱되도록 JSON 문자열로 직렬화한다.

    qtbridge.js는 콜백 결과가 JSON 형식 문자열이면 자동 파싱하여 객체로 변환한다.
    한글 등 비ASCII가 그대로 보존되도록 ensure_ascii=False.
    """
    return json.dumps(value, ensure_ascii=False)


class API(QObject):
    """JS ↔ Python 브릿지 객체.

    qtbridge.js가 `window.pywebview.api`로 노출하여 기존 app.js 호출 규약을 유지한다.
    모든 슬롯은 별도 QThread에서 실행되어 GUI 메인 스레드를 차단하지 않는다.
    복합 반환값(dict/list)은 JSON 문자열로 직렬화하여 전달하면 JS 측에서 자동 파싱한다.
    """

    # ── Hardware ──────────────────────────────────────────────────────────────

    @pyqtSlot(result=str)
    def scan_hardware(self) -> str:
        logger.info("API: scan_hardware()")
        try:
            return _jdump(scan_hardware())
        except Exception as exc:
            logger.error("scan_hardware error: %s", exc)
            return _jdump([])

    @pyqtSlot(result=str)
    def get_system_summary(self) -> str:
        try:
            return _jdump(get_system_summary())
        except Exception as exc:
            logger.error("get_system_summary error: %s", exc)
            return _jdump({})

    # ── Driver comparison ─────────────────────────────────────────────────────

    @pyqtSlot(result=str)
    def get_update_list(self) -> str:
        logger.info("API: get_update_list()")
        try:
            devices = scan_hardware()
            manifest = load_manifest(_manifest_path())
            return _jdump(get_update_list(devices, manifest))
        except Exception as exc:
            logger.error("get_update_list error: %s", exc)
            return _jdump([])

    # ── Installation ──────────────────────────────────────────────────────────

    @pyqtSlot("QVariantList")
    def start_install(self, driver_ids) -> None:
        logger.info("API: start_install(%s)", driver_ids)
        try:
            settings = _load_settings()
            # manifest.json이 위치한 폴더 이름 (기본값: "drivers")
            download_path = settings.get("download_path", "drivers")

            manifest = load_manifest(_manifest_path())
            devices = scan_hardware()
            all_updates = get_update_list(devices, manifest)

            if driver_ids:
                # QVariantList는 Python list로 그대로 들어온다.
                ids = list(driver_ids)
                raw_queue = [d for d in all_updates if d.get("driver_id") in ids]
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

    @pyqtSlot()
    def abort_install(self) -> None:
        abort_install()

    @pyqtSlot(result=str)
    def get_progress(self) -> str:
        return _jdump(get_progress())

    # ── Online / DB download ─────────────────────────────────────────────────

    @pyqtSlot(result=str)
    def check_online_updates(self) -> str:
        logger.info("API: check_online_updates()")
        online = check_connectivity()
        db_exists = _has_driver_db()
        return _jdump({
            "online": online,
            "db_exists": db_exists,
            "download_state": get_download_state(),
        })

    @pyqtSlot()
    def download_driver_db(self) -> None:
        logger.info("API: download_driver_db()")
        start_download_thread()

    @pyqtSlot(result=str)
    def get_download_state(self) -> str:
        return _jdump(get_download_state())

    # ── Logs ──────────────────────────────────────────────────────────────────

    @pyqtSlot(result=str)
    def get_log_lines(self) -> str:
        return _jdump(get_all_log_lines())

    # ── Settings ──────────────────────────────────────────────────────────────

    @pyqtSlot(result=str)
    def get_settings(self) -> str:
        return _jdump(_load_settings())

    @pyqtSlot("QVariantMap")
    def save_settings(self, settings) -> None:
        logger.info("API: save_settings()")
        # QVariantMap은 Python dict로 들어온다. 키 정규화를 위해 dict()로 감싼다.
        _save_settings(dict(settings))

    # ── App self-update ───────────────────────────────────────────────────────

    @pyqtSlot(result=str)
    def check_app_update(self) -> str:
        logger.info("API: check_app_update()")
        try:
            return _jdump(check_app_update())
        except Exception as exc:
            logger.error("check_app_update error: %s", exc)
            return _jdump({"update_available": False, "error": str(exc)})

    @pyqtSlot(result=str)
    def get_install_results(self) -> str:
        return _jdump(get_install_results())

    @pyqtSlot()
    def reboot_system(self) -> None:
        import subprocess
        logger.info("Initiating system reboot in 30 seconds...")
        subprocess.Popen(["shutdown", "/r", "/t", "30"], creationflags=subprocess.CREATE_NO_WINDOW)

    @pyqtSlot(str, result=bool)
    def apply_app_update(self, download_url: str) -> bool:
        logger.info("API: apply_app_update()")
        return apply_update(download_url)

    # ── State queries ─────────────────────────────────────────────────────────

    @pyqtSlot(result=bool)
    def has_driver_db(self) -> bool:
        return _has_driver_db()

    @pyqtSlot(result=bool)
    def is_online(self) -> bool:
        return check_connectivity()

    @pyqtSlot(result=str)
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


def _icon_path() -> Path | None:
    """앱 아이콘 경로 반환. assets/icon.ico가 번들된 경우 사용."""
    candidates = [
        RESOURCE_DIR / "assets" / "icon.ico",
        BASE_DIR / "assets" / "icon.ico",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def main() -> None:
    logger.info("Driver Manager Pro starting...")

    # UAC check — GUI 초기화 전에 수행해야 한다.
    if not check_admin():
        logger.warning("Not running as administrator — relaunching with UAC...")
        relaunch_as_admin()
        return

    # 최초 실행 시 번들 manifest를 쓰기 가능한 데이터 디렉토리로 복사
    _ensure_manifest()

    # ── PyQt6 애플리케이션 초기화 ───────────────────────────────────────────
    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("Driver Manager Pro")

    icon = _icon_path()
    if icon is not None:
        qt_app.setWindowIcon(QIcon(str(icon)))

    window = QMainWindow()
    window.setWindowTitle("Driver Manager Pro")
    window.resize(1280, 800)
    window.setMinimumSize(900, 600)
    if icon is not None:
        window.setWindowIcon(QIcon(str(icon)))

    view = QWebEngineView(window)
    # 페이지 로드 전 어두운 배경으로 초기화하여 흰 플래시 방지
    view.page().setBackgroundColor(QColor("#101622"))
    window.setCentralWidget(view)

    # ── API 객체를 별도 QThread로 이동하여 GUI 차단 방지 ─────────────────────
    api = API()
    api_thread = QThread()
    api.moveToThread(api_thread)
    api_thread.start()

    channel = QWebChannel(view.page())
    channel.registerObject("api", api)
    view.page().setWebChannel(channel)

    # 로컬 HTML 로드
    ui_path = _find_ui()
    view.load(QUrl.fromLocalFile(str(ui_path)))

    logger.info("Launching UI window...")
    window.show()

    # 종료 시 워커 스레드 정리
    exit_code = qt_app.exec()
    api_thread.quit()
    api_thread.wait(3000)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
