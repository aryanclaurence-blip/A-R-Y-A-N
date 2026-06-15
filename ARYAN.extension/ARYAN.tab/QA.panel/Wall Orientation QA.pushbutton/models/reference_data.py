# -*- coding: utf-8 -*-
"""Reference data model for Wall Orientation QA."""

from compatibility_service import CompatibilityService


class ReferenceData(object):
    """Stores a reference element and its direction vector."""

    def __init__(self, element_id, unique_id, name, category_name, vector):
        self.ElementId = element_id
        self.UniqueId = unique_id
        self.Name = name
        self.CategoryName = category_name
        self.Vector = vector

    def to_log_string(self):
        return "{0} [{1}] Id:{2}".format(
            self.Name,
            self.CategoryName,
            CompatibilityService.get_element_id_value(self.ElementId)
        )
