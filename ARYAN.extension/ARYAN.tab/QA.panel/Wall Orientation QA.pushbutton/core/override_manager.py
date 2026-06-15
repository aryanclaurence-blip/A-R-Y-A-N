# -*- coding: utf-8 -*-
"""View graphic override manager."""

import clr

clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import OverrideGraphicSettings, Color

from wall_result import WallStatus
from view_service import ViewService
from compatibility_service import CompatibilityService


class OverrideManager(object):
    """Creates and applies reusable graphic overrides in the active view."""

    COLOR_PARALLEL = Color(0, 255, 0)
    COLOR_PERPENDICULAR = Color(0, 183, 255)
    COLOR_INVALID = Color(255, 59, 48)

    def __init__(self, logger=None):
        self._logger = logger
        self._parallel_settings = None
        self._perpendicular_settings = None
        self._invalid_settings = None
        self._clear_settings = None
        self._build_settings()

    def set_logger(self, logger):
        self._logger = logger

    def _build_settings(self):
        self._parallel_settings = self._create_color_override(self.COLOR_PARALLEL)
        self._perpendicular_settings = self._create_color_override(
            self.COLOR_PERPENDICULAR
        )
        self._invalid_settings = self._create_color_override(self.COLOR_INVALID)
        self._clear_settings = OverrideGraphicSettings()

    def _create_color_override(self, color):
        settings = OverrideGraphicSettings()
        settings.SetProjectionLineColor(color)
        settings.SetSurfaceForegroundPatternColor(color)
        settings.SetCutLineColor(color)
        settings.SetCutForegroundPatternColor(color)
        try:
            settings.SetSurfaceTransparency(20)
        except Exception:
            pass
        return settings

    def get_settings_for_status(self, status):
        if status == WallStatus.PARALLEL:
            return self._parallel_settings
        if status == WallStatus.PERPENDICULAR:
            return self._perpendicular_settings
        return self._invalid_settings

    def apply_overrides(self, document, view, results):
        if document is None or view is None:
            raise ValueError("Document and view are required.")
        if not results:
            if self._logger:
                self._logger.warn("No analysis results to override.")
            return 0

        def apply_action():
            count = 0
            for element_id, result in results.items():
                settings = self.get_settings_for_status(result.Status)
                view.SetElementOverrides(element_id, settings)
                count += 1
            return count

        count = CompatibilityService.run_in_transaction(
            document,
            "Wall Orientation QA - Apply Overrides",
            apply_action
        )

        if self._logger:
            self._logger.info("Overrides applied to {0} wall(s).".format(count))

        return count

    def clear_overrides(self, document, view):
        if document is None or view is None:
            raise ValueError("Document and view are required.")

        wall_ids = ViewService.get_visible_wall_ids(document, view)

        def clear_action():
            count = 0
            for wall_id in wall_ids:
                view.SetElementOverrides(wall_id, self._clear_settings)
                count += 1
            return count

        count = CompatibilityService.run_in_transaction(
            document,
            "Wall Orientation QA - Clear Overrides",
            clear_action
        )

        if self._logger:
            self._logger.info(
                "Overrides cleared for {0} visible wall(s).".format(count)
            )

        return count
