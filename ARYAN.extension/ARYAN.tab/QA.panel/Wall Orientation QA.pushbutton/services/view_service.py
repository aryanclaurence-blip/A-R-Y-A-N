# -*- coding: utf-8 -*-
"""Active view and wall collection service."""

import clr

clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    FilteredElementCollector,
    BuiltInCategory,
    Wall,
    View,
    ViewType,
)


class ViewService(object):
    """Provides active view utilities and visible wall collection."""

    @staticmethod
    def get_active_view(document, uidocument):
        if uidocument is not None:
            try:
                view = uidocument.ActiveView
                if view is not None:
                    return view
            except Exception:
                pass
        if document is not None:
            try:
                return document.ActiveView
            except Exception:
                pass
        return None

    @staticmethod
    def is_supported_view(view):
        if view is None:
            return False
        if view.IsTemplate:
            return False
        supported = set([
            ViewType.FloorPlan,
            ViewType.CeilingPlan,
            ViewType.EngineeringPlan,
            ViewType.AreaPlan,
            ViewType.Section,
            ViewType.Elevation,
            ViewType.ThreeD,
            ViewType.DraftingView,
            ViewType.Detail,
        ])
        try:
            return view.ViewType in supported
        except Exception:
            return True

    @staticmethod
    def get_view_name(view):
        if view is None:
            return "No Active View"
        try:
            return view.Name
        except Exception:
            return "Unknown View"

    @staticmethod
    def get_visible_walls(document, view):
        if document is None or view is None:
            return []

        collector = FilteredElementCollector(document, view.Id)
        collector.OfCategory(BuiltInCategory.OST_Walls)
        collector.WhereElementIsNotElementType()

        walls = []
        for element in collector:
            if isinstance(element, Wall):
                walls.append(element)
        return walls

    @staticmethod
    def get_visible_wall_ids(document, view):
        walls = ViewService.get_visible_walls(document, view)
        return [wall.Id for wall in walls]
