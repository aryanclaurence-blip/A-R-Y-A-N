# -*- coding: utf-8 -*-
"""Reference element selection service."""

import clr

clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("System")

from System import InvalidOperationException
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException

from vector_service import VectorService
from compatibility_service import CompatibilityService


class ReferenceSelectionFilter(ISelectionFilter):
    """Allows only elements that provide a valid direction vector."""

    def AllowElement(self, element):
        return VectorService.can_extract_vector(element)

    def AllowReference(self, reference, point):
        return False


class SelectionService(object):
    """Handles interactive multi-selection of reference elements."""

    @staticmethod
    def pick_reference_elements(uidocument, logger):
        if uidocument is None:
            raise InvalidOperationException("No active UI document.")

        selection = uidocument.Selection
        document = uidocument.Document
        picked_elements = []

        try:
            references = selection.PickObjects(
                ObjectType.Element,
                ReferenceSelectionFilter(),
                "Select reference elements (Walls, Lines, Grids, Ref Planes). "
                "Press Finish or ESC when done."
            )
            for reference in references:
                element = document.GetElement(reference.ElementId)
                if element is not None:
                    picked_elements.append(element)
        except OperationCanceledException:
            if logger:
                logger.info("Selection cancelled by user.")
        except Exception as ex:
            if logger:
                logger.error("Selection error: {0}".format(str(ex)))
            raise

        return picked_elements

    @staticmethod
    def build_reference_data_list(elements, logger):
        from reference_data import ReferenceData

        references = []
        skipped = 0

        for element in elements:
            vector = VectorService.extract_vector(element)
            if vector is None:
                skipped += 1
                if logger:
                    logger.warn(
                        "Skipped element without valid vector: {0}".format(
                            CompatibilityService.safe_element_name(element)
                        )
                    )
                continue

            ref_data = ReferenceData(
                element_id=element.Id,
                unique_id=CompatibilityService.safe_unique_id(element),
                name=CompatibilityService.safe_element_name(element),
                category_name=CompatibilityService.safe_category_name(element),
                vector=vector,
            )
            references.append(ref_data)
            if logger:
                logger.info("Reference loaded: {0}".format(ref_data.to_log_string()))

        if skipped > 0 and logger:
            logger.warn("{0} element(s) skipped (no valid vector).".format(skipped))

        return references
