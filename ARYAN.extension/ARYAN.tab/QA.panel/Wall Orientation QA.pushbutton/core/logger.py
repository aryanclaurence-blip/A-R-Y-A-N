# -*- coding: utf-8 -*-
"""Centralized logging for Wall Orientation QA."""

import datetime


class QALogger(object):
    """Thread-safe style logger with optional UI callback."""

    LEVEL_INFO = "INFO"
    LEVEL_WARN = "WARN"
    LEVEL_ERROR = "ERROR"

    def __init__(self, ui_callback=None):
        self._ui_callback = ui_callback
        self._entries = []

    def set_ui_callback(self, callback):
        self._ui_callback = callback

    def _format_entry(self, level, message):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        return "[{0}] [{1}] {2}".format(timestamp, level, message)

    def _write(self, level, message):
        entry = self._format_entry(level, message)
        self._entries.append(entry)
        if self._ui_callback:
            try:
                self._ui_callback(entry)
            except Exception:
                pass

    def info(self, message):
        self._write(self.LEVEL_INFO, message)

    def warn(self, message):
        self._write(self.LEVEL_WARN, message)

    def error(self, message):
        self._write(self.LEVEL_ERROR, message)

    def get_all_entries(self):
        return list(self._entries)

    def clear(self):
        self._entries = []
