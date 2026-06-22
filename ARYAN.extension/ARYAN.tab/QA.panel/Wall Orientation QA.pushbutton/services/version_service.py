# -*- coding: utf-8 -*-
"""Revit version detection service."""

import clr

clr.AddReference("RevitAPI")


class VersionService(object):
    """Detects and formats the active Revit application version."""

    MIN_SUPPORTED_YEAR = 2020
    MAX_SUPPORTED_YEAR = 2028

    @staticmethod
    def get_version_number(application):
        if application is None:
            return "Unknown"
        try:
            return str(application.VersionNumber)
        except Exception:
            return "Unknown"

    @staticmethod
    def get_version_name(application):
        if application is None:
            return "Unknown"
        try:
            return str(application.VersionName)
        except Exception:
            return "Unknown"

    @staticmethod
    def get_display_version(application):
        number = VersionService.get_version_number(application)
        name = VersionService.get_version_name(application)
        if number == "Unknown" and name == "Unknown":
            return "Unknown"
        return "{0} ({1})".format(number, name)

    @staticmethod
    def get_document_version(document):
        if document is None:
            return "Unknown"
        try:
            app = document.Application
            return VersionService.get_display_version(app)
        except Exception:
            return "Unknown"

    @staticmethod
    def get_supported_range_label():
        return "{0}-{1}".format(
            VersionService.MIN_SUPPORTED_YEAR,
            VersionService.MAX_SUPPORTED_YEAR
        )

    @staticmethod
    def is_supported_version(application):
        number = VersionService.get_version_number(application)
        try:
            year = int(number)
            return (
                VersionService.MIN_SUPPORTED_YEAR <= year <=
                VersionService.MAX_SUPPORTED_YEAR
            )
        except Exception:
            return True
