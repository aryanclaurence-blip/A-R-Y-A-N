# -*- coding: utf-8 -*-
"""Vector extraction and comparison service."""

import math
import clr

clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    Wall,
    Grid,
    ReferencePlane,
    LocationCurve,
    LocationPoint,
    XYZ,
    BuiltInCategory,
)

try:
    from Autodesk.Revit.DB import ModelLine, DetailLine
except ImportError:
    ModelLine = None
    DetailLine = None

from compatibility_service import CompatibilityService

PARALLEL_TOLERANCE = 1e-9
PERPENDICULAR_TOLERANCE = 1e-9


def _build_supported_element_types():
    types = [Wall, Grid, ReferencePlane]
    if ModelLine is not None:
        types.append(ModelLine)
    if DetailLine is not None:
        types.append(DetailLine)
    return tuple(types)


_SUPPORTED_ELEMENT_TYPES = _build_supported_element_types()


class VectorService(object):
    """Extracts and compares direction vectors from Revit elements."""

    SUPPORTED_CATEGORIES = set([
        int(BuiltInCategory.OST_Walls),
        int(BuiltInCategory.OST_Lines),
        int(BuiltInCategory.OST_Grids),
        int(BuiltInCategory.OST_CLines),
    ])

    @staticmethod
    def can_extract_vector(element):
        if element is None:
            return False
        try:
            if isinstance(element, _SUPPORTED_ELEMENT_TYPES):
                return True
            cat_id = CompatibilityService.get_category_id_value(element)
            if cat_id in VectorService.SUPPORTED_CATEGORIES:
                return True
        except Exception:
            pass
        return False

    @staticmethod
    def normalize_vector(vector):
        if vector is None:
            return None
        length = math.sqrt(
            vector.X * vector.X +
            vector.Y * vector.Y +
            vector.Z * vector.Z
        )
        if length < 1e-12:
            return None
        return XYZ(vector.X / length, vector.Y / length, vector.Z / length)

    @staticmethod
    def flatten_to_xy(vector):
        if vector is None:
            return None
        length = math.sqrt(vector.X * vector.X + vector.Y * vector.Y)
        if length < 1e-12:
            return None
        return XYZ(vector.X / length, vector.Y / length, 0.0)

    @staticmethod
    def prepare_vector(vector):
        normalized = VectorService.normalize_vector(vector)
        if normalized is None:
            return None
        return VectorService.flatten_to_xy(normalized)

    @staticmethod
    def dot_product(vector_a, vector_b):
        if vector_a is None or vector_b is None:
            return 0.0
        return (
            vector_a.X * vector_b.X +
            vector_a.Y * vector_b.Y +
            vector_a.Z * vector_b.Z
        )

    @staticmethod
    def is_parallel(vector_a, vector_b):
        dot = VectorService.dot_product(vector_a, vector_b)
        return abs(abs(dot) - 1.0) < PARALLEL_TOLERANCE

    @staticmethod
    def is_perpendicular(vector_a, vector_b):
        dot = VectorService.dot_product(vector_a, vector_b)
        return abs(dot) < PERPENDICULAR_TOLERANCE

    @staticmethod
    def angle_degrees(vector_a, vector_b):
        dot = VectorService.dot_product(vector_a, vector_b)
        clamped = max(-1.0, min(1.0, abs(dot)))
        return math.degrees(math.acos(clamped))

    @staticmethod
    def _direction_from_curve(curve):
        if curve is None:
            return None
        try:
            direction = curve.ComputeDerivatives(0.5, True).BasisX
            return VectorService.prepare_vector(direction)
        except Exception:
            pass
        try:
            point_a = curve.GetEndPoint(0)
            point_b = curve.GetEndPoint(1)
            delta = point_b - point_a
            return VectorService.prepare_vector(delta)
        except Exception:
            return None

    @staticmethod
    def extract_from_wall(wall):
        try:
            location = wall.Location
            if isinstance(location, LocationCurve):
                return VectorService._direction_from_curve(location.Curve)
            orientation = wall.Orientation
            if orientation:
                return VectorService.prepare_vector(orientation)
        except Exception:
            pass
        return None

    @staticmethod
    def extract_from_grid(grid):
        try:
            curve = grid.Curve
            return VectorService._direction_from_curve(curve)
        except Exception:
            return None

    @staticmethod
    def extract_from_line(line_element):
        try:
            location = line_element.Location
            if isinstance(location, LocationCurve):
                return VectorService._direction_from_curve(location.Curve)
        except Exception:
            pass
        return None

    @staticmethod
    def extract_from_reference_plane(reference_plane):
        try:
            bubble = reference_plane.BubbleEnd
            free = reference_plane.FreeEnd
            delta = free - bubble
            prepared = VectorService.prepare_vector(delta)
            if prepared is not None:
                return prepared
            normal = reference_plane.Normal
            return VectorService.prepare_vector(normal)
        except Exception:
            return None

    @staticmethod
    def extract_vector(element):
        if element is None:
            return None

        if isinstance(element, Wall):
            return VectorService.extract_from_wall(element)

        if isinstance(element, Grid):
            return VectorService.extract_from_grid(element)

        if ModelLine is not None and isinstance(element, ModelLine):
            return VectorService.extract_from_line(element)

        if DetailLine is not None and isinstance(element, DetailLine):
            return VectorService.extract_from_line(element)

        if isinstance(element, ReferencePlane):
            return VectorService.extract_from_reference_plane(element)

        try:
            cat_id = CompatibilityService.get_category_id_value(element)
            if cat_id >= 0:
                if cat_id == int(BuiltInCategory.OST_Grids):
                    return VectorService.extract_from_grid(element)
                if cat_id in (
                    int(BuiltInCategory.OST_Lines),
                    int(BuiltInCategory.OST_CLines),
                ):
                    return VectorService.extract_from_line(element)
                if cat_id == int(BuiltInCategory.OST_Walls):
                    return VectorService.extract_from_wall(element)
        except Exception:
            pass

        try:
            location = element.Location
            if isinstance(location, LocationCurve):
                return VectorService._direction_from_curve(location.Curve)
            if isinstance(location, LocationPoint):
                return None
        except Exception:
            pass

        return None
