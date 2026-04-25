"""Tests for ``app.log_config.configure_logging``.

Logging config is process-global, so each test reaches into
``log_config._INSTALLED_HANDLERS`` to remove the handlers it
installed; otherwise records would accumulate across tests."""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

import pytest

from app import log_config


@pytest.fixture(autouse=True)
def _isolate_logging(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    yield
    root = logging.getLogger()
    for h in list(log_config._INSTALLED_HANDLERS):
        try:
            root.removeHandler(h)
            for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
                logging.getLogger(name).removeHandler(h)
            h.close()
        except Exception:
            pass
    log_config._INSTALLED_HANDLERS.clear()


def _flush_handlers():
    for h in log_config._INSTALLED_HANDLERS:
        h.flush()


def _read_app_log(tmp_path: Path) -> str:
    log_file = tmp_path / "logs" / "app.log"
    return log_file.read_text("utf-8") if log_file.exists() else ""


class TestHandlerInstallation:
    def test_installs_stderr_and_file_handler(self):
        log_config.configure_logging()
        types = {type(h).__name__ for h in log_config._INSTALLED_HANDLERS}
        assert "StreamHandler" in types
        assert "TimedRotatingFileHandler" in types

    def test_creates_log_dir_on_demand(self, tmp_path):
        log_dir = tmp_path / "logs"
        assert not log_dir.exists()
        log_config.configure_logging()
        assert log_dir.is_dir()

    def test_log_lines_reach_the_file(self, tmp_path):
        log_config.configure_logging()
        logging.getLogger("app.test").info("persistent line")
        _flush_handlers()
        contents = _read_app_log(tmp_path)
        assert "persistent line" in contents
        assert "INFO" in contents
        assert "app.test" in contents

    def test_log_lines_reach_stderr(self, capsys):
        log_config.configure_logging()
        logging.getLogger("app.test").info("stderr line")
        _flush_handlers()
        captured = capsys.readouterr()
        assert "stderr line" in captured.err

    def test_uvicorn_loggers_get_the_file_handler(self, tmp_path):
        """Uvicorn's loggers don't propagate to root by default, so we
        attach our file handler directly. Otherwise its access logs
        would never make it to the persistent file."""
        log_config.configure_logging()
        logging.getLogger("uvicorn.access").info("GET /foo 200")
        _flush_handlers()
        contents = _read_app_log(tmp_path)
        assert "GET /foo 200" in contents

    def test_repeated_calls_do_not_multiply_handlers(self):
        log_config.configure_logging()
        first = list(log_config._INSTALLED_HANDLERS)
        log_config.configure_logging()
        second = list(log_config._INSTALLED_HANDLERS)
        assert len(second) == len(first)
        # Old handlers were torn down, new ones replaced them.
        for h in first:
            assert h not in second


class TestRotationConfig:
    def test_daily_midnight_with_15_backups(self):
        log_config.configure_logging()
        file_handlers = [
            h for h in log_config._INSTALLED_HANDLERS
            if isinstance(h, logging.handlers.TimedRotatingFileHandler)
        ]
        assert len(file_handlers) == 1
        h = file_handlers[0]
        assert h.when == "MIDNIGHT"
        assert h.backupCount == 15
        assert h.utc is True


class TestFallback:
    def test_skips_file_handler_when_dir_cannot_be_created(
        self, monkeypatch, capsys,
    ):
        """A read-only volume mount must not crash startup. We log the
        failure and continue with stderr-only."""
        original_mkdir = Path.mkdir

        def boom(self, *args, **kwargs):
            if "logs" in self.parts:
                raise OSError("read-only filesystem")
            return original_mkdir(self, *args, **kwargs)

        monkeypatch.setattr(Path, "mkdir", boom)

        log_config.configure_logging()

        types = {type(h).__name__ for h in log_config._INSTALLED_HANDLERS}
        # Stderr is always installed; file is not.
        assert "StreamHandler" in types
        assert "TimedRotatingFileHandler" not in types
        # The failure was logged so an admin can see it via fly logs.
        captured = capsys.readouterr()
        assert "Persistent file logging disabled" in captured.err
        assert "read-only filesystem" in captured.err
