"""
수정 이력:
  2026-05-22 - 세션별 로그 파일(날짜+시간), 버퍼 2000, 세션 구분선 함수 추가
               ERROR 레벨 exc_info 자동 포함 핸들러 적용
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


_log_lines: list[str] = []
_MAX_BUFFER = 2000  # 버퍼 500 → 2000으로 확대


def _make_handler() -> logging.FileHandler:
    log_dir = get_base_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    # 세션마다 고유한 로그 파일 생성 — 날짜+시간 포함
    log_file = log_dir / f"install_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    return handler


class _BufferHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        line = self.format(record)
        _log_lines.append(line)
        if len(_log_lines) > _MAX_BUFFER:
            _log_lines.pop(0)


class _ExcInfoErrorFilter(logging.Filter):
    """ERROR 이상 레벨에서 예외 정보가 없으면 자동으로 현재 예외를 첨부한다."""
    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.ERROR and not record.exc_info:
            import sys as _sys
            exc = _sys.exc_info()
            if exc[0] is not None:
                record.exc_info = exc
        return True


def setup_logger(level_name: str = "INFO") -> logging.Logger:
    level = getattr(logging, level_name.upper(), logging.INFO)
    log = logging.getLogger("dmp")
    log.setLevel(level)
    if log.handlers:
        return log

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    buf_handler = _BufferHandler()
    buf_handler.setFormatter(fmt)
    log.addHandler(buf_handler)

    try:
        file_handler = _make_handler()
        # 파일 핸들러는 DEBUG 레벨까지 전부 기록
        file_handler.setLevel(logging.DEBUG)
        log.addHandler(file_handler)
    except OSError:
        pass

    console = logging.StreamHandler(sys.stdout)
    if hasattr(console.stream, "reconfigure"):
        try:
            console.stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    console.setFormatter(fmt)
    log.addHandler(console)

    # ERROR 이상에서 활성 예외가 있으면 자동 첨부
    log.addFilter(_ExcInfoErrorFilter())

    return log


def get_log_lines(since: int = 0) -> list[str]:
    return _log_lines[since:]


def get_all_log_lines() -> list[str]:
    return list(_log_lines)


def log_session_start(label: str = "") -> None:
    """설치 세션 시작 구분선을 로그에 기록한다."""
    sep = "=" * 64
    logger.info(sep)
    logger.info("  SESSION START%s", f": {label}" if label else "")
    logger.info("  %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    logger.info(sep)


def log_session_end(label: str = "", success_count: int = 0, total: int = 0) -> None:
    """설치 세션 종료 구분선을 로그에 기록한다."""
    sep = "-" * 64
    logger.info(sep)
    if total:
        logger.info("  SESSION END%s  (%d/%d 성공)",
                    f": {label}" if label else "", success_count, total)
    else:
        logger.info("  SESSION END%s", f": {label}" if label else "")
    logger.info(sep)


logger = setup_logger()
