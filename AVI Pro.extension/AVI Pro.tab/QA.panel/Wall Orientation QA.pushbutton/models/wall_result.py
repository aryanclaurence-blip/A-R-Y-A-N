# -*- coding: utf-8 -*-
"""Wall analysis result model for Wall Orientation QA."""


class WallStatus(object):
    PARALLEL = "Parallel"
    PERPENDICULAR = "Perpendicular"
    INVALID = "Invalid"


class WallResult(object):
    """Stores classification and metadata for a single wall."""

    def __init__(
        self,
        element_id,
        unique_id,
        wall_type,
        level,
        angle,
        status,
        reference_name
    ):
        self.ElementId = element_id
        self.UniqueId = unique_id
        self.WallType = wall_type
        self.Level = level
        self.Angle = angle
        self.Status = status
        self.ReferenceName = reference_name

    def is_invalid(self):
        return self.Status == WallStatus.INVALID
