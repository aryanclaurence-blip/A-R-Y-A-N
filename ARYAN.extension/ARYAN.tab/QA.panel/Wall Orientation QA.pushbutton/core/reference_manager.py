# -*- coding: utf-8 -*-
"""Reference storage manager."""

from reference_data import ReferenceData
from compatibility_service import CompatibilityService


class ReferenceManager(object):
    """Stores and manages reference direction vectors."""

    def __init__(self, logger=None):
        self._logger = logger
        self._references = []

    def set_logger(self, logger):
        self._logger = logger

    def add_references(self, reference_list):
        if not reference_list:
            return 0
        added = 0
        existing_ids = set()
        for existing in self._references:
            existing_ids.add(
                CompatibilityService.get_element_id_value(existing.ElementId)
            )
        for reference in reference_list:
            if isinstance(reference, ReferenceData):
                ref_id = CompatibilityService.get_element_id_value(reference.ElementId)
                if ref_id in existing_ids:
                    continue
                self._references.append(reference)
                existing_ids.add(ref_id)
                added += 1
        if self._logger and added > 0:
            self._logger.info("{0} reference(s) added.".format(added))
        return added

    def set_references(self, reference_list):
        self.clear_references()
        return self.add_references(reference_list)

    def clear_references(self):
        count = len(self._references)
        self._references = []
        if self._logger and count > 0:
            self._logger.info("References cleared.")
        return count

    def get_references(self):
        return list(self._references)

    def get_vectors(self):
        vectors = []
        for reference in self._references:
            if reference.Vector is not None:
                vectors.append(reference.Vector)
        return vectors

    def get_count(self):
        return len(self._references)

    def has_references(self):
        return len(self._references) > 0
