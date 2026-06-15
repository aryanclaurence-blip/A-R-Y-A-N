# -*- coding: utf-8 -*-
"""Main WPF window for Wall Orientation QA."""

import os
import sys
import clr

clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("PresentationFramework")
clr.AddReference("System")
clr.AddReference("WindowsBase")

from System import Action, TimeSpan
from System.Windows import MessageBox, MessageBoxButton, MessageBoxImage, WindowState, Duration
from System.Windows.Media import SolidColorBrush, Color
from System.Windows.Media.Animation import DoubleAnimation, Storyboard
from Autodesk.Revit.UI import IExternalEventHandler, ExternalEvent
from Autodesk.Revit.Exceptions import ApplicationException

from pyrevit import forms

BUNDLE_DIR = os.path.dirname(os.path.dirname(__file__))
for subfolder in ['core', 'models', 'services']:
    folder_path = os.path.join(BUNDLE_DIR, subfolder)
    if folder_path not in sys.path:
        sys.path.insert(0, folder_path)

from logger import QALogger
from reference_manager import ReferenceManager
from wall_analyzer import WallAnalyzer
from override_manager import OverrideManager
from export_manager import ExportManager
from statistics import QAStatistics

from version_service import VersionService
from selection_service import SelectionService
from view_service import ViewService


class RevitExternalHandler(IExternalEventHandler):
    """Routes UI button actions into the Revit API context."""

    REQUEST_NONE = "none"
    REQUEST_SELECT = "select"
    REQUEST_OVERRIDE = "override"
    REQUEST_EXPORT = "export"
    REQUEST_CLEAR = "clear"

    def __init__(self, window):
        self._window = window
        self.request = self.REQUEST_NONE

    def Execute(self, uiapp):
        restore_after = self.request == self.REQUEST_SELECT
        try:
            uidoc = uiapp.ActiveUIDocument
            if uidoc is None:
                self._window.report_error("No active UI document.")
                return

            document = uidoc.Document
            view = ViewService.get_active_view(document, uidoc)

            if self.request == self.REQUEST_SELECT:
                self._window.handle_select_references(uidoc)
            elif self.request == self.REQUEST_OVERRIDE:
                self._window.handle_override_view(document, uidoc, view)
            elif self.request == self.REQUEST_EXPORT:
                self._window.handle_export_invalid()
            elif self.request == self.REQUEST_CLEAR:
                self._window.handle_clear_overrides(document, uidoc, view)
        except ApplicationException as ex:
            self._window.report_error("Revit API error: {0}".format(str(ex)))
        except Exception as ex:
            self._window.report_error("Unexpected error: {0}".format(str(ex)))
        finally:
            self.request = self.REQUEST_NONE
            if restore_after:
                self._window.restore_from_selection()
            self._window.set_buttons_enabled(True)

    def GetName(self):
        return "Wall Orientation QA External Handler"


class WallOrientationQAWindow(forms.WPFWindow):
    """Enterprise dashboard for wall orientation QA."""

    def __init__(self, uidoc, document):
        xaml_path = os.path.join(os.path.dirname(__file__), "MainWindow.xaml")
        forms.WPFWindow.__init__(self, xaml_path)

        self._uidoc = uidoc
        self._document = document
        self._statistics = QAStatistics()
        self._is_hidden_for_selection = False

        self._logger = QALogger(self._append_log_safe)
        self._reference_manager = ReferenceManager(self._logger)
        self._wall_analyzer = WallAnalyzer(self._logger)
        self._override_manager = OverrideManager(self._logger)
        self._export_manager = ExportManager(self._logger)

        self._external_handler = RevitExternalHandler(self)
        self._external_event = ExternalEvent.Create(self._external_handler)

        self._wire_events()
        self._initialize_ui()

    def _wire_events(self):
        self.btnSelectReferences.Click += self._on_select_references_click
        self.btnOverrideView.Click += self._on_override_view_click
        self.btnExportInvalid.Click += self._on_export_invalid_click
        self.btnClearOverrides.Click += self._on_clear_overrides_click
        self.Closed += self._on_window_closed
        self.SizeChanged += self._on_size_changed

    def _initialize_ui(self):
        version_text = VersionService.get_display_version(self._document.Application)
        self.txtRevitVersion.Text = version_text
        self._logger.info("Revit Version: {0}".format(version_text))
        self._logger.info(
            "Supported Revit range: {0}".format(VersionService.get_supported_range_label())
        )
        if not VersionService.is_supported_version(self._document.Application):
            self._logger.warn(
                "Current Revit version is outside the tested range ({0}).".format(
                    VersionService.get_supported_range_label()
                )
            )
        self._logger.info("ARYAN — Wall Orientation QA initialized.")
        self._logger.info("Active view: {0}".format(
            ViewService.get_view_name(ViewService.get_active_view(self._document, self._uidoc))
        ))
        self._refresh_statistics()
        self.set_status("Ready", success=True)

    def _on_window_closed(self, sender, args):
        self._logger.info("ARYAN — Wall Orientation QA closed.")

    def _on_size_changed(self, sender, args):
        if self.ActualWidth < 860:
            self.FontSize = 12
        else:
            self.FontSize = 13

    def _set_buttons_enabled(self, enabled):
        self.btnSelectReferences.IsEnabled = enabled
        self.btnOverrideView.IsEnabled = enabled
        self.btnExportInvalid.IsEnabled = enabled
        self.btnClearOverrides.IsEnabled = enabled

    def set_buttons_enabled(self, enabled):
        if self.Dispatcher.CheckAccess():
            self._set_buttons_enabled(enabled)
        else:
            self.Dispatcher.Invoke(Action(lambda: self._set_buttons_enabled(enabled)))

    def _invoke_ui(self, action):
        if self.Dispatcher.CheckAccess():
            action()
        else:
            self.Dispatcher.Invoke(Action(action))

    def hide_for_selection(self):
        def _hide():
            self._is_hidden_for_selection = True
            self.Hide()
        self._invoke_ui(_hide)

    def restore_from_selection(self):
        def _restore():
            if not self._is_hidden_for_selection:
                return
            self._is_hidden_for_selection = False
            self.Show()
            self.WindowState = WindowState.Normal
            self.Activate()
            self.Topmost = True
            self.Topmost = False
            self._animate_window_restore()
        self._invoke_ui(_restore)

    def _animate_window_restore(self):
        try:
            self.Opacity = 0.0
            animation = DoubleAnimation(
                0.0,
                1.0,
                Duration(TimeSpan.FromMilliseconds(350))
            )
            self.BeginAnimation(self.OpacityProperty, animation)
        except Exception:
            self.Opacity = 1.0

    def _animate_stat_text(self, text_block):
        try:
            transform = text_block.RenderTransform
            if transform is None:
                return
            duration = Duration(TimeSpan.FromMilliseconds(120))
            storyboard = Storyboard()
            scale_x = DoubleAnimation(1.0, 1.08, duration)
            scale_x.AutoReverse = True
            scale_y = DoubleAnimation(1.0, 1.08, duration)
            scale_y.AutoReverse = True
            Storyboard.SetTarget(scale_x, text_block)
            Storyboard.SetTargetProperty(scale_x, "(UIElement.RenderTransform).(ScaleTransform.ScaleX)")
            Storyboard.SetTarget(scale_y, text_block)
            Storyboard.SetTargetProperty(scale_y, "(UIElement.RenderTransform).(ScaleTransform.ScaleY)")
            storyboard.Children.Add(scale_x)
            storyboard.Children.Add(scale_y)
            storyboard.Begin()
        except Exception:
            pass

    def _raise_request(self, request_type, status_message):
        self._external_handler.request = request_type
        self.set_status(status_message, success=False)
        self.set_buttons_enabled(False)
        self._external_event.Raise()

    def _on_select_references_click(self, sender, args):
        self._logger.info("UI minimized — select references in Revit, then click Finish.")
        self.set_status("Selecting in Revit… click Finish", success=False)
        self.hide_for_selection()
        self._raise_request(
            RevitExternalHandler.REQUEST_SELECT,
            "Selecting in Revit… click Finish"
        )

    def _on_override_view_click(self, sender, args):
        if not self._reference_manager.has_references():
            self.report_error("Select at least one reference before applying overrides.")
            return
        self._raise_request(
            RevitExternalHandler.REQUEST_OVERRIDE,
            "Analyzing walls and applying overrides..."
        )

    def _on_export_invalid_click(self, sender, args):
        invalid_results = self._wall_analyzer.get_invalid_results()
        if not invalid_results:
            self.report_error("No invalid walls available. Run Override Current View first.")
            return
        self._raise_request(
            RevitExternalHandler.REQUEST_EXPORT,
            "Exporting invalid walls..."
        )

    def _on_clear_overrides_click(self, sender, args):
        self._raise_request(
            RevitExternalHandler.REQUEST_CLEAR,
            "Clearing view overrides..."
        )

    def handle_select_references(self, uidoc):
        self._logger.info("Entering reference selection mode.")
        try:
            picked_elements = SelectionService.pick_reference_elements(uidoc, self._logger)
            if not picked_elements:
                self._logger.info("No new references selected.")
                self.set_status("Ready", success=True)
                return

            new_references = SelectionService.build_reference_data_list(
                picked_elements,
                self._logger
            )
            self._reference_manager.add_references(new_references)
            self._statistics.ReferenceCount = self._reference_manager.get_count()
            self._refresh_statistics(animate=True)
            self._logger.info("{0} references loaded.".format(self._statistics.ReferenceCount))
            self.set_status("References updated", success=True)
        finally:
            pass

    def handle_override_view(self, document, uidoc, view):
        if not self._reference_manager.has_references():
            self.report_error("Select at least one reference before analysis.")
            return

        if view is None:
            self.report_error("No active view found.")
            return

        if not ViewService.is_supported_view(view):
            self.report_error("The active view type is not supported for wall QA.")
            return

        self._logger.info("Analyzing walls in view: {0}".format(ViewService.get_view_name(view)))
        references = self._reference_manager.get_references()
        results = self._wall_analyzer.analyze(document, view, references)
        self._statistics.update_from_results(results)
        self._override_manager.apply_overrides(document, view, results)
        self._refresh_statistics(animate=True)
        self._logger.info("Overrides applied.")
        self.set_status("Analysis complete", success=True)

    def handle_export_invalid(self):
        invalid_results = self._wall_analyzer.get_invalid_results()
        if not invalid_results:
            self.report_error("No invalid walls to export.")
            return

        exported_path = self._export_manager.export_invalid_walls(invalid_results)
        if exported_path:
            self.set_status("CSV exported", success=True)
        else:
            self.set_status("Export cancelled", success=False)

    def handle_clear_overrides(self, document, uidoc, view):
        if view is None:
            self.report_error("No active view found.")
            return

        self._override_manager.clear_overrides(document, view)
        self.set_status("Overrides cleared", success=True)

    def _refresh_statistics(self, animate=False):
        self._statistics.ReferenceCount = self._reference_manager.get_count()
        results = self._wall_analyzer.get_results()
        if results:
            self._statistics.update_from_results(results)

        self.txtReferenceCountHeader.Text = str(self._statistics.ReferenceCount)
        self.txtStatReferenceCount.Text = str(self._statistics.ReferenceCount)
        self.txtStatParallel.Text = str(self._statistics.ParallelCount)
        self.txtStatPerpendicular.Text = str(self._statistics.PerpendicularCount)
        self.txtStatInvalid.Text = str(self._statistics.InvalidCount)

        if animate:
            self._animate_stat_text(self.txtStatReferenceCount)
            self._animate_stat_text(self.txtStatParallel)
            self._animate_stat_text(self.txtStatPerpendicular)
            self._animate_stat_text(self.txtStatInvalid)

    def _append_log_safe(self, message):
        self._invoke_ui(lambda: self._append_log(message))

    def _append_log(self, message):
        if self.txtLogOutput.Text:
            self.txtLogOutput.Text = self.txtLogOutput.Text + "\n" + message
        else:
            self.txtLogOutput.Text = message
        self.txtLogOutput.CaretIndex = len(self.txtLogOutput.Text)
        self.scrollLog.ScrollToEnd()

    def set_status(self, message, success=True):
        def _update():
            self.txtStatus.Text = message
            self.txtFooterStatus.Text = message
            if success:
                self.txtStatus.Foreground = SolidColorBrush(Color.FromRgb(61, 220, 151))
                self.statusPulseDot.Fill = SolidColorBrush(Color.FromRgb(61, 220, 151))
            else:
                self.txtStatus.Foreground = SolidColorBrush(Color.FromRgb(0, 212, 255))
                self.statusPulseDot.Fill = SolidColorBrush(Color.FromRgb(0, 212, 255))

        self._invoke_ui(_update)

    def report_error(self, message):
        self._logger.error(message)

        def _update_error():
            self.txtStatus.Text = "Error"
            self.txtFooterStatus.Text = message
            self.txtStatus.Foreground = SolidColorBrush(Color.FromRgb(255, 107, 107))
            self.statusPulseDot.Fill = SolidColorBrush(Color.FromRgb(255, 107, 107))

        self._invoke_ui(_update_error)

        try:
            MessageBox.Show(
                message,
                "ARYAN — Wall Orientation QA",
                MessageBoxButton.OK,
                MessageBoxImage.Warning
            )
        except Exception:
            pass
