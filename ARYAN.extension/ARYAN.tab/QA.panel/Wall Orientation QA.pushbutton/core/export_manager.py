# -*- coding: utf-8 -*-
"""CSV export manager for invalid walls."""

import os
import clr

clr.AddReference("PresentationFramework")
from Microsoft.Win32 import SaveFileDialog

from compatibility_service import CompatibilityService


class ExportManager(object):
    """Exports invalid wall results to CSV."""

    CSV_HEADER = "ElementId,UniqueId,WallType,Level,Angle"

    def __init__(self, logger=None):
        self._logger = logger

    def set_logger(self, logger):
        self._logger = logger

    def export_invalid_walls(self, invalid_results):
        if not invalid_results:
            if self._logger:
                self._logger.warn("No invalid walls to export.")
            return None

        file_path = self._prompt_save_path()
        if not file_path:
            if self._logger:
                self._logger.info("Export cancelled by user.")
            return None

        rows = [self.CSV_HEADER]
        for element_id, result in invalid_results.items():
            row = self._format_row(result)
            rows.append(row)

        self._write_csv(file_path, rows)

        if self._logger:
            self._logger.info(
                "CSV exported: {0} invalid wall(s) -> {1}".format(
                    len(invalid_results),
                    file_path
                )
            )

        return file_path

    def _prompt_save_path(self):
        dialog = SaveFileDialog()
        dialog.Title = "Export Invalid Walls"
        dialog.Filter = "CSV files (*.csv)|*.csv|All files (*.*)|*.*"
        dialog.DefaultExt = ".csv"
        dialog.FileName = "ARYAN_WallOrientationQA_InvalidWalls.csv"
        dialog.AddExtension = True
        dialog.OverwritePrompt = True

        result = dialog.ShowDialog()
        if result:
            return dialog.FileName
        return None

    def _format_row(self, result):
        element_id = CompatibilityService.get_element_id_value(result.ElementId)
        unique_id = self._escape_csv(result.UniqueId)
        wall_type = self._escape_csv(result.WallType)
        level = self._escape_csv(result.Level)
        angle = "{0:.2f}".format(float(result.Angle))
        return "{0},{1},{2},{3},{4}".format(
            element_id,
            unique_id,
            wall_type,
            level,
            angle
        )

    def _escape_csv(self, value):
        if value is None:
            return ""
        text = str(value)
        if "," in text or '"' in text or "\n" in text:
            text = text.replace('"', '""')
            return '"{0}"'.format(text)
        return text

    def _write_csv(self, file_path, rows):
        directory = os.path.dirname(file_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)

        with open(file_path, "w") as csv_file:
            for index, row in enumerate(rows):
                csv_file.write(row)
                if index < len(rows) - 1:
                    csv_file.write("\n")
