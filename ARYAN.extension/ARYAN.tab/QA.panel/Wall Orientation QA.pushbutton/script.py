# -*- coding: utf-8 -*-
"""
ARYAN extension — Wall Orientation QA feature.
pyRevit entry script.
"""

import os
import sys

__title__ = "Wall Orientation QA"
__author__ = "ARYAN"
__doc__ = "ARYAN feature: enterprise-grade wall orientation validation in the active view."

BUNDLE_DIR = os.path.dirname(__file__)

for subfolder in ["core", "models", "services", "ui"]:
    folder_path = os.path.join(BUNDLE_DIR, subfolder)
    if folder_path not in sys.path:
        sys.path.insert(0, folder_path)

from pyrevit import revit, forms
from main_window import WallOrientationQAWindow


def _validate_environment():
    uidoc = revit.uidoc
    document = revit.doc

    if uidoc is None or document is None:
        forms.alert(
            "Open a Revit project before running Wall Orientation QA.",
            title="Wall Orientation QA",
            exitscript=True
        )

    if document.IsFamilyDocument:
        forms.alert(
            "Wall Orientation QA cannot run inside the Family Editor.",
            title="Wall Orientation QA",
            exitscript=True
        )

    return uidoc, document


active_uidoc, active_document = _validate_environment()
_qa_window = WallOrientationQAWindow(active_uidoc, active_document)
_qa_window.Show()
