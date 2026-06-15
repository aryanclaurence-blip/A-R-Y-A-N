# -*- coding: utf-8 -*-
"""Version-safe Revit API compatibility wrappers (Revit 2020-2028)."""

import clr

clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import ElementId


class CompatibilityService(object):
    """Provides API wrappers that work across Revit 2020-2028."""

    SUPPORTED_MIN_YEAR = 2020
    SUPPORTED_MAX_YEAR = 2028

    @staticmethod
    def get_element_id_value(element_id):
        """
        Read ElementId as int across API generations.
        Revit 2024+: ElementId.Value (long)
        Revit 2020-2023: ElementId.IntegerValue (int)
        """
        if element_id is None:
            return -1
        try:
            return int(element_id.Value)
        except Exception:
            pass
        try:
            return int(element_id.IntegerValue)
        except Exception:
            pass
        return -1

    @staticmethod
    def invalid_element_id():
        try:
            return ElementId.InvalidElementId
        except Exception:
            pass
        try:
            return ElementId(-1)
        except Exception:
            return None

    @staticmethod
    def element_id_from_int(value):
        """
        Create ElementId from numeric value across API generations.
        """
        numeric = None
        try:
            numeric = long(value)
        except Exception:
            try:
                numeric = int(value)
            except Exception:
                return CompatibilityService.invalid_element_id()

        try:
            return ElementId(numeric)
        except Exception:
            pass
        try:
            return ElementId(int(numeric))
        except Exception:
            return CompatibilityService.invalid_element_id()

    @staticmethod
    def get_category_id_value(element):
        if element is None:
            return -1
        try:
            category = element.Category
            if category is None:
                return -1
            return CompatibilityService.get_element_id_value(category.Id)
        except Exception:
            return -1

    @staticmethod
    def element_ids_equal(element_id_a, element_id_b):
        return (
            CompatibilityService.get_element_id_value(element_id_a) ==
            CompatibilityService.get_element_id_value(element_id_b)
        )

    @staticmethod
    def is_valid_element_id(element_id):
        return CompatibilityService.get_element_id_value(element_id) > 0

    @staticmethod
    def safe_element_name(element):
        if element is None:
            return "Unknown"
        try:
            name = element.Name
            if name:
                return name
        except Exception:
            pass
        try:
            return element.Category.Name
        except Exception:
            pass
        return "Element {0}".format(
            CompatibilityService.get_element_id_value(element.Id)
        )

    @staticmethod
    def safe_category_name(element):
        if element is None:
            return "Unknown"
        try:
            if element.Category:
                return element.Category.Name
        except Exception:
            pass
        return "Unknown"

    @staticmethod
    def safe_unique_id(element):
        if element is None:
            return ""
        try:
            return element.UniqueId
        except Exception:
            return ""

    @staticmethod
    def safe_parameter_string(element, built_in_parameter):
        if element is None:
            return ""
        try:
            param = element.get_Parameter(built_in_parameter)
            if param and param.HasValue:
                value = param.AsString()
                if value:
                    return value
                value = param.AsValueString()
                if value:
                    return value
        except Exception:
            pass
        return ""

    @staticmethod
    def run_in_transaction(document, name, action):
        from Autodesk.Revit.DB import Transaction

        transaction = Transaction(document, name)
        transaction.Start()
        try:
            result = action()
            transaction.Commit()
            return result
        except Exception:
            if transaction.HasStarted() and not transaction.HasEnded():
                transaction.RollBack()
            raise
