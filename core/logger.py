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
_MAX_BUFFER = 500


def _make_handler() -> logging.FileHandler:
    log_dir = get_base_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"install_{datetime.now().strftime('%Y%m%d')}.log"
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    return handler


class _BufferHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        line = self.format(record)
        _log_lines.append(line)
        if len(_log_lines) > _MAX_BUFFER:
            _log_lines.pop(0)


def setup_logger(level_name: str = "INFO") -> logging.Logger:
    level = getattr(logging, level_name.upper(), logging.INFO)
    logger = logging.getLogger("dmp")
    logger.setLevel(level)
    if logger.handlers:
        return logger

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")

    buf_handler = _BufferHandler()
    buf_handler.setFormatter(fmt)
    logger.addHandler(buf_handler)

    try:
        file_handler = _make_handler()
        logger.addHandler(file_handler)
    except OSError:
        pass

    console = logging.StreamHandler(sys.stdout)
    if hasattr(console.stream, "reconfigure"):
        try:
            console.stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    console.setFormatter(fmt)
    logger.addHandler(console)

    return logger


def get_log_lines(since: int = 0) -> list[str]:
    return _log_lines[since:]


def get_all_log_lines() -> list[str]:
    return list(_log_lines)


logger = setup_logger()
