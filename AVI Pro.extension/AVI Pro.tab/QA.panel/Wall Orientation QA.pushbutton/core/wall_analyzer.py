# -*- coding: utf-8 -*-
"""Wall orientation analysis engine."""

import clr

clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import BuiltInParameter

from wall_result import WallResult, WallStatus
from vector_service import VectorService
from compatibility_service import CompatibilityService
from view_service import ViewService


class WallAnalyzer(object):
    """Analyzes visible walls against stored reference vectors."""

    def __init__(self, logger=None):
        self._logger = logger
        self._results = {}

    def set_logger(self, logger):
        self._logger = logger

    def get_results(self):
        return dict(self._results)

    def clear_results(self):
        self._results = {}

    def analyze(self, document, view, references):
        self._results = {}

        if document is None:
            raise ValueError("Document is required for analysis.")
        if view is None:
            raise ValueError("Active view is required for analysis.")
        if not references:
            raise ValueError("At least one reference is required for analysis.")

        walls = ViewService.get_visible_walls(document, view)
        if self._logger:
            self._logger.info("Analyzing {0} visible wall(s).".format(len(walls)))

        for wall in walls:
            result = self._classify_wall(wall, references)
            if result is not None:
                self._results[wall.Id] = result

        if self._logger:
            parallel = 0
            perpendicular = 0
            invalid = 0
            for result in self._results.values():
                if result.Status == WallStatus.PARALLEL:
                    parallel += 1
                elif result.Status == WallStatus.PERPENDICULAR:
                    perpendicular += 1
                else:
                    invalid += 1
            self._logger.info(
                "Analysis complete: Parallel={0}, Perpendicular={1}, Invalid={2}".format(
                    parallel, perpendicular, invalid
                )
            )

        return self._results

    def _classify_wall(self, wall, references):
        wall_vector = VectorService.extract_from_wall(wall)
        if wall_vector is None:
            if self._logger:
                self._logger.warn(
                    "Wall {0} has no valid direction vector.".format(
                        CompatibilityService.get_element_id_value(wall.Id)
                    )
                )
            return self._build_result(
                wall,
                WallStatus.INVALID,
                90.0,
                "N/A"
            )

        status = WallStatus.INVALID
        best_angle = 90.0
        best_reference_name = "N/A"
        nearest_reference_name = "N/A"
        nearest_angle = 90.0

        is_parallel = False
        is_perpendicular = False

        for reference in references:
            ref_vector = reference.Vector
            if ref_vector is None:
                continue

            angle = VectorService.angle_degrees(wall_vector, ref_vector)

            if angle < nearest_angle:
                nearest_angle = angle
                nearest_reference_name = reference.Name

            if VectorService.is_parallel(wall_vector, ref_vector):
                is_parallel = True
                best_angle = angle
                best_reference_name = reference.Name

            if VectorService.is_perpendicular(wall_vector, ref_vector):
                is_perpendicular = True
                if not is_parallel:
                    best_angle = angle
                    best_reference_name = reference.Name

        if is_parallel:
            status = WallStatus.PARALLEL
        elif is_perpendicular:
            status = WallStatus.PERPENDICULAR
        else:
            status = WallStatus.INVALID
            best_angle = nearest_angle
            best_reference_name = nearest_reference_name

        return self._build_result(
            wall,
            status,
            best_angle,
            best_reference_name
        )

    def _build_result(self, wall, status, angle, reference_name):
        wall_type_name = self._get_wall_type_name(wall)
        level_name = self._get_level_name(wall)

        return WallResult(
            element_id=wall.Id,
            unique_id=CompatibilityService.safe_unique_id(wall),
            wall_type=wall_type_name,
            level=level_name,
            angle=round(angle, 2),
            status=status,
            reference_name=reference_name,
        )

    def _get_wall_type_name(self, wall):
        try:
            wall_type = wall.Document.GetElement(wall.GetTypeId())
            if wall_type is not None:
                name = wall_type.Name
                if name:
                    return name
        except Exception:
            pass
        return CompatibilityService.safe_parameter_string(
            wall,
            BuiltInParameter.ELEM_TYPE_PARAM
        ) or "Unknown"

    def _get_level_name(self, wall):
        try:
            level_id = wall.LevelId
            if CompatibilityService.is_valid_element_id(level_id):
                level = wall.Document.GetElement(level_id)
                if level is not None:
                    return CompatibilityService.safe_element_name(level)
        except Exception:
            pass
        return CompatibilityService.safe_parameter_string(
            wall,
            BuiltInParameter.WALL_BASE_CONSTRAINT
        ) or "Unknown"

    def get_invalid_results(self):
        invalid = {}
        for element_id, result in self._results.items():
            if result.is_invalid():
                invalid[element_id] = result
        return invalid
