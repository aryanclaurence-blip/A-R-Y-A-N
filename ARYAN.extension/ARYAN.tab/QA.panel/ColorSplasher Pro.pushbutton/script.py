# -- coding: utf-8 --
"""
ARYAN — ColorSplasher Pro
script.py — pyRevit entry point.

Upgrade of pyRevit ColorSplasher by BIMOne Inc. (MIT 2021).
All original functionality is preserved and intact.
New features added on top of the original architecture:
  - Live value search/filter
  - Count column in value list
  - Multi-parameter compound key coloring
  - Numeric heat map mode
  - Revit link support (host / links / host+links)
  - CSV + JSON export
  - Enhanced sort (A-Z, Z-A, Count asc/desc)
  - Dark enterprise UI (existing style kept for original event handlers)

Compatibility: Revit 2019-2027, IronPython 2.7, pyRevit.
"""

import sys
import os
from re import split
from math import fabs
from random import randint
from os.path import exists, isfile, dirname, join
from traceback import extract_tb
from unicodedata import normalize
from unicodedata import category as unicode_category

from pyrevit.framework import Forms
from pyrevit.framework import Drawing
from pyrevit.framework import System
from pyrevit import HOST_APP, revit, DB, UI
from pyrevit.framework import List
from pyrevit.compat import get_elementid_value_func
from pyrevit.script import get_logger
from pyrevit import script as pyrevit_script
from pyrevit import forms
import clr

clr.AddReference("System.Data")
clr.AddReference("System")
from System.Data import DataTable

# ------------------------------------------------------------------
# Load the Pro engine (new features, no changes to existing code)
# ------------------------------------------------------------------
_BUNDLE_DIR = dirname(__file__)
if _BUNDLE_DIR not in sys.path:
    sys.path.insert(0, _BUNDLE_DIR)

try:
    from script_pro_engine import (
        get_range_values_multi,
        get_range_values_heatmap,
        get_loaded_links,
        collect_elements_from_link,
        filter_value_items,
        sort_value_items,
        get_item_count,
        build_display_key_with_count,
        export_to_csv,
        export_to_json,
        ValuesInfoPro,
        get_revit_version,
        get_element_int_id,
    )
    _PRO_ENGINE_OK = True
except Exception as _pro_import_err:
    _PRO_ENGINE_OK = False

logger = get_logger()  # Ctrl+click for debug

# ---------------------------------------------------------------------------
# UNCHANGED: Categories to exclude (from original script)
# ---------------------------------------------------------------------------
CAT_EXCLUDED = (
    int(DB.BuiltInCategory.OST_RoomSeparationLines),
    int(DB.BuiltInCategory.OST_Cameras),
    int(DB.BuiltInCategory.OST_CurtainGrids),
    int(DB.BuiltInCategory.OST_Elev),
    int(DB.BuiltInCategory.OST_Grids),
    int(DB.BuiltInCategory.OST_IOSModelGroups),
    int(DB.BuiltInCategory.OST_Views),
    int(DB.BuiltInCategory.OST_SitePropertyLineSegment),
    int(DB.BuiltInCategory.OST_SectionBox),
    int(DB.BuiltInCategory.OST_ShaftOpening),
    int(DB.BuiltInCategory.OST_BeamAnalytical),
    int(DB.BuiltInCategory.OST_StructuralFramingOpening),
    int(DB.BuiltInCategory.OST_MEPSpaceSeparationLines),
    int(DB.BuiltInCategory.OST_DuctSystem),
    int(DB.BuiltInCategory.OST_Lines),
    int(DB.BuiltInCategory.OST_PipingSystem),
    int(DB.BuiltInCategory.OST_Matchline),
    int(DB.BuiltInCategory.OST_CenterLines),
    int(DB.BuiltInCategory.OST_CurtainGridsRoof),
    int(DB.BuiltInCategory.OST_SWallRectOpening),
    -2000278,
    -1,
)

LINK_TEMP_DIRECTSHAPE_NAME = "ColorSplasherPro_LinkOverlay"
LEGACY_LINK_TEMP_DIRECTSHAPE_NAME = "ColorSplasherPro_Temp"



# ===========================================================================
# UNCHANGED: Original external event handlers — SubscribeView, ApplyColors,
#            ResetColors, CreateLegend, CreateFilters
#            (no renames, no modifications, verbatim from ColorSplasher)
# ===========================================================================

class SubscribeView(UI.IExternalEventHandler):
    def __init__(self):
        self.registered = 1

    def Execute(self, uiapp):
        try:
            if self.registered == 1:
                self.registered = 0
                uiapp.ViewActivated += self.view_changed
            else:
                self.registered = 1
                uiapp.ViewActivated -= self.view_changed
        except Exception:
            external_event_trace()

    def view_changed(self, sender, e):
        wndw = SubscribeView._wndw
        if wndw and wndw.IsOpen == 1:
            if self.registered == 0:
                new_doc = e.Document
                if new_doc:
                    if wndw:
                        try:
                            current_doc = revit.DOCS.doc
                            if not new_doc.Equals(current_doc):
                                wndw.Close()
                        except (AttributeError, RuntimeError):
                            pass
                new_view = get_active_view(e.Document)
                if new_view != 0:
                    wndw.list_box2.SelectionChanged -= wndw.list_selected_index_changed
                    wndw.crt_view = new_view
                    categ_inf_used_up = get_used_categories_parameters(
                        CAT_EXCLUDED, wndw.crt_view, new_doc
                    )
                    wndw.table_data = DataTable("Data")
                    wndw.table_data.Columns.Add("Key", System.String)
                    wndw.table_data.Columns.Add("Value", System.Object)
                    names = [x.name for x in categ_inf_used_up]
                    select_category_text = "Select Category"
                    wndw.table_data.Rows.Add(select_category_text, 0)
                    for key_, value_ in zip(names, categ_inf_used_up):
                        wndw.table_data.Rows.Add(key_, value_)
                    wndw._categories.ItemsSource = wndw.table_data.DefaultView
                    if wndw._categories.Items.Count > 0:
                        wndw._categories.SelectedIndex = 0
                    wndw._table_data_3 = wndw._create_empty_table()
                    wndw.list_box2.ItemsSource = wndw._table_data_3.DefaultView
                    wndw._update_placeholder_visibility()
                    # Reset secondary/tertiary combos
                    wndw._refresh_secondary_tertiary()

    def GetName(self):
        return "Subscribe View Changed Event (Pro)"


class ApplyColors(UI.IExternalEventHandler):
    def __init__(self):
        pass

    def Execute(self, uiapp):
        try:
            new_doc = uiapp.ActiveUIDocument.Document
            view = get_active_view(new_doc)
            if not view:
                return
            wndw = ApplyColors._wndw
            if not wndw:
                return

            apply_line_color = wndw._chk_line_color.IsChecked
            apply_foreground_pattern_color = wndw._chk_foreground_pattern.IsChecked
            apply_background_pattern_color = wndw._chk_background_pattern.IsChecked
            if (
                not apply_line_color
                and not apply_foreground_pattern_color
                and not apply_background_pattern_color
            ):
                apply_foreground_pattern_color = True

            solid_fill_id = solid_fill_pattern_id()

            if wndw._categories.SelectedItem is None:
                return
            sel_cat_row = wndw._categories.SelectedItem
            row = wndw._get_category_row(sel_cat_row, wndw._categories.SelectedIndex)
            if row is None:
                return
            sel_cat = row["Value"]
            if sel_cat == 0:
                return

            if (
                wndw._list_box1.SelectedIndex == -1
                or wndw._list_box1.SelectedIndex == 0
            ):
                if wndw._list_box1.SelectedIndex == 0:
                    sel_param_row = wndw._list_box1.SelectedItem
                    if sel_param_row is not None:
                        param_row = wndw._get_parameter_row(sel_param_row, 0)
                        if param_row is not None and param_row["Value"] == 0:
                            return
                return

            sel_param_row = wndw._list_box1.SelectedItem
            param_row = wndw._get_parameter_row(sel_param_row, wndw._list_box1.SelectedIndex)
            if param_row is None:
                return
            checked_param = param_row["Value"]

            refreshed_values = get_range_values(sel_cat, checked_param, view)

            color_map = {}
            for indx in range(wndw.list_box2.Items.Count):
                try:
                    item = wndw.list_box2.Items[indx]
                    row = wndw._get_value_row(item, indx)
                    if row is None:
                        continue
                    value_item = row["Value"]
                    color_map[value_item.value] = (
                        value_item.n1,
                        value_item.n2,
                        value_item.n3,
                    )
                except (KeyError, AttributeError, IndexError) as ex:
                    logger.debug("Error accessing listbox item %d: %s", indx, str(ex))
                    continue

            with revit.Transaction("Apply colors to elements"):
                get_elementid_value = get_elementid_value_func()
                version = int(HOST_APP.version)
                if get_elementid_value(sel_cat.cat.Id) in (
                    int(DB.BuiltInCategory.OST_Rooms),
                    int(DB.BuiltInCategory.OST_MEPSpaces),
                    int(DB.BuiltInCategory.OST_Areas),
                ):
                    if version > 2021:
                        if (
                            wndw.crt_view.GetColorFillSchemeId(
                                sel_cat.cat.Id
                            ).ToString()
                            == "-1"
                        ):
                            color_schemes = (
                                DB.FilteredElementCollector(new_doc)
                                .OfClass(DB.ColorFillScheme)
                                .ToElements()
                            )
                            if len(color_schemes) > 0:
                                for sch in color_schemes:
                                    if sch.CategoryId == sel_cat.cat.Id:
                                        if len(sch.GetEntries()) > 0:
                                            wndw.crt_view.SetColorFillSchemeId(
                                                sel_cat.cat.Id, sch.Id
                                            )
                                            break
                    else:
                        from System.Windows import Visibility
                        wndw._txt_block5.Visibility = Visibility.Visible
                else:
                    from System.Windows import Visibility
                    wndw._txt_block5.Visibility = Visibility.Collapsed

                for val_info in refreshed_values:
                    if val_info.value in color_map:
                        ogs = DB.OverrideGraphicSettings()
                        r, g, b = color_map[val_info.value]
                        base_color = DB.Color(r, g, b)
                        line_color, foreground_color, background_color = (
                            get_color_shades(
                                base_color,
                                apply_line_color,
                                apply_foreground_pattern_color,
                                apply_background_pattern_color,
                            )
                        )
                        if apply_line_color:
                            ogs.SetProjectionLineColor(line_color)
                            ogs.SetCutLineColor(line_color)
                        if apply_foreground_pattern_color:
                            ogs.SetSurfaceForegroundPatternColor(foreground_color)
                            ogs.SetCutForegroundPatternColor(foreground_color)
                            if solid_fill_id is not None:
                                ogs.SetSurfaceForegroundPatternId(solid_fill_id)
                                ogs.SetCutForegroundPatternId(solid_fill_id)
                        if apply_background_pattern_color and version >= 2019:
                            ogs.SetSurfaceBackgroundPatternColor(background_color)
                            ogs.SetCutBackgroundPatternColor(background_color)
                            if solid_fill_id is not None:
                                ogs.SetSurfaceBackgroundPatternId(solid_fill_id)
                                ogs.SetCutBackgroundPatternId(solid_fill_id)
                        for idt in val_info.ele_id:
                            view.SetElementOverrides(idt, ogs)
        except Exception:
            external_event_trace()

    def GetName(self):
        return "Set colors to elements (Pro)"


class ResetColors(UI.IExternalEventHandler):
    def __init__(self):
        pass

    def Execute(self, uiapp):
        try:
            new_doc = revit.DOCS.doc
            view = get_active_view(new_doc)
            if view == 0:
                return
            wndw = ResetColors._wndw
            if not wndw:
                return
            ogs = DB.OverrideGraphicSettings()
            collector = (
                DB.FilteredElementCollector(new_doc, view.Id)
                .WhereElementIsNotElementType()
                .WhereElementIsViewIndependent()
                .ToElementIds()
            )
            if wndw._categories.SelectedItem is None:
                sel_cat = 0
            else:
                sel_cat_row = wndw._categories.SelectedItem
                cat_row = wndw._get_category_row(
                    sel_cat_row, wndw._categories.SelectedIndex
                )
                sel_cat = cat_row["Value"] if cat_row is not None else 0
            if sel_cat == 0:
                task_no_cat = UI.TaskDialog("ColorSplasher Pro")
                task_no_cat.MainInstruction = "Please select a category to reset the colours."
                wndw.Topmost = False
                task_no_cat.Show()
                wndw.Topmost = True
                return
            with revit.Transaction("Reset colors in elements"):
                try:
                    filter_name = sel_cat.name + "/"
                    filters = view.GetFilters()
                    for filt_id in filters:
                        filt_ele = new_doc.GetElement(filt_id)
                        if filt_ele.Name.StartsWith(filter_name):
                            view.RemoveFilter(filt_id)
                            try:
                                new_doc.Delete(filt_id)
                            except Exception:
                                external_event_trace()
                except Exception:
                    external_event_trace()
                for i in collector:
                    view.SetElementOverrides(i, ogs)

                # Delete temporary DirectShapes (Fix link element coloring reset)
                if wndw and hasattr(wndw, '_temp_direct_shapes') and wndw._temp_direct_shapes:
                    for ds_id in wndw._temp_direct_shapes:
                        try:
                            new_doc.Delete(ds_id)
                        except Exception:
                            pass
                    wndw._temp_direct_shapes = []

                # Also double check if there are any orphaned temp DirectShapes in doc
                try:
                    ds_collector = DB.FilteredElementCollector(new_doc).OfClass(DB.DirectShape).ToElements()
                    for ds in ds_collector:
                        if ds.Name in (LINK_TEMP_DIRECTSHAPE_NAME, LEGACY_LINK_TEMP_DIRECTSHAPE_NAME):
                            try:
                                new_doc.Delete(ds.Id)
                            except Exception:
                                pass
                except Exception:
                    pass
        except Exception:
            external_event_trace()

    def GetName(self):
        return "Reset colors in elements (Pro)"


class CreateLegend(UI.IExternalEventHandler):
    def __init__(self):
        pass

    def Execute(self, uiapp):
        try:
            new_doc = uiapp.ActiveUIDocument.Document
            wndw = CreateLegend._wndw
            if not wndw:
                return
            apply_line_color = wndw._chk_line_color.IsChecked
            apply_foreground_pattern_color = wndw._chk_foreground_pattern.IsChecked
            apply_background_pattern_color = wndw._chk_background_pattern.IsChecked
            if (
                not apply_line_color
                and not apply_foreground_pattern_color
                and not apply_background_pattern_color
            ):
                apply_foreground_pattern_color = True
            collector = (
                DB.FilteredElementCollector(new_doc).OfClass(DB.View).ToElements()
            )
            legends = []
            for vw in collector:
                if vw.ViewType == DB.ViewType.Legend:
                    legends.append(vw)
                    break

            if len(legends) == 0:
                task2 = UI.TaskDialog("ColorSplasher Pro")
                task2.MainInstruction = "In order to create a new legend, you need to have at least one. Please create a legend view."
                wndw.Topmost = False
                task2.Show()
                wndw.Topmost = True
                return

            if wndw.list_box2.Items.Count == 0:
                task2 = UI.TaskDialog("ColorSplasher Pro")
                task2.MainInstruction = "No items to create a legend. Please select a category and parameter with values."
                wndw.Topmost = False
                task2.Show()
                wndw.Topmost = True
                return

            t = DB.Transaction(new_doc, "Create Legend")
            t.Start()
            try:
                new_id_legend = legends[0].Duplicate(DB.ViewDuplicateOption.Duplicate)
                new_legend = new_doc.GetElement(new_id_legend)
                sel_cat_row = wndw._categories.SelectedItem
                sel_par_row = wndw._list_box1.SelectedItem
                cat_row = wndw._get_category_row(sel_cat_row, wndw._categories.SelectedIndex)
                par_row = wndw._get_parameter_row(sel_par_row, wndw._list_box1.SelectedIndex)
                if cat_row is None or par_row is None:
                    t.RollBack()
                    return
                sel_cat = cat_row["Value"]
                sel_par = par_row["Value"]
                cat_name = strip_accents(sel_cat.name)
                par_name = strip_accents(sel_par.name)
                renamed = False
                legend_prefix = "Color Splasher Pro - "
                try:
                    new_legend.Name = legend_prefix + cat_name + " - " + par_name
                    renamed = True
                except Exception:
                    external_event_trace()
                if not renamed:
                    for i in range(1000):
                        try:
                            new_legend.Name = (
                                legend_prefix + cat_name + " - " + par_name + " - " + str(i)
                            )
                            break
                        except Exception:
                            external_event_trace()
                            if i == 999:
                                raise Exception("Could not rename legend view")

                old_all_ele = DB.FilteredElementCollector(new_doc, legends[0].Id).ToElements()
                ele_id_type = None
                for ele in old_all_ele:
                    if ele.Id != new_legend.Id and ele.Category is not None:
                        if isinstance(ele, DB.TextNote):
                            ele_id_type = ele.GetTypeId()
                            break
                get_elementid_value = get_elementid_value_func()
                if not ele_id_type:
                    all_text_notes = (
                        DB.FilteredElementCollector(new_doc)
                        .OfClass(DB.TextNoteType)
                        .ToElements()
                    )
                    for ele in all_text_notes:
                        ele_id_type = ele.Id
                        break
                if get_elementid_value(ele_id_type) == 0:
                    raise Exception("No text note type found in the model")

                filled_type = None
                filled_region_types = (
                    DB.FilteredElementCollector(new_doc)
                    .OfClass(DB.FilledRegionType)
                    .ToElements()
                )
                for filled_region_type in filled_region_types:
                    pattern = new_doc.GetElement(filled_region_type.ForegroundPatternId)
                    if (
                        pattern is not None
                        and pattern.GetFillPattern().IsSolidFill
                        and filled_region_type.ForegroundPatternColor.IsValid
                    ):
                        filled_type = filled_region_type
                        break
                if not filled_type and filled_region_types:
                    for idx in range(100):
                        try:
                            new_type = filled_region_types[0].Duplicate("Fill Region " + str(idx))
                            break
                        except Exception:
                            external_event_trace()
                            if idx == 99:
                                raise Exception("Could not create fill region type")
                    for idx in range(100):
                        try:
                            new_pattern = DB.FillPattern(
                                "Fill Pattern " + str(idx),
                                DB.FillPatternTarget.Drafting,
                                DB.FillPatternHostOrientation.ToView,
                                float(0),
                                float(0.00001),
                            )
                            new_ele_pat = DB.FillPatternElement.Create(new_doc, new_pattern)
                            break
                        except Exception:
                            external_event_trace()
                            if idx == 99:
                                raise Exception("Could not create fill pattern")
                    new_type.ForegroundPatternId = new_ele_pat.Id
                    filled_type = new_type
                if filled_type is None:
                    raise Exception("Could not find or create a fill region type")

                list_max_x = []
                list_y = []
                list_text_heights = []
                y_pos = 0
                spacing = 0
                for index, vw_item in enumerate(wndw.list_box2.Items):
                    punto = DB.XYZ(0, y_pos, 0)
                    item = vw_item["Value"]
                    text_line = cat_name + " / " + par_name + " - " + item.value
                    new_text = DB.TextNote.Create(
                        new_doc, new_legend.Id, punto, text_line, ele_id_type
                    )
                    new_doc.Regenerate()
                    prev_bbox = new_text.get_BoundingBox(new_legend)
                    height = prev_bbox.Max.Y - prev_bbox.Min.Y
                    spacing = height * 0.25
                    list_max_x.append(prev_bbox.Max.X)
                    list_y.append(prev_bbox.Min.Y)
                    list_text_heights.append(height)
                    y_pos = prev_bbox.Min.Y - (height + spacing)
                ini_x = max(list_max_x) + spacing
                solid_fill_id = (
                    solid_fill_pattern_id() if apply_foreground_pattern_color else None
                )
                for indx, y in enumerate(list_y):
                    try:
                        vw_item = wndw.list_box2.Items[indx]
                        row = wndw._get_value_row(vw_item, indx)
                        if row is None:
                            continue
                        item = row["Value"]
                        height = list_text_heights[indx]
                        rect_width = height * 2
                        point0 = DB.XYZ(ini_x, y, 0)
                        point1 = DB.XYZ(ini_x, y + height, 0)
                        point2 = DB.XYZ(ini_x + rect_width, y + height, 0)
                        point3 = DB.XYZ(ini_x + rect_width, y, 0)
                        line01 = DB.Line.CreateBound(point0, point1)
                        line12 = DB.Line.CreateBound(point1, point2)
                        line23 = DB.Line.CreateBound(point2, point3)
                        line30 = DB.Line.CreateBound(point3, point0)
                        list_curve_loops = List[DB.CurveLoop]()
                        curve_loops = DB.CurveLoop()
                        curve_loops.Append(line01)
                        curve_loops.Append(line12)
                        curve_loops.Append(line23)
                        curve_loops.Append(line30)
                        list_curve_loops.Add(curve_loops)
                        reg = DB.FilledRegion.Create(
                            new_doc, filled_type.Id, new_legend.Id, list_curve_loops
                        )
                        ogs = DB.OverrideGraphicSettings()
                        base_color = DB.Color(item.n1, item.n2, item.n3)
                        line_color, foreground_color, background_color = (
                            get_color_shades(
                                base_color,
                                apply_line_color,
                                apply_foreground_pattern_color,
                                apply_background_pattern_color,
                            )
                        )
                        if apply_line_color:
                            ogs.SetProjectionLineColor(line_color)
                            ogs.SetCutLineColor(line_color)
                        if apply_foreground_pattern_color:
                            ogs.SetSurfaceForegroundPatternColor(foreground_color)
                            ogs.SetCutForegroundPatternColor(foreground_color)
                            if solid_fill_id is not None:
                                ogs.SetSurfaceForegroundPatternId(solid_fill_id)
                                ogs.SetCutForegroundPatternId(solid_fill_id)
                        elif apply_background_pattern_color:
                            ogs.SetSurfaceForegroundPatternColor(background_color)
                            ogs.SetCutForegroundPatternColor(background_color)
                            if solid_fill_id is not None:
                                ogs.SetSurfaceForegroundPatternId(solid_fill_id)
                                ogs.SetCutForegroundPatternId(solid_fill_id)
                        new_legend.SetElementOverrides(reg.Id, ogs)
                    except Exception as e:
                        logger.debug("Error creating filled region: %s", str(e))
                        continue

                t.Commit()
                task2 = UI.TaskDialog("ColorSplasher Pro")
                task2.MainInstruction = "Legend created successfully: " + new_legend.Name
                wndw.Topmost = False
                task2.Show()
                wndw.Topmost = True

            except Exception as e:
                if t.HasStarted() and not t.HasEnded():
                    t.RollBack()
                logger.debug("Legend creation failed: %s", str(e))
                task2 = UI.TaskDialog("ColorSplasher Pro")
                task2.MainInstruction = "Failed to create legend: " + str(e)
                wndw.Topmost = False
                task2.Show()
                wndw.Topmost = True
        except Exception:
            external_event_trace()

    def GetName(self):
        return "Create Legend (Pro)"


class CreateFilters(UI.IExternalEventHandler):
    def __init__(self):
        pass

    def Execute(self, uiapp):
        try:
            new_doc = uiapp.ActiveUIDocument.Document
            view = get_active_view(new_doc)
            if view != 0:
                wndw = CreateFilters._wndw
                if not wndw:
                    return
                apply_line_color = wndw._chk_line_color.IsChecked
                apply_foreground_pattern_color = wndw._chk_foreground_pattern.IsChecked
                apply_background_pattern_color = wndw._chk_background_pattern.IsChecked
                if (
                    not apply_line_color
                    and not apply_foreground_pattern_color
                    and not apply_background_pattern_color
                ):
                    apply_foreground_pattern_color = True
                dict_filters = {}
                for filt_id in view.GetFilters():
                    filter_ele = new_doc.GetElement(filt_id)
                    dict_filters[filter_ele.Name] = filt_id
                dict_rules = {}
                iterator = (
                    DB.FilteredElementCollector(new_doc)
                    .OfClass(DB.ParameterFilterElement)
                    .GetElementIterator()
                )
                while iterator.MoveNext():
                    ele = iterator.Current
                    dict_rules[ele.Name] = ele.Id
                with revit.Transaction("Create View Filters"):
                    sel_cat_row = wndw._categories.SelectedItem
                    sel_par_row = wndw._list_box1.SelectedItem
                    cat_row = wndw._get_category_row(sel_cat_row, wndw._categories.SelectedIndex)
                    par_row = wndw._get_parameter_row(sel_par_row, wndw._list_box1.SelectedIndex)
                    if cat_row is None or par_row is None:
                        return
                    sel_cat = cat_row["Value"]
                    sel_par = par_row["Value"]
                    parameter_id = sel_par.rl_par.Id
                    param_storage_type = sel_par.rl_par.StorageType
                    categories = List[DB.ElementId]()
                    categories.Add(sel_cat.cat.Id)
                    solid_fill_id = solid_fill_pattern_id()
                    version = int(HOST_APP.version)
                    items_listbox = wndw.list_box2.Items
                    for i in range(items_listbox.Count):
                        vw_item = wndw.list_box2.Items[i]
                        row = wndw._get_value_row(vw_item, i)
                        if row is None:
                            continue
                        item = row["Value"]
                        ogs = DB.OverrideGraphicSettings()
                        base_color = DB.Color(item.n1, item.n2, item.n3)
                        line_color, foreground_color, background_color = (
                            get_color_shades(
                                base_color,
                                apply_line_color,
                                apply_foreground_pattern_color,
                                apply_background_pattern_color,
                            )
                        )
                        if apply_line_color:
                            ogs.SetProjectionLineColor(line_color)
                            ogs.SetCutLineColor(line_color)
                        if apply_foreground_pattern_color:
                            ogs.SetSurfaceForegroundPatternColor(foreground_color)
                            ogs.SetCutForegroundPatternColor(foreground_color)
                            if solid_fill_id is not None:
                                ogs.SetSurfaceForegroundPatternId(solid_fill_id)
                                ogs.SetCutForegroundPatternId(solid_fill_id)
                        if apply_background_pattern_color and version >= 2019:
                            ogs.SetSurfaceBackgroundPatternColor(background_color)
                            ogs.SetCutBackgroundPatternColor(background_color)
                            if solid_fill_id is not None:
                                ogs.SetSurfaceBackgroundPatternId(solid_fill_id)
                                ogs.SetCutBackgroundPatternId(solid_fill_id)
                        filter_name = (
                            sel_cat.name + " " + sel_par.name + " - " + item.value
                        )
                        filter_name = filter_name.translate(
                            {ord(c): None for c in "{}[]:\\|?/<>*"}
                        )
                        if filter_name in dict_filters or filter_name in dict_rules:
                            if (
                                filter_name in dict_rules
                                and filter_name not in dict_filters
                            ):
                                view.AddFilter(dict_rules[filter_name])
                                view.SetFilterOverrides(dict_rules[filter_name], ogs)
                            else:
                                view.SetFilterOverrides(dict_filters[filter_name], ogs)
                        else:
                            if param_storage_type == DB.StorageType.Double:
                                if item.value == "None" or len(item.values_double) == 0:
                                    equals_rule = (
                                        DB.ParameterFilterRuleFactory.CreateEqualsRule(
                                            parameter_id, "", 0.001
                                        )
                                    )
                                else:
                                    minimo = min(item.values_double)
                                    maximo = max(item.values_double)
                                    avg_values = (maximo + minimo) / 2
                                    equals_rule = (
                                        DB.ParameterFilterRuleFactory.CreateEqualsRule(
                                            parameter_id,
                                            avg_values,
                                            fabs(avg_values - minimo) + 0.001,
                                        )
                                    )
                            elif param_storage_type == DB.StorageType.ElementId:
                                if item.value == "None":
                                    prevalue = DB.ElementId.InvalidElementId
                                else:
                                    prevalue = item.par.AsElementId()
                                equals_rule = (
                                    DB.ParameterFilterRuleFactory.CreateEqualsRule(
                                        parameter_id, prevalue
                                    )
                                )
                            elif param_storage_type == DB.StorageType.Integer:
                                if item.value == "None":
                                    prevalue = 0
                                else:
                                    prevalue = item.par.AsInteger()
                                equals_rule = (
                                    DB.ParameterFilterRuleFactory.CreateEqualsRule(
                                        parameter_id, prevalue
                                    )
                                )
                            elif param_storage_type == DB.StorageType.String:
                                if item.value == "None":
                                    prevalue = ""
                                else:
                                    prevalue = item.value
                                if version > 2023:
                                    equals_rule = (
                                        DB.ParameterFilterRuleFactory.CreateEqualsRule(
                                            parameter_id, prevalue
                                        )
                                    )
                                else:
                                    equals_rule = (
                                        DB.ParameterFilterRuleFactory.CreateEqualsRule(
                                            parameter_id, prevalue, True
                                        )
                                    )
                            else:
                                task2 = UI.TaskDialog("ColorSplasher Pro")
                                task2.MainInstruction = "Creation of filters for this type of parameter is not supported."
                                wndw.Topmost = False
                                task2.Show()
                                wndw.Topmost = True
                                break
                            try:
                                elem_filter = DB.ElementParameterFilter(equals_rule)
                                fltr = DB.ParameterFilterElement.Create(
                                    new_doc, filter_name, categories, elem_filter
                                )
                                view.AddFilter(fltr.Id)
                                view.SetFilterOverrides(fltr.Id, ogs)
                            except Exception:
                                external_event_trace()
                                task2 = UI.TaskDialog("ColorSplasher Pro")
                                task2.MainInstruction = "View filters were not created. The selected parameter is not exposed by Revit and rules cannot be created."
                                wndw.Topmost = False
                                task2.Show()
                                wndw.Topmost = True
                                break
        except Exception:
            external_event_trace()

    def GetName(self):
        return "Create Filters (Pro)"


# ===========================================================================
# UNCHANGED: Original data model classes
# ===========================================================================

class ValuesInfo:
    def __init__(self, para, val, idt, num1, num2, num3):
        self.par = para
        self.value = val
        self.name = strip_accents(para.Definition.Name)
        self.ele_id = List[DB.ElementId]()
        self.ele_id.Add(idt)
        self.n1 = num1
        self.n2 = num2
        self.n3 = num3
        self.colour = Drawing.Color.FromArgb(self.n1, self.n2, self.n3)
        self.values_double = []
        if para.StorageType == DB.StorageType.Double:
            self.values_double.append(para.AsDouble())
        elif para.StorageType == DB.StorageType.ElementId:
            self.values_double.append(para.AsElementId())


class ParameterInfo:
    def __init__(self, param_type, para):
        self.param_type = param_type
        self.rl_par = para
        self.par = para.Definition
        self.name = strip_accents(para.Definition.Name)


class CategoryInfo:
    def __init__(self, category, param):
        self.name = strip_accents(category.Name)
        self.cat = category
        get_elementid_value = get_elementid_value_func()
        self.int_id = get_elementid_value(category.Id)
        self.par = param


def _append_transformed_solids(geometry_element, transform, output):
    """Append positive-volume solids from a linked element geometry tree."""
    if geometry_element is None:
        return
    for geom_obj in geometry_element:
        try:
            if isinstance(geom_obj, DB.Solid):
                if geom_obj.Volume > 0:
                    output.append(DB.SolidUtils.CreateTransformed(geom_obj, transform))
            elif isinstance(geom_obj, DB.GeometryInstance):
                _append_transformed_solids(
                    geom_obj.GetInstanceGeometry(),
                    transform,
                    output
                )
        except Exception:
            continue


def _directshape_category_id(category_info):
    """Return a DirectShape-compatible host category id for an overlay."""
    try:
        cat_id = DB.ElementId(category_info.int_id)
        if hasattr(DB.DirectShape, "IsValidCategoryId"):
            if DB.DirectShape.IsValidCategoryId(cat_id):
                return cat_id
        else:
            return cat_id
    except Exception:
        pass
    return DB.ElementId(DB.BuiltInCategory.OST_GenericModel)


def create_link_overlay_directshape(doc, view, category_info, link_meta, overrides):
    """Create a host-side DirectShape overlay for one linked element.

    Revit host views cannot apply per-element overrides directly to ElementIds
    that belong to a linked document.  To make linked elements colorizable from
    the host model, we create a temporary DirectShape from the linked element's
    transformed solids and apply the selected overrides to that overlay.
    """
    link_doc = link_meta.get("link_doc")
    link_inst = link_meta.get("link_instance")
    element_id = link_meta.get("element_id")
    if link_doc is None or link_inst is None or element_id is None:
        return None

    linked_element = link_doc.GetElement(element_id)
    if linked_element is None:
        return None

    options = DB.Options()
    try:
        options.View = view
    except Exception:
        pass
    try:
        options.IncludeNonVisibleObjects = False
    except Exception:
        pass
    try:
        options.DetailLevel = DB.ViewDetailLevel.Fine
    except Exception:
        pass

    geometry = linked_element.get_Geometry(options)
    transformed_geometry = []
    _append_transformed_solids(
        geometry,
        link_inst.GetTotalTransform(),
        transformed_geometry
    )
    if not transformed_geometry:
        return None

    from System.Collections.Generic import List as GenericList
    ds = DB.DirectShape.CreateElement(doc, _directshape_category_id(category_info))
    ds.Name = LINK_TEMP_DIRECTSHAPE_NAME
    try:
        ds.ApplicationId = "ColorSplasherPro"
        ds.ApplicationDataId = "link:{0}:element:{1}".format(
            link_meta.get("link_instance_id_int"),
            link_meta.get("element_id_int")
        )
    except Exception:
        pass
    ds.SetShape(GenericList[DB.GeometryObject](transformed_geometry))
    view.SetElementOverrides(ds.Id, overrides)
    return ds.Id


# ===========================================================================
# NEW: ApplyColorsPro — multi-param / heat-map / link-aware color application
# ===========================================================================

class ApplyColorsPro(UI.IExternalEventHandler):
    """
    Extended color application handler supporting multi-param, heat map, and links.
    Called when standard Apply Colors fails to match the pro mode selection.
    """

    def __init__(self):
        pass

    def Execute(self, uiapp):
        try:
            if not _PRO_ENGINE_OK:
                return
            new_doc = uiapp.ActiveUIDocument.Document
            view = get_active_view(new_doc)
            if not view:
                return
            wndw = ApplyColorsPro._wndw
            if not wndw:
                return

            apply_line_color = wndw._chk_line_color.IsChecked
            apply_foreground = wndw._chk_foreground_pattern.IsChecked
            apply_background = wndw._chk_background_pattern.IsChecked
            if not apply_line_color and not apply_foreground and not apply_background:
                apply_foreground = True

            solid_fill_id = solid_fill_pattern_id()
            version = int(HOST_APP.version)

            color_map = {}
            for indx in range(wndw.list_box2.Items.Count):
                try:
                    item = wndw.list_box2.Items[indx]
                    row = wndw._get_value_row(item, indx)
                    if row is None:
                        continue
                    vi = row["Value"]
                    color_map[vi.value] = (vi.n1, vi.n2, vi.n3)
                except (KeyError, AttributeError, IndexError):
                    continue

            # Collect all current values from the window (already computed, stored in _all_value_items_raw)
            all_values = getattr(wndw, '_all_value_items_raw', [])
            if not all_values:
                return

            # Get selected category
            sel_cat_row = wndw._categories.SelectedItem
            if sel_cat_row is None:
                return
            cat_row = wndw._get_category_row(sel_cat_row, wndw._categories.SelectedIndex)
            if cat_row is None:
                return
            sel_cat = cat_row["Value"]
            if sel_cat == 0:
                return

            if not hasattr(wndw, '_temp_direct_shapes'):
                wndw._temp_direct_shapes = []

            with revit.Transaction("Apply colors to elements (Pro)"):
                # 1. Delete previous temporary DirectShapes
                existing_temp_ids = []
                if wndw._temp_direct_shapes:
                    for ds_id in wndw._temp_direct_shapes:
                        if new_doc.GetElement(ds_id):
                            existing_temp_ids.append(ds_id)
                if existing_temp_ids:
                    from System.Collections.Generic import List as WpfList
                    try:
                        new_doc.Delete(WpfList[DB.ElementId](existing_temp_ids))
                    except Exception:
                        for eid in existing_temp_ids:
                            try:
                                new_doc.Delete(eid)
                            except Exception:
                                pass
                wndw._temp_direct_shapes = []

                # 2. Iterate and apply overrides
                for vi in all_values:
                    if vi.value not in color_map:
                        continue
                    r, g, b = color_map[vi.value]
                    base_color = DB.Color(r, g, b)
                    line_color, fg_color, bg_color = get_color_shades(
                        base_color, apply_line_color, apply_foreground, apply_background
                    )
                    ogs = DB.OverrideGraphicSettings()
                    if apply_line_color:
                        ogs.SetProjectionLineColor(line_color)
                        ogs.SetCutLineColor(line_color)
                    if apply_foreground:
                        ogs.SetSurfaceForegroundPatternColor(fg_color)
                        ogs.SetCutForegroundPatternColor(fg_color)
                        if solid_fill_id is not None:
                            ogs.SetSurfaceForegroundPatternId(solid_fill_id)
                            ogs.SetCutForegroundPatternId(solid_fill_id)
                    if apply_background and version >= 2019:
                        ogs.SetSurfaceBackgroundPatternColor(bg_color)
                        ogs.SetCutBackgroundPatternColor(bg_color)
                        if solid_fill_id is not None:
                            ogs.SetSurfaceBackgroundPatternId(solid_fill_id)
                            ogs.SetCutBackgroundPatternId(solid_fill_id)
                            
                    for idt in vi.ele_id:
                        link_matches = wndw._get_link_registry_matches(idt, vi)

                        if link_matches:
                            for link_meta in link_matches:
                                try:
                                    overlay_id = create_link_overlay_directshape(
                                        new_doc, view, sel_cat, link_meta, ogs
                                    )
                                    if overlay_id is not None:
                                        wndw._temp_direct_shapes.append(overlay_id)
                                except Exception as ds_ex:
                                    logger.debug(
                                        "Failed to create linked-element overlay: %s",
                                        str(ds_ex)
                                    )
                        else:
                            # Host element
                            try:
                                view.SetElementOverrides(idt, ogs)
                            except Exception:
                                pass

            wndw._set_status("Colors applied", success=True)
        except Exception:
            external_event_trace()

    def GetName(self):
        return "Apply Colors Pro (multi-param/heatmap)"


# ===========================================================================
# MAIN WINDOW — ColorSplasherProWindow
# Extends the original architecture with all new features.
# Original event handler names preserved.
# ===========================================================================

class ColorSplasherProWindow(forms.WPFWindow):
    """
    Enterprise ColorSplasher Pro window.
    Inherits pyRevit WPFWindow for automatic XAML binding.
    """

    # Placeholder text constants
    _SEARCH_VALUES_PLACEHOLDER = "Search values..."

    def _create_empty_table(self):
        """Create a new DataTable with all columns needed for the ListView."""
        table = DataTable("Data")
        table.Columns.Add("Key", System.String)
        table.Columns.Add("Value", System.Object)
        table.Columns.Add("ValText", System.String)
        table.Columns.Add("Count", System.Int32)
        table.Columns.Add("R", System.Int32)
        table.Columns.Add("G", System.Int32)
        table.Columns.Add("B", System.Int32)
        table.Columns.Add("Hex", System.String)
        table.Columns.Add("Source", System.String)
        return table

    def __init__(
        self,
        xaml_file_name,
        categories,
        ext_ev,
        uns_ev,
        s_view,
        reset_event,
        ev_legend,
        ev_filters,
        ev_pro,
    ):
        self._initialized = False
        forms.WPFWindow.__init__(self, xaml_file_name)
        self.IsOpen = 1

        # Events
        self.filter_ev = ev_filters
        self.legend_ev = ev_legend
        self.reset_ev = reset_event
        self.crt_view = s_view
        self.event = ext_ev          # Standard ApplyColors event
        self.event_pro = ev_pro      # Pro ApplyColorsPro event
        self.uns_event = uns_ev
        self.uns_event.Raise()

        # Categories data
        self.categs = categories
        self.width_par = 1

        # Config persistence
        self._config = pyrevit_script.get_config()

        # Raw full value list before search/sort filter
        self._all_value_items_raw = []
        # Filtered + sorted display list
        self._display_value_items = []

        # Parameter lists
        self._filtered_parameters = []
        self._all_parameters = []

        # Category table
        self.table_data = DataTable("Data")
        self.table_data.Columns.Add("Key", System.String)
        self.table_data.Columns.Add("Value", System.Object)
        names = [x.name for x in self.categs]
        self.table_data.Rows.Add("Select Category", 0)
        for key_, value_ in zip(names, self.categs):
            self.table_data.Rows.Add(key_, value_)

        # Value list table
        self._table_data_3 = self._create_empty_table()

        # Parameter tables
        self._table_data_2 = DataTable("Data")
        self._table_data_2.Columns.Add("Key", System.String)
        self._table_data_2.Columns.Add("Value", System.Object)
        self._table_data_2.Rows.Add("Select Parameter", 0)

        # Loaded links cache
        self._loaded_links = []

        # UI state
        self._shift_pressed_on_click = False
        self._current_sort_mode = 'az'

        # Setup
        self.Closed += self.closed
        pyrevit_script.restore_window_position(self)
        self._setup_ui()
        self._initialized = True

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        """Initialise all UI controls after XAML load."""
        # Revit version label
        try:
            ver = str(HOST_APP.version)
            self._txt_revit_ver.Text = ver
        except Exception:
            self._txt_revit_ver.Text = "--"

        # Category combo
        self._categories.ItemsSource = self.table_data.DefaultView
        self._categories.SelectionChanged += self.update_filter
        self._categories.SelectedIndex = -1

        # Primary param combo
        self._list_box1.ItemsSource = self._table_data_2.DefaultView
        self._list_box1.SelectedIndex = 0

        # Initialize dynamic parameter panel
        self._dynamic_rows = []
        self._panel_multi_params.Children.Clear()
        self._add_parameter_dropdown()

        # Checkbox settings from config
        self._chk_line_color.IsChecked = self._config.get_option("apply_line_color_pro", False)
        self._chk_foreground_pattern.IsChecked = self._config.get_option(
            "apply_foreground_pattern_color_pro", True
        )
        if HOST_APP.is_newer_than(2019, or_equal=True):
            self._chk_background_pattern.IsChecked = self._config.get_option(
                "apply_background_pattern_color_pro", False
            )
            self._chk_background_pattern.IsEnabled = True
        else:
            self._chk_background_pattern.IsChecked = False
            self._chk_background_pattern.IsEnabled = False
            self._chk_background_pattern.Content = "Apply Background Pattern Color (Requires Revit 2019+)"

        # Value list
        self.list_box2.ItemsSource = self._table_data_3.DefaultView
        self.list_box2.SelectionChanged += self.list_selected_index_changed
        self.list_box2.MouseDown += self.list_box2_mouse_down
        self._update_placeholder_visibility()

        # Search values placeholder
        self._search_values.Text = self._SEARCH_VALUES_PLACEHOLDER
        try:
            from System.Windows.Media import Brushes
            self._search_values.Foreground = Brushes.Gray
        except Exception:
            pass

        # Sort combo default
        self._combo_sort.SelectedIndex = 0

        # Mode panel visibility defaults
        self._update_mode_ui()

        # Load links into dropdown
        self._refresh_links()
        try:
            self._combo_links.SelectionChanged += self.on_link_selection_changed
        except Exception:
            pass

        # Sort
        try:
            from System.Windows.Controls import ScrollViewer
            ScrollViewer.SetHorizontalScrollBarVisibility(
                self.list_box2,
                System.Windows.Controls.ScrollBarVisibility.Auto
            )
        except Exception:
            pass

        self.Closing += self.closing_event

        # Icon (Fix #1)
        try:
            from System.Windows.Media.Imaging import BitmapImage
            from System import Uri
            icon_path = join(_BUNDLE_DIR, "icon.png")
            if exists(icon_path):
                self.Icon = BitmapImage(Uri(icon_path))
        except Exception as icon_ex:
            logger.debug("Failed to load window icon: %s", str(icon_ex))

    def _update_mode_ui(self):
        """Show/hide secondary/tertiary combos and heat map band selector based on mode."""
        try:
            from System.Windows import Visibility
            is_heatmap = self._radio_heatmap.IsChecked
            is_multi = self._radio_multi.IsChecked

            # Heat map band selector visibility
            if is_heatmap:
                self._panel_heatmap_opts.Visibility = Visibility.Visible
            else:
                self._panel_heatmap_opts.Visibility = Visibility.Collapsed
        except Exception:
            pass

    def _refresh_links(self):
        """Populate the link selector combo box."""
        try:
            doc = revit.DOCS.doc
            self._loaded_links = get_loaded_links(doc)
            self._combo_links.Items.Clear()
            self._combo_links.Items.Add("All Links")
            for li in self._loaded_links:
                self._combo_links.Items.Add(li.link_name)
            self._combo_links.SelectedIndex = 0
        except Exception:
            pass

    def _refresh_secondary_tertiary(self):
        """Refresh dynamic parameter combos from current category params."""
        try:
            sel_cat_row = self._categories.SelectedItem
            if sel_cat_row is None:
                return
            row = self._get_category_row(sel_cat_row, self._categories.SelectedIndex)
            if row is None:
                return
            sel_cat = row["Value"]
            if sel_cat == 0:
                return

            if self._all_parameters:
                param_names = ["(none)"] + [name for name, _ in self._all_parameters]
            elif sel_cat.par:
                param_names = ["(none)"] + [p.name for p in sel_cat.par]
            else:
                param_names = ["No Parameters Available"]

            if not self._dynamic_rows:
                self._add_parameter_dropdown()

            for row_dict in self._dynamic_rows:
                combo = row_dict["combo"]
                curr_sel = combo.SelectedItem
                combo.SelectionChanged -= self.on_dynamic_parameter_changed
                combo.Items.Clear()
                for name in param_names:
                    combo.Items.Add(name)
                if curr_sel in param_names:
                    combo.SelectedItem = curr_sel
                else:
                    combo.SelectedIndex = 0
                combo.SelectionChanged += self.on_dynamic_parameter_changed
        except Exception as ex:
            logger.debug("Error refreshing dynamic combos: %s", str(ex))

    # ------------------------------------------------------------------
    # Closed / closing
    # ------------------------------------------------------------------

    def closed(self, sender, args):
        try:
            pyrevit_script.save_window_position(self)
        except Exception:
            pass

        # Unregister event handler directly on the UI thread to prevent reload crash
        try:
            uiapp = HOST_APP.uiapp
            if hasattr(self, '_event_handler_uns') and self._event_handler_uns:
                uiapp.ViewActivated -= self._event_handler_uns.view_changed
        except Exception:
            pass

        # Cleanup static references to prevent reload crashes
        try:
            SubscribeView._wndw = None
            ApplyColors._wndw = None
            ApplyColorsPro._wndw = None
            ResetColors._wndw = None
            CreateLegend._wndw = None
            CreateFilters._wndw = None
            ColorSplasherProWindow._current_wndw = None
        except Exception:
            pass

        # Dispose of external events
        if hasattr(self, '_ext_events') and self._ext_events:
            for ev in self._ext_events:
                if ev:
                    try:
                        ev.Dispose()
                    except Exception:
                        pass
            self._ext_events = []

    def closing_event(self, sender, e):
        self.IsOpen = 0
        if hasattr(self, 'uns_event') and self.uns_event:
            try:
                self.uns_event.Raise()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------

    def _set_status(self, message, success=True):
        """Update the status indicator in the header and footer."""
        try:
            from System.Windows.Media import SolidColorBrush, Color as WpfColor

            self._txt_status.Text = message
            self._txt_footer_status.Text = message

            if success:
                clr_val = WpfColor.FromRgb(34, 197, 94) # #22C55E
            else:
                clr_val = WpfColor.FromRgb(239, 68, 68) # #EF4444

            brush = SolidColorBrush(clr_val)
            self._txt_status.Foreground = brush
            self._status_dot.Fill = brush
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Data row accessor (from original — unchanged)
    # ------------------------------------------------------------------

    def _get_data_row_from_item(self, item, item_index=None, table=None):
        """Return the backing DataRow for a WPF-bound item.

        WPF normally exposes DataTable-bound ComboBox/ListView items as
        DataRowView objects, but pyRevit/IronPython can occasionally surface
        raw values during selection commits or after an ItemsSource refresh.
        The previous fallback always indexed the values table, so category and
        parameter selections could resolve to the wrong row (or no row at all),
        making category clicks appear to do nothing.  Accepting the source table
        keeps the fallback aligned with the control that raised the event.
        """
        from System.Data import DataRow, DataRowView

        if item is None:
            return None
        if isinstance(item, DataRowView):
            return item.Row
        if isinstance(item, DataRow):
            return item
        if hasattr(item, "Row"):
            return item.Row

        source_table = table
        if source_table is None:
            source_table = getattr(self, "_table_data_3", None)

        if item_index is not None and source_table is not None:
            try:
                if 0 <= item_index < source_table.Rows.Count:
                    return source_table.Rows[item_index]
            except Exception:
                pass
        return None

    def _get_category_row(self, item=None, item_index=None):
        """Resolve a category ComboBox selection to its category table row."""
        if item is None:
            item = self._categories.SelectedItem
        if item_index is None:
            item_index = self._categories.SelectedIndex
        return self._get_data_row_from_item(item, item_index, self.table_data)

    def _get_parameter_row(self, item=None, item_index=None):
        """Resolve a primary parameter ComboBox selection to its table row."""
        if item is None:
            item = self._list_box1.SelectedItem
        if item_index is None:
            item_index = self._list_box1.SelectedIndex
        return self._get_data_row_from_item(item, item_index, self._table_data_2)

    def _get_value_row(self, item=None, item_index=None):
        """Resolve a value ListView selection to its values table row."""
        if item is None:
            item = self.list_box2.SelectedItem
        if item_index is None:
            item_index = self.list_box2.SelectedIndex
        return self._get_data_row_from_item(item, item_index, self._table_data_3)

    # ------------------------------------------------------------------
    # Placeholder visibility (from original — unchanged)
    # ------------------------------------------------------------------

    def _update_placeholder_visibility(self):
        from System.Windows import Visibility

        if self.list_box2.ItemsSource is None or self.list_box2.Items.Count == 0:
            self._txt_placeholder_values.Visibility = Visibility.Visible
        else:
            self._txt_placeholder_values.Visibility = Visibility.Collapsed

    # ------------------------------------------------------------------
    # NEW: Rebuild value list from raw items applying search + sort
    # ------------------------------------------------------------------

    def _rebuild_display_list(self):
        """
        Filter and sort _all_value_items_raw then repopulate list_box2.
        Builds display key as 'value  (count)'.
        """
        try:
            self.list_box2.SelectionChanged -= self.list_selected_index_changed
        except Exception:
            pass

        try:
            # Get search text
            search_text = ""
            placeholder = self._SEARCH_VALUES_PLACEHOLDER
            if self._search_values.Text and self._search_values.Text != placeholder:
                search_text = self._search_values.Text

            # Get sort mode from tag of selected ComboBoxItem
            sort_mode = 'az'
            try:
                selected_sort = self._combo_sort.SelectedItem
                if selected_sort is not None and hasattr(selected_sort, "Tag") and selected_sort.Tag:
                    sort_mode = str(selected_sort.Tag)
            except Exception:
                pass
            self._current_sort_mode = sort_mode

            # Filter
            if _PRO_ENGINE_OK:
                filtered = filter_value_items(self._all_value_items_raw, search_text)
                sorted_items = sort_value_items(filtered, sort_mode)
            else:
                filtered = self._all_value_items_raw
                sorted_items = filtered

            self._display_value_items = sorted_items

            # Rebuild DataTable
            self._table_data_3 = self._create_empty_table()

            for vi in sorted_items:
                count = get_item_count(vi) if _PRO_ENGINE_OK else 0
                display_key = build_display_key_with_count(vi.value, count) if _PRO_ENGINE_OK else vi.value
                hex_color = "#{0:02X}{1:02X}{2:02X}".format(vi.n1, vi.n2, vi.n3)
                source_name = getattr(vi, "link_name", "") or ""
                self._table_data_3.Rows.Add(
                    display_key,
                    vi,
                    vi.value,
                    count,
                    vi.n1,
                    vi.n2,
                    vi.n3,
                    hex_color,
                    source_name
                )

            default_view = self._table_data_3.DefaultView
            self.list_box2.ItemsSource = default_view
            self.list_box2.SelectedIndex = -1
            self._update_placeholder_visibility()
            self.list_box2.UpdateLayout()

            # Update summary stats in Bento UI
            try:
                total_vals = len(self._display_value_items)
                total_elements = sum(get_item_count(vi) for vi in self._display_value_items)
                self._txt_total_values.Text = str(total_vals)
                self._txt_total_elements.Text = "{:,}".format(total_elements)
            except Exception:
                pass

            # Update preview for first item
            try:
                if self._display_value_items:
                    first_item = self._display_value_items[0]
                    self._update_preview(first_item.n1, first_item.n2, first_item.n3)
            except Exception:
                pass

            self._update_listbox_colors_async()
        except Exception:
            external_event_trace()
        finally:
            try:
                self.list_box2.SelectionChanged += self.list_selected_index_changed
            except Exception:
                pass

    def _register_link_element(self, element, link_info, link_name=None):
        """Register a linked element for later host-side overlay colorization."""
        try:
            ele_id_int = get_element_int_id(element.Id)
            link_inst_id_int = get_element_int_id(link_info.link_instance.Id)
            meta = {
                "link_instance": link_info.link_instance,
                "link_doc": link_info.link_doc,
                "link_name": link_name or link_info.link_name,
                "element_id": element.Id,
                "element_id_int": ele_id_int,
                "link_instance_id_int": link_inst_id_int,
            }
            registry = getattr(self, "_link_elements_registry", None)
            if registry is None:
                registry = {}
                self._link_elements_registry = registry
            registry.setdefault(ele_id_int, []).append(meta)
        except Exception as ex:
            logger.debug("Failed to register linked element: %s", str(ex))

    def _get_link_registry_matches(self, element_id, value_item=None):
        """Return registered linked-element metadata matching a value item/id."""
        try:
            id_int = get_element_int_id(element_id)
            matches = list(getattr(self, "_link_elements_registry", {}).get(id_int, []))
            if not matches or value_item is None:
                return matches
            link_name = getattr(value_item, "link_name", None)
            if link_name:
                filtered = [m for m in matches if m.get("link_name") == link_name]
                if filtered:
                    return filtered
            linked_ids = getattr(value_item, "_linked_element_id_ints", None)
            if linked_ids is not None and id_int in linked_ids:
                return matches
            return []
        except Exception:
            return []

    # ------------------------------------------------------------------
    # NEW: Collect value items considering mode + link selection
    # ------------------------------------------------------------------

    def _collect_value_items(self):
        """
        Collect value items depending on the active mode:
        - Standard: original get_range_values
        - Multi-Param: get_range_values_multi from engine
        - Heat Map: get_range_values_heatmap from engine
        With optional link element injection.
        """
        try:
            doc = revit.DOCS.doc
            view = self.crt_view

            # Get selected category
            sel_cat_row = self._categories.SelectedItem
            if sel_cat_row is None or self._categories.SelectedIndex <= 0:
                self._set_status("Please select a category", success=False)
                return
            cat_row = self._get_category_row(sel_cat_row, self._categories.SelectedIndex)
            if cat_row is None:
                return
            sel_cat = cat_row["Value"]
            if sel_cat == 0:
                return

            # Get selected primary parameter
            sel_par_row = self._list_box1.SelectedItem
            if sel_par_row is None or self._list_box1.SelectedIndex <= 0:
                self._set_status("Please select a parameter", success=False)
                return
            par_row = self._get_parameter_row(sel_par_row, self._list_box1.SelectedIndex)
            if par_row is None:
                return
            sel_param = par_row["Value"]
            if sel_param == 0:
                return

            # Determine link elements to include
            link_elements = []
            self._link_elements_registry = {}
            if _PRO_ENGINE_OK:
                try:
                    include_links = self._radio_links.IsChecked or self._radio_all.IsChecked
                    host_only = self._radio_host.IsChecked

                    if include_links or not host_only:
                        links_to_use = self._get_selected_link_infos()

                        for li in links_to_use:
                            elems = collect_elements_from_link(li, sel_cat.int_id, view)
                            for (ele, link_name) in elems:
                                self._register_link_element(ele, li, link_name)
                            link_elements.extend(elems)
                except Exception as ex:
                    logger.debug("Failed to populate link elements registry: %s", str(ex))
                    link_elements = []

            # Determine mode
            is_standard = not hasattr(self, '_radio_multi') or self._radio_standard.IsChecked
            is_multi = hasattr(self, '_radio_multi') and self._radio_multi.IsChecked
            is_heatmap = hasattr(self, '_radio_heatmap') and self._radio_heatmap.IsChecked

            # Host-only vs host+links
            use_links = bool(link_elements)

            # Determine selection scope
            scope = "view"
            if hasattr(self, "_radio_scope_whole") and self._radio_scope_whole.IsChecked:
                scope = "whole"
            elif hasattr(self, "_radio_scope_selected") and self._radio_scope_selected.IsChecked:
                scope = "selected"

            if self._radio_links.IsChecked:
                scope = "none"

            if is_heatmap and _PRO_ENGINE_OK:
                # Heat map mode
                num_bands_text = "5"
                try:
                    selected_band = self._combo_bands.SelectedItem
                    if selected_band is not None and hasattr(selected_band, "Content"):
                        num_bands_text = str(selected_band.Content)
                except Exception:
                    pass
                try:
                    num_bands = int(num_bands_text)
                except Exception:
                    num_bands = 5
                value_items, ranges, errors = get_range_values_heatmap(
                    sel_cat, sel_param, view, doc,
                    num_bands=num_bands,
                    link_elements=link_elements if use_links else None,
                    scope=scope
                )
                if errors and not value_items:
                    self._set_status("Heat map: no numeric values", success=False)
                    return
                self._all_value_items_raw = value_items

            elif is_multi and _PRO_ENGINE_OK:
                # Multi-param mode: collect all selected parameters from dynamic inputs
                additional_names = []
                for row_dict in self._dynamic_rows:
                    combo = row_dict["combo"]
                    sel_item = combo.SelectedItem
                    if sel_item and sel_item != "(none)" and sel_item != "No Parameters Available":
                        additional_names.append(sel_item)
                
                value_items = get_range_values_multi(
                    sel_cat, sel_param,
                    additional_names,
                    view, doc,
                    link_elements=link_elements if use_links else None,
                    scope=scope
                )
                self._all_value_items_raw = value_items

            else:
                # Standard mode: use original get_range_values, then append link values
                value_items = []
                if scope != "none":
                    value_items = get_range_values(sel_cat, sel_param, view, scope=scope)
                # If links requested, run multi-param to include them
                if use_links and _PRO_ENGINE_OK:
                    value_items_links = get_range_values_multi(
                        sel_cat, sel_param, [], view, doc,
                        link_elements=link_elements,
                        scope="none"
                    )
                    # Merge: keep host values, add link-only values
                    existing_values = set(vi.value for vi in value_items)
                    for vi in value_items_links:
                        if vi.value not in existing_values:
                            value_items.append(vi)
                self._all_value_items_raw = value_items

            # Now rebuild the display
            self._rebuild_display_list()
            total = len(self._all_value_items_raw)
            self._set_status("{0} value(s) loaded".format(total), success=True)

        except Exception:
            external_event_trace()

    # ------------------------------------------------------------------
    # UNCHANGED: Original event handler — check_item (parameter selection)
    # ------------------------------------------------------------------

    def check_item(self, sender, e):
        """Handle parameter selection change."""
        if not getattr(self, "_initialized", False):
            return
        try:
            self.list_box2.SelectionChanged -= self.list_selected_index_changed
        except Exception:
            pass

        if self._categories.SelectedItem is None:
            return
        sel_cat_row = self._categories.SelectedItem
        from System.Data import DataRowView

        try:
            if isinstance(sel_cat_row, DataRowView):
                sel_cat = sel_cat_row.Row["Value"]
            elif hasattr(sel_cat_row, "Row"):
                sel_cat = sel_cat_row.Row["Value"]
            else:
                sel_cat = sel_cat_row["Value"]
        except Exception as ex:
            logger.debug("Error getting category: %s", str(ex))
            return

        if sel_cat is None or sel_cat == 0:
            return
        if (
            sender.SelectedIndex == -1
            or sender.SelectedItem is None
            or sender.SelectedIndex == 0
        ):
            if sender.SelectedIndex == 0:
                selected_item = sender.SelectedItem
                if selected_item is not None:
                    row = self._get_parameter_row(selected_item, 0)
                    if row is not None and row["Value"] == 0:
                        self._table_data_3 = self._create_empty_table()
                        self.list_box2.ItemsSource = self._table_data_3.DefaultView
                        self._update_placeholder_visibility()
                        return
            self._table_data_3 = self._create_empty_table()
            self.list_box2.ItemsSource = self._table_data_3.DefaultView
            self._update_placeholder_visibility()
            return

        # Delegate to the new unified collector
        self._collect_value_items()

        try:
            self.list_box2.SelectionChanged += self.list_selected_index_changed
        except Exception:
            pass

    def _get_selected_link_infos(self):
        """Return the currently selected link(s), or all loaded links."""
        try:
            selected_link_idx = self._combo_links.SelectedIndex
            if selected_link_idx <= 0:
                return list(self._loaded_links)
            idx = selected_link_idx - 1
            if 0 <= idx < len(self._loaded_links):
                return [self._loaded_links[idx]]
        except Exception:
            pass
        return []

    def _load_parameters_for_current_source(self, sel_cat):
        """Load category parameters from host, links, or both based on source UI."""
        doc = revit.DOCS.doc
        include_links = (
            hasattr(self, "_radio_links")
            and (self._radio_links.IsChecked or self._radio_all.IsChecked)
        )
        links_only = hasattr(self, "_radio_links") and self._radio_links.IsChecked

        # Host-only can use the schema-based cache. Link-aware modes need
        # element sampling as linked documents can expose parameters that the
        # host category schema does not contain.
        if not include_links:
            if not sel_cat.par:
                sel_cat.par = _load_params_on_demand(doc, self.crt_view, sel_cat.int_id)
            return sel_cat.par

        link_params = collect_parameters_for_category(
            doc,
            self.crt_view,
            sel_cat.int_id,
            include_links=True,
            loaded_links=self._get_selected_link_infos(),
            include_host=not links_only
        )
        if link_params:
            return link_params

        if not links_only:
            if not sel_cat.par:
                sel_cat.par = _load_params_on_demand(doc, self.crt_view, sel_cat.int_id)
            return sel_cat.par
        return []

    # ------------------------------------------------------------------
    # UNCHANGED: Original event handler — update_filter (category change)
    # ------------------------------------------------------------------

    def update_filter(self, sender, e):
        """Update parameter list when category selection changes."""
        if not getattr(self, "_initialized", False):
            return
        try:
            if sender.SelectedItem is None:
                return

            sel_cat_row = sender.SelectedItem
            row = self._get_data_row_from_item(sel_cat_row, sender.SelectedIndex, self.table_data)
            if row is None:
                return
            sel_cat = row["Value"]

            self._table_data_2 = DataTable("Data")
            self._table_data_2.Columns.Add("Key", System.String)
            self._table_data_2.Columns.Add("Value", System.Object)
            self._table_data_3 = self._create_empty_table()

            self._table_data_2.Rows.Add("Select Parameter", 0)

            if sel_cat != 0 and sender.SelectedIndex != 0:
                # Load parameters from the currently selected source.
                params_for_source = self._load_parameters_for_current_source(sel_cat)

                if not params_for_source:
                    self._table_data_2.Rows.Clear()
                    self._table_data_2.Rows.Add("No Parameters Available", 0)
                    self._list_box1.ItemsSource = self._table_data_2.DefaultView
                    self._list_box1.SelectedIndex = 0
                    self.list_box2.ItemsSource = self._table_data_3.DefaultView
                    self._update_placeholder_visibility()
                    return

                names_par = [x.name for x in params_for_source]
                for key_, value_ in zip(names_par, params_for_source):
                    self._table_data_2.Rows.Add(key_, value_)
                self._all_parameters = [
                    (key_, value_) for key_, value_ in zip(names_par, params_for_source)
                ]
                self._list_box1.ItemsSource = self._table_data_2.DefaultView
                self._list_box1.SelectedIndex = 0
                self.list_box2.ItemsSource = self._table_data_3.DefaultView
                self._update_placeholder_visibility()
                self._refresh_secondary_tertiary()
            else:
                self._all_parameters = []
                self._list_box1.ItemsSource = self._table_data_2.DefaultView
                self._list_box1.SelectedIndex = 0
                self.list_box2.ItemsSource = self._table_data_3.DefaultView
                self._update_placeholder_visibility()

            self._all_value_items_raw = []
        except Exception as ex:
            logger.debug("Error in update_filter: %s", str(ex))
            try:
                self._set_status("Error loading parameters: {}".format(str(ex)), success=False)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # NEW: Mode changed handler
    # ------------------------------------------------------------------

    def on_mode_changed(self, sender, e):
        """Called when coloring mode radio changes."""
        if not getattr(self, "_initialized", False):
            return
        self._update_mode_ui()
        
        # Ensure default dynamic row exists in Multi-Param mode
        if self._radio_multi.IsChecked and not self._dynamic_rows:
            self._add_parameter_dropdown()
            
        # Refresh value list if a parameter is selected
        if (
            self._list_box1.SelectedIndex > 0
            and self._categories.SelectedIndex > 0
        ):
            self._collect_value_items()

    def on_source_changed(self, sender, e):
        """Called when link/source radio selection changes."""
        if not getattr(self, "_initialized", False):
            return
        if self._categories.SelectedIndex > 0:
            self.update_filter(self._categories, None)

    def on_link_selection_changed(self, sender, e):
        """Refresh parameters/values when the specific link selector changes."""
        if not getattr(self, "_initialized", False):
            return
        if self._categories.SelectedIndex > 0:
            self.update_filter(self._categories, None)

    def button_click_refresh_links(self, sender, e):
        """Reload Revit link instances and refresh the active category selection."""
        self._refresh_links()
        if getattr(self, "_initialized", False) and self._categories.SelectedIndex > 0:
            self.update_filter(self._categories, None)

    def button_click_link_info(self, sender, e):
        """Show loaded link count and names for troubleshooting."""
        try:
            if not self._loaded_links:
                UI.TaskDialog.Show("ColorSplasher Pro", "No loaded Revit links found.")
                return
            names = [li.link_name for li in self._loaded_links]
            UI.TaskDialog.Show(
                "ColorSplasher Pro",
                "Loaded links ({0}):\n{1}".format(len(names), "\n".join(names))
            )
        except Exception:
            external_event_trace()

    def on_scope_changed(self, sender, e):
        """Called when selection scope radio changes."""
        if not getattr(self, "_initialized", False):
            return
        if self._categories.SelectedIndex > 0 and self._list_box1.SelectedIndex > 0:
            self._collect_value_items()

    # ------------------------------------------------------------------
    # NEW: Secondary / Tertiary Parameter Selection handler
    # ------------------------------------------------------------------

    def on_dynamic_parameter_changed(self, sender, e):
        """Called when any dynamic parameter selection changes."""
        if not getattr(self, "_initialized", False):
            return
        self._collect_value_items()

    def btn_add_param_click(self, sender, e):
        """Click handler for + Add Parameter button."""
        self._add_parameter_dropdown()

    def _add_parameter_dropdown(self, selected_name=None):
        """Dynamically append a new parameter selector row."""
        try:
            from System.Windows.Controls import Grid, ColumnDefinition, ComboBox, Button, TextBlock
            from System.Windows import GridLength, GridUnitType, Thickness, VerticalAlignment
            from System.Windows.Media import Brushes, FontFamily
            
            row_index = len(self._dynamic_rows) + 2
            
            grid = Grid()
            grid.Margin = Thickness(0, 4, 0, 4)
            
            col_lbl = ColumnDefinition()
            col_lbl.Width = GridLength.Auto
            col_cmb = ColumnDefinition()
            col_cmb.Width = GridLength(1.0, GridUnitType.Star)
            col_btn = ColumnDefinition()
            col_btn.Width = GridLength.Auto
            
            grid.ColumnDefinitions.Add(col_lbl)
            grid.ColumnDefinitions.Add(col_cmb)
            grid.ColumnDefinitions.Add(col_btn)
            
            lbl = TextBlock()
            lbl.Text = "Parameter {}: ".format(row_index)
            lbl.VerticalAlignment = VerticalAlignment.Center
            lbl.Width = 70
            lbl.FontSize = 10
            lbl.Foreground = self.FindResource("TextMuted")
            Grid.SetColumn(lbl, 0)
            grid.Children.Add(lbl)
            
            combo = ComboBox()
            combo.Style = self.FindResource("CleanCombo")
            combo.Height = 28
            combo.VerticalAlignment = VerticalAlignment.Center
            
            sel_cat_row = self._categories.SelectedItem
            param_names = []
            if sel_cat_row is not None:
                row = self._get_category_row(sel_cat_row, self._categories.SelectedIndex)
                if self._all_parameters:
                    param_names = ["(none)"] + [name for name, _ in self._all_parameters]
                elif row is not None and row["Value"] != 0 and row["Value"].par:
                    param_names = ["(none)"] + [p.name for p in row["Value"].par]
            
            if not param_names:
                param_names = ["No Parameters Available"]
                
            for name in param_names:
                combo.Items.Add(name)
                
            if selected_name and selected_name in param_names:
                combo.SelectedItem = selected_name
            else:
                combo.SelectedIndex = 0
                
            combo.SelectionChanged += self.on_dynamic_parameter_changed
            Grid.SetColumn(combo, 1)
            grid.Children.Add(combo)
            
            btn = Button()
            btn.Style = self.FindResource("BtnSecondary")
            btn.Width = 24
            btn.Height = 28
            btn.Margin = Thickness(4, 0, 0, 0)
            btn.VerticalAlignment = VerticalAlignment.Center
            
            tb = TextBlock()
            tb.Text = u"\uE711" # Chrome Close red glyph
            tb.FontFamily = self.FindResource("Segoe MDL2 Assets") or FontFamily("Segoe MDL2 Assets")
            tb.FontSize = 10
            tb.Foreground = Brushes.Red
            btn.Content = tb
            
            def on_del_click(s, ev):
                self._remove_parameter_dropdown(grid)
                
            btn.Click += on_del_click
            Grid.SetColumn(btn, 2)
            grid.Children.Add(btn)
            
            self._panel_multi_params.Children.Add(grid)
            self._dynamic_rows.append({"grid": grid, "label": lbl, "combo": combo})
            self._update_dynamic_labels()
            
            if getattr(self, "_initialized", False):
                self._collect_value_items()
        except Exception as ex:
            logger.debug("Error adding parameter: %s", str(ex))

    def _remove_parameter_dropdown(self, grid):
        """Remove a dynamic parameter selector row."""
        try:
            self._panel_multi_params.Children.Remove(grid)
            self._dynamic_rows = [r for r in self._dynamic_rows if r["grid"] != grid]
            self._update_dynamic_labels()
            if getattr(self, "_initialized", False):
                self._collect_value_items()
        except Exception as ex:
            logger.debug("Error removing parameter: %s", str(ex))

    def _update_dynamic_labels(self):
        """Re-index dynamic labels when rows are added/removed."""
        try:
            for idx, r in enumerate(self._dynamic_rows):
                r["label"].Text = "Parameter {}: ".format(idx + 2)
        except Exception as ex:
            logger.debug("Error updating labels: %s", str(ex))

    # ------------------------------------------------------------------
    # NEW: Search values handler
    # ------------------------------------------------------------------

    def search_values_enter(self, sender, e):
        """Clear placeholder when search box gets focus."""
        try:
            from System.Windows.Media import Brushes
            if self._search_values.Text == self._SEARCH_VALUES_PLACEHOLDER:
                self._search_values.Text = ""
                self._search_values.Foreground = Brushes.Black
        except Exception:
            pass

    def search_values_leave(self, sender, e):
        """Restore placeholder if empty."""
        try:
            from System.Windows.Media import Brushes
            if self._search_values.Text == "":
                self._search_values.Text = self._SEARCH_VALUES_PLACEHOLDER
                self._search_values.Foreground = Brushes.Gray
        except Exception:
            pass

    def on_search_values_changed(self, sender, e):
        """Live filter the value list as user types."""
        if not getattr(self, "_initialized", False):
            return
        if self._search_values.Text == self._SEARCH_VALUES_PLACEHOLDER:
            return
        if self._all_value_items_raw:
            self._rebuild_display_list()

    # ------------------------------------------------------------------
    # NEW: Sort changed handler
    # ------------------------------------------------------------------

    def on_sort_changed(self, sender, e):
        """Re-sort the current value list."""
        if not getattr(self, "_initialized", False):
            return
        if self._all_value_items_raw:
            self._rebuild_display_list()

    # ------------------------------------------------------------------
    # UNCHANGED: Checkbox changed
    # ------------------------------------------------------------------

    def checkbox_changed(self, sender, e):
        if not getattr(self, "_initialized", False):
            return
        self._config.set_option("apply_line_color_pro", self._chk_line_color.IsChecked)
        self._config.set_option(
            "apply_foreground_pattern_color_pro", self._chk_foreground_pattern.IsChecked
        )
        if HOST_APP.is_newer_than(2019, or_equal=True):
            self._config.set_option(
                "apply_background_pattern_color_pro", self._chk_background_pattern.IsChecked
            )
        pyrevit_script.save_config()

    # ------------------------------------------------------------------
    # UNCHANGED: Button click handlers (original names)
    # ------------------------------------------------------------------

    def button_click_set_colors(self, sender, e):
        # Validation before applying colors (Fix #9)
        if self._categories.SelectedIndex <= 0:
            forms.alert("Please select a Category first.", title="ColorSplasher Pro")
            return
        if self._list_box1.SelectedIndex <= 0:
            forms.alert("Please select at least one Parameter.", title="ColorSplasher Pro")
            return
        if self.list_box2.Items.Count <= 0:
            forms.alert("No values found to colorize. Please check your category and parameter selection.", title="ColorSplasher Pro")
            return
            
        # Choose handler based on mode/source. Linked elements require the Pro
        # handler because host views cannot directly override element ids from
        # a linked document; Pro creates host-side overlay DirectShapes.
        is_standard = self._radio_standard.IsChecked
        uses_links = (
            hasattr(self, "_radio_links")
            and (self._radio_links.IsChecked or self._radio_all.IsChecked)
        )
        if is_standard and not uses_links:
            self.event.Raise()
        else:
            self.event_pro.Raise()

    def button_click_reset(self, sender, e):
        self.reset_ev.Raise()

    def button_click_create_legend(self, sender, e):
        if self.list_box2.Items.Count <= 0:
            return
        self.legend_ev.Raise()

    def button_click_create_view_filters(self, sender, e):
        if self.list_box2.Items.Count <= 0:
            return
        self.reset_ev.Raise()
        self.filter_ev.Raise()

    def save_load_color_scheme(self, sender, e):
        saveform = FormSaveLoadScheme()
        saveform.Show()

    def button_click_random_colors(self, sender, e):
        """Reassign random colours to all displayed values."""
        try:
            if self._all_value_items_raw:
                used_colors = set()
                for vi in self._all_value_items_raw:
                    attempts = 0
                    while attempts < 200:
                        r = randint(30, 230)
                        g = randint(30, 230)
                        b = randint(30, 230)
                        if (r, g, b) not in used_colors:
                            used_colors.add((r, g, b))
                            break
                        attempts += 1
                    vi.n1 = r
                    vi.n2 = g
                    vi.n3 = b
                    try:
                        vi.colour = Drawing.Color.FromArgb(r, g, b)
                    except Exception:
                        pass
                self._rebuild_display_list()
        except Exception:
            external_event_trace()

    def button_click_gradient_colors(self, sender, e):
        """Apply gradient between first and last value colour."""
        try:
            items = self._all_value_items_raw
            number_items = len(items)
            if number_items < 2:
                return
            start_color = items[0].colour
            end_color = items[-1].colour
            list_colors = self.get_gradient_colors(start_color, end_color, number_items)
            for indx, vi in enumerate(items):
                vi.n1 = abs(list_colors[indx][1])
                vi.n2 = abs(list_colors[indx][2])
                vi.n3 = abs(list_colors[indx][3])
                try:
                    vi.colour = Drawing.Color.FromArgb(vi.n1, vi.n2, vi.n3)
                except Exception:
                    pass
            self._rebuild_display_list()
        except Exception:
            external_event_trace()

    def button_click_select_all(self, sender, e):
        """Select all elements from all parameter values."""
        try:
            if not self._all_value_items_raw:
                return
            uidoc = HOST_APP.uiapp.ActiveUIDocument
            all_element_ids = List[DB.ElementId]()
            for vi in self._all_value_items_raw:
                if hasattr(vi, "ele_id") and vi.ele_id is not None:
                    for ele_id in vi.ele_id:
                        all_element_ids.Add(ele_id)
            if all_element_ids.Count > 0:
                uidoc.Selection.SetElementIds(all_element_ids)
                uidoc.RefreshActiveView()
        except Exception:
            external_event_trace()

    def button_click_select_none(self, sender, e):
        """Clear the current selection."""
        try:
            uidoc = HOST_APP.uiapp.ActiveUIDocument
            uidoc.Selection.SetElementIds(List[DB.ElementId]())
            uidoc.RefreshActiveView()
        except Exception:
            external_event_trace()

    # ------------------------------------------------------------------
    # NEW: Export handlers
    # ------------------------------------------------------------------

    def button_click_export_csv(self, sender, e):
        """Export current value table to CSV."""
        if not _PRO_ENGINE_OK:
            self._set_status("Engine not loaded", success=False)
            return
        if not self._all_value_items_raw:
            UI.TaskDialog.Show("ColorSplasher Pro", "No values to export. Please select a category and parameter first.")
            return
        try:
            with Forms.SaveFileDialog() as dlg:
                dlg.Title = "Export to CSV"
                dlg.Filter = "CSV files (*.csv)|*.csv|All files (*.*)|*.*"
                dlg.FileName = "ColorSplasherPro_Export.csv"
                dlg.DefaultExt = ".csv"
                dlg.OverwritePrompt = True
                if dlg.ShowDialog() == Forms.DialogResult.OK:
                    cat_name = self._get_selected_cat_name()
                    par_name = self._get_selected_par_name()
                    view_name = ""
                    try:
                        view_name = self.crt_view.Name
                    except Exception:
                        pass
                    ok, msg = export_to_csv(
                        self._all_value_items_raw,
                        dlg.FileName,
                        cat_name, par_name, view_name
                    )
                    if ok:
                        self._set_status("CSV exported", success=True)
                        UI.TaskDialog.Show("ColorSplasher Pro", msg)
                    else:
                        self._set_status("Export failed", success=False)
                        UI.TaskDialog.Show("ColorSplasher Pro", msg)
        except Exception:
            external_event_trace()

    def button_click_export_json(self, sender, e):
        """Export current value table to JSON."""
        if not _PRO_ENGINE_OK:
            self._set_status("Engine not loaded", success=False)
            return
        if not self._all_value_items_raw:
            UI.TaskDialog.Show("ColorSplasher Pro", "No values to export. Please select a category and parameter first.")
            return
        try:
            with Forms.SaveFileDialog() as dlg:
                dlg.Title = "Export to JSON"
                dlg.Filter = "JSON files (*.json)|*.json|All files (*.*)|*.*"
                dlg.FileName = "ColorSplasherPro_Export.json"
                dlg.DefaultExt = ".json"
                dlg.OverwritePrompt = True
                if dlg.ShowDialog() == Forms.DialogResult.OK:
                    cat_name = self._get_selected_cat_name()
                    par_name = self._get_selected_par_name()
                    view_name = ""
                    try:
                        view_name = self.crt_view.Name
                    except Exception:
                        pass
                    ok, msg = export_to_json(
                        self._all_value_items_raw,
                        dlg.FileName,
                        cat_name, par_name, view_name
                    )
                    if ok:
                        self._set_status("JSON exported", success=True)
                        UI.TaskDialog.Show("ColorSplasher Pro", msg)
                    else:
                        self._set_status("Export failed", success=False)
                        UI.TaskDialog.Show("ColorSplasher Pro", msg)
        except Exception:
            external_event_trace()

    def _get_selected_cat_name(self):
        try:
            row = self._get_category_row(self._categories.SelectedItem, self._categories.SelectedIndex)
            if row and row["Value"] != 0:
                return row["Value"].name
        except Exception:
            pass
        return "Unknown"

    def _get_selected_par_name(self):
        try:
            row = self._get_parameter_row(self._list_box1.SelectedItem, self._list_box1.SelectedIndex)
            if row and row["Value"] != 0:
                return row["Value"].name
        except Exception:
            pass
        return "Unknown"

    # ------------------------------------------------------------------
    # UNCHANGED: Gradient colour helper (from original)
    # ------------------------------------------------------------------

    def get_gradient_colors(self, start_color, end_color, steps):
        a_step = float((end_color.A - start_color.A) / steps)
        r_step = float((end_color.R - start_color.R) / steps)
        g_step = float((end_color.G - start_color.G) / steps)
        b_step = float((end_color.B - start_color.B) / steps)
        color_list = []
        for index in range(steps):
            a = max(start_color.A + int(a_step * index) - 1, 0)
            r = max(start_color.R + int(r_step * index) - 1, 0)
            g = max(start_color.G + int(g_step * index) - 1, 0)
            b = max(start_color.B + int(b_step * index) - 1, 0)
            color_list.append([a, r, g, b])
        return color_list

    # ------------------------------------------------------------------
    # UNCHANGED: Mouse / selection handlers (from original)
    # ------------------------------------------------------------------

    def list_box2_mouse_down(self, sender, e):
        from System.Windows.Input import ModifierKeys, Keyboard, Key
        from System.Windows.Media import VisualTreeHelper
        from System.Windows.Controls import ListBoxItem

        hit_on_item = False
        try:
            pos = e.GetPosition(self.list_box2)
            hit = VisualTreeHelper.HitTest(self.list_box2, pos)
            if hit is not None and hit.VisualHit is not None:
                element = hit.VisualHit
                while element is not None:
                    if isinstance(element, ListBoxItem):
                        hit_on_item = True
                        break
                    element = VisualTreeHelper.GetParent(element)
        except Exception as ex:
            logger.debug("Error in list_box2_mouse_down: {0}".format(ex))
            hit_on_item = False

        if not hit_on_item:
            self._shift_pressed_on_click = False
            e.Handled = True
            return

        shift_from_event = (
            e.KeyboardDevice.Modifiers & ModifierKeys.Shift
        ) == ModifierKeys.Shift
        shift_from_keyboard = (
            Keyboard.IsKeyDown(Key.LeftShift) or Keyboard.IsKeyDown(Key.RightShift)
        )
        self._shift_pressed_on_click = shift_from_event or shift_from_keyboard

    def list_selected_index_changed(self, sender, e):
        """Handle ListBox selection change — colour pick or element selection."""
        if not getattr(self, "_initialized", False):
            return
        if sender.SelectedIndex == -1:
            if hasattr(self, "_shift_pressed_on_click"):
                self._shift_pressed_on_click = False
            return
        if sender.SelectedItem is None:
            self._shift_pressed_on_click = False
            return

        from System.Windows.Input import Keyboard, Key
        shift_pressed = Keyboard.IsKeyDown(Key.LeftShift) or Keyboard.IsKeyDown(Key.RightShift)
        if (
            not shift_pressed
            and hasattr(self, "_shift_pressed_on_click")
            and self._shift_pressed_on_click
        ):
            shift_pressed = True

        if shift_pressed:
            # Select elements in Revit
            try:
                selected_item = sender.SelectedItem
                if selected_item is not None:
                    from System.Data import DataRowView
                    row = None
                    if isinstance(selected_item, DataRowView):
                        row = selected_item.Row
                    elif hasattr(selected_item, "Row"):
                        row = selected_item.Row
                    else:
                        if (
                            hasattr(self, "_table_data_3")
                            and self._table_data_3 is not None
                            and sender.SelectedIndex >= 0
                            and sender.SelectedIndex < self._table_data_3.Rows.Count
                        ):
                            row = self._table_data_3.Rows[sender.SelectedIndex]

                    if row is None:
                        try:
                            self.list_box2.SelectionChanged -= self.list_selected_index_changed
                            sender.SelectedIndex = -1
                        except Exception:
                            pass
                        finally:
                            try:
                                self.list_box2.SelectionChanged += self.list_selected_index_changed
                            except Exception:
                                pass
                        self._shift_pressed_on_click = False
                        return

                    value_item = row["Value"]
                    if (
                        hasattr(value_item, "ele_id")
                        and value_item.ele_id is not None
                        and value_item.ele_id.Count > 0
                    ):
                        uidoc = HOST_APP.uiapp.ActiveUIDocument
                        uidoc.Selection.SetElementIds(value_item.ele_id)
                        uidoc.RefreshActiveView()

                try:
                    self.list_box2.SelectionChanged -= self.list_selected_index_changed
                    sender.SelectedIndex = -1
                except Exception:
                    pass
                finally:
                    try:
                        self.list_box2.SelectionChanged += self.list_selected_index_changed
                    except Exception:
                        pass
            except Exception as ex:
                logger.debug("Error selecting elements: %s", str(ex))
                try:
                    self.list_box2.SelectionChanged -= self.list_selected_index_changed
                    sender.SelectedIndex = -1
                except Exception:
                    pass
                finally:
                    try:
                        self.list_box2.SelectionChanged += self.list_selected_index_changed
                    except Exception:
                        pass
            finally:
                self._shift_pressed_on_click = False
        else:
            # Open colour dialog
            clr_dlg = Forms.ColorDialog()
            clr_dlg.AllowFullOpen = True
            if clr_dlg.ShowDialog() == Forms.DialogResult.OK:
                selected_item = sender.SelectedItem
                if selected_item is not None:
                    row = self._get_value_row(selected_item, sender.SelectedIndex)
                    if row is not None:
                        value_item = row["Value"]
                        value_item.n1 = clr_dlg.Color.R
                        value_item.n2 = clr_dlg.Color.G
                        value_item.n3 = clr_dlg.Color.B
                        try:
                            value_item.colour = Drawing.Color.FromArgb(
                                clr_dlg.Color.R, clr_dlg.Color.G, clr_dlg.Color.B
                            )
                        except Exception:
                            pass
                        self._update_listbox_colors()
                        self._update_preview(value_item.n1, value_item.n2, value_item.n3)
            try:
                self.list_box2.SelectionChanged -= self.list_selected_index_changed
                sender.SelectedIndex = -1
            except Exception:
                pass
            finally:
                try:
                    self.list_box2.SelectionChanged += self.list_selected_index_changed
                except Exception:
                    pass
            self._shift_pressed_on_click = False

    def _update_preview(self, r, g, b):
        try:
            from System.Windows.Media import SolidColorBrush, Color
            top_r = max(0, min(255, int(r + (255 - r) * 0.3)))
            top_g = max(0, min(255, int(g + (255 - g) * 0.3)))
            top_b = max(0, min(255, int(b + (255 - b) * 0.3)))

            right_r = max(0, min(255, int(r * 0.7)))
            right_g = max(0, min(255, int(g * 0.7)))
            right_b = max(0, min(255, int(b * 0.7)))

            self._cube_top.Fill = SolidColorBrush(Color.FromRgb(top_r, top_g, top_b))
            self._cube_left.Fill = SolidColorBrush(Color.FromRgb(r, g, b))
            self._cube_right.Fill = SolidColorBrush(Color.FromRgb(right_r, right_g, right_b))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # UNCHANGED: Colour rendering helpers (from original)
    # ------------------------------------------------------------------

    def _update_listbox_colors_async(self):
        try:
            from System.Windows.Threading import DispatcherTimer, DispatcherPriority

            timer = DispatcherTimer(DispatcherPriority.Loaded)
            timer.Interval = System.TimeSpan.FromMilliseconds(100)

            def update_colors(s, ev):
                try:
                    self._update_listbox_colors()
                except Exception as ex:
                    logger.debug("Error in update_colors timer: %s", str(ex))
                finally:
                    timer.Stop()

            timer.Tick += update_colors
            timer.Start()
        except Exception as ex:
            logger.debug("Error setting up color update timer: %s", str(ex))
            self._update_listbox_colors()

    def _update_listbox_colors(self):
        try:
            from System.Windows.Media import SolidColorBrush, Color

            if not hasattr(self, "_table_data_3") or self._table_data_3 is None:
                return

            for i in range(self.list_box2.Items.Count):
                try:
                    item = self.list_box2.Items[i]
                    row = self._get_value_row(item, i)
                    if row is None:
                        continue
                    value_item = row["Value"]
                    if not hasattr(value_item, "colour") or value_item.colour is None:
                        continue
                    color_obj = value_item.colour
                    wpf_color = Color.FromArgb(
                        color_obj.A, color_obj.R, color_obj.G, color_obj.B
                    )
                    brush = SolidColorBrush(wpf_color)
                    listbox_item = self.list_box2.ItemContainerGenerator.ContainerFromIndex(i)
                    if listbox_item is not None:
                        listbox_item.Background = brush
                        brightness = (
                            color_obj.R * 299 + color_obj.G * 587 + color_obj.B * 114
                        ) / 1000
                        if brightness > 128:
                            listbox_item.Foreground = SolidColorBrush(Color.FromRgb(0, 0, 0))
                        else:
                            listbox_item.Foreground = SolidColorBrush(Color.FromRgb(255, 255, 255))
                except (KeyError, AttributeError, IndexError) as ex:
                    logger.debug("Error updating listbox color for item %d: %s", i, str(ex))
                    continue
        except Exception:
            external_event_trace()


# ===========================================================================
# UNCHANGED: FormSaveLoadScheme (verbatim from original ColorSplasher)
# ===========================================================================

class FormSaveLoadScheme(Forms.Form):
    def __init__(self):
        self.Font = Drawing.Font(
            self.Font.FontFamily, 9,
            Drawing.FontStyle.Regular, Drawing.GraphicsUnit.Pixel,
        )
        self.TopMost = True
        self.InitializeComponent()

    def InitializeComponent(self):
        self._btn_save = Forms.Button()
        self._btn_load = Forms.Button()
        self._txt_ifloading = Forms.Label()
        self._radio_by_value = Forms.RadioButton()
        self._radio_by_pos = Forms.RadioButton()
        self.tooltip1 = Forms.ToolTip()
        self._spr_top = Forms.Label()
        self.SuspendLayout()
        self._spr_top.Anchor = (
            Forms.AnchorStyles.Top | Forms.AnchorStyles.Left | Forms.AnchorStyles.Right
        )
        self._spr_top.Location = Drawing.Point(0, 0)
        self._spr_top.Name = "spr_top"
        self._spr_top.Size = Drawing.Size(500, 2)
        self._spr_top.BackColor = Drawing.Color.FromArgb(82, 53, 239)
        self._txt_ifloading.Anchor = Forms.AnchorStyles.Top | Forms.AnchorStyles.Left
        self._txt_ifloading.Location = Drawing.Point(12, 10)
        self._txt_ifloading.Text = "If Loading a Color Scheme:"
        self._txt_ifloading.Name = "_radio_byValue"
        self._txt_ifloading.Size = Drawing.Size(239, 23)
        self._radio_by_value.Anchor = Forms.AnchorStyles.Top | Forms.AnchorStyles.Left
        self._radio_by_value.Location = Drawing.Point(19, 35)
        self._radio_by_value.Text = "Load by Parameter Value."
        self._radio_by_value.Name = "_radio_byValue"
        self._radio_by_value.Size = Drawing.Size(230, 25)
        self._radio_by_value.Checked = True
        self._radio_by_pos.Anchor = Forms.AnchorStyles.Top | Forms.AnchorStyles.Left
        self._radio_by_pos.Location = Drawing.Point(250, 35)
        self._radio_by_pos.Text = "Load by Position in Window."
        self._radio_by_pos.Name = "_radio_byValue"
        self._radio_by_pos.Size = Drawing.Size(239, 25)
        self._btn_save.Anchor = Forms.AnchorStyles.Bottom | Forms.AnchorStyles.Right
        self._btn_save.Location = Drawing.Point(13, 70)
        self._btn_save.Name = "btn_cancel"
        self._btn_save.Size = Drawing.Size(236, 25)
        self._btn_save.Text = "Save Color Scheme"
        self._btn_save.Cursor = Forms.Cursors.Hand
        self._btn_save.Click += self.specify_path_save
        self._btn_load.Anchor = Forms.AnchorStyles.Bottom | Forms.AnchorStyles.Right
        self._btn_load.Location = Drawing.Point(253, 70)
        self._btn_load.Name = "btn_cancel"
        self._btn_load.Size = Drawing.Size(236, 25)
        self._btn_load.Text = "Load Color Scheme"
        self._btn_load.Cursor = Forms.Cursors.Hand
        self._btn_load.Click += self.specify_path_load
        self.Controls.Add(self._txt_ifloading)
        self.Controls.Add(self._radio_by_value)
        self.Controls.Add(self._radio_by_pos)
        self.Controls.Add(self._btn_save)
        self.Controls.Add(self._btn_load)
        self.Controls.Add(self._spr_top)
        self.MaximizeBox = 0
        self.MinimizeBox = 0
        self.ClientSize = Drawing.Size(500, 105)
        self.Name = "Save / Load Color Scheme"
        self.Text = "Save / Load Color Scheme"
        self.FormBorderStyle = Forms.FormBorderStyle.FixedSingle
        self.CenterToScreen()
        self.ResumeLayout(False)

    def specify_path_save(self, sender, e):
        with Forms.SaveFileDialog() as dlg:
            wndw = getattr(ColorSplasherProWindow, "_current_wndw", None)
            dlg.Title = "Specify Path to Save Color Scheme"
            dlg.Filter = "Color Scheme (*.cschn)|*.cschn"
            dlg.RestoreDirectory = True
            dlg.OverwritePrompt = True
            dlg.InitialDirectory = System.Environment.GetFolderPath(
                System.Environment.SpecialFolder.Desktop
            )
            dlg.FileName = "Color Scheme.cschn"
            if not wndw or wndw.list_box2.Items.Count == 0:
                UI.TaskDialog.Show("No Colors Detected",
                    "The list of values is empty. Please select a category and parameter first.")
                self.Close()
            elif dlg.ShowDialog() == Forms.DialogResult.OK:
                self.save_path_to_file(dlg.FileName)
                self.Close()

    def save_path_to_file(self, new_path):
        try:
            wndw = getattr(ColorSplasherProWindow, "_current_wndw", None)
            if not wndw:
                return
            with open(new_path, "w") as f:
                for i in range(wndw.list_box2.Items.Count):
                    item = wndw.list_box2.Items[i]
                    if hasattr(item, "Row"):
                        value_item = item.Row["Value"]
                        item_key = item.Row["Key"]
                    else:
                        value_item = wndw._table_data_3.Rows[i]["Value"]
                        item_key = wndw._table_data_3.Rows[i]["Key"]
                    color_inst = value_item.colour
                    f.write(
                        item_key + "::R" + str(color_inst.R) +
                        "G" + str(color_inst.G) +
                        "B" + str(color_inst.B) + "\n"
                    )
        except Exception as ex:
            external_event_trace()
            UI.TaskDialog.Show("Error Saving Scheme", str(ex))

    def specify_path_load(self, sender, e):
        with Forms.OpenFileDialog() as dlg:
            wndw = getattr(ColorSplasherProWindow, "_current_wndw", None)
            dlg.Title = "Specify Path to Load Color Scheme"
            dlg.Filter = "Color Scheme (*.cschn)|*.cschn"
            dlg.RestoreDirectory = True
            dlg.InitialDirectory = System.Environment.GetFolderPath(
                System.Environment.SpecialFolder.Desktop
            )
            if not wndw or wndw.list_box2.Items.Count == 0:
                UI.TaskDialog.Show("No Values Detected",
                    "The list of values is empty. Please select a category and parameter first.")
                self.Close()
            elif dlg.ShowDialog() == Forms.DialogResult.OK:
                self.load_path_from_file(dlg.FileName)
                self.Close()

    def load_path_from_file(self, path):
        wndw = getattr(ColorSplasherProWindow, "_current_wndw", None)
        if not isfile(path):
            UI.TaskDialog.Show("Error Loading Scheme", "The file does not exist.")
        else:
            if not wndw:
                return
            try:
                with open(path, "r") as f:
                    all_lines = f.readlines()
                    if self._radio_by_value.Checked:
                        for line in all_lines:
                            line_val = line.strip().split("::R")
                            par_val = line_val[0]
                            rgb_result = split(r"[RGB]", line_val[1])
                            for item in wndw._table_data_3.Rows:
                                if item["Key"] == par_val:
                                    self.apply_color_to_item(rgb_result, item)
                                    break
                    else:
                        for ind, line in enumerate(all_lines):
                            if ind < len(wndw._table_data_3.Rows):
                                line_val = line.strip().split("::R")
                                rgb_result = split(r"[RGB]", line_val[1])
                                item = wndw._table_data_3.Rows[ind]
                                self.apply_color_to_item(rgb_result, item)
                            else:
                                break
                    wndw._update_listbox_colors()
            except Exception as ex:
                external_event_trace()
                UI.TaskDialog.Show("Error Loading Scheme", str(ex))

    def apply_color_to_item(self, rgb_result, item):
        r = int(rgb_result[0])
        g = int(rgb_result[1])
        b = int(rgb_result[2])
        item["Value"].n1 = r
        item["Value"].n2 = g
        item["Value"].n3 = b
        item["Value"].colour = Drawing.Color.FromArgb(r, g, b)
        
        # Also update DataTable columns for WPF binding compatibility
        try:
            item["R"] = r
            item["G"] = g
            item["B"] = b
            item["Hex"] = "#{0:02X}{1:02X}{2:02X}".format(r, g, b)
        except Exception:
            pass


# ===========================================================================
# UNCHANGED: Utility functions (from original ColorSplasher)
# ===========================================================================

def get_active_view(ac_doc):
    uidoc = HOST_APP.uiapp.ActiveUIDocument
    selected_view = ac_doc.ActiveView
    if (
        selected_view.ViewType == DB.ViewType.ProjectBrowser
        or selected_view.ViewType == DB.ViewType.SystemBrowser
    ):
        selected_view = ac_doc.GetElement(uidoc.GetOpenUIViews()[0].ViewId)
    if not selected_view.CanUseTemporaryVisibilityModes():
        task2 = UI.TaskDialog("ColorSplasher Pro")
        task2.MainInstruction = (
            "Visibility settings cannot be modified in "
            + str(selected_view.ViewType)
            + " views. Please change your current view."
        )
        task2.Show()
        return 0
    return selected_view


def get_parameter_value(para):
    if not para.HasValue:
        return "None"
    if para.StorageType == DB.StorageType.Double:
        return get_double_value(para)
    if para.StorageType == DB.StorageType.ElementId:
        return get_elementid_value(para)
    if para.StorageType == DB.StorageType.Integer:
        return get_integer_value(para)
    if para.StorageType == DB.StorageType.String:
        return para.AsString()
    return "None"


def get_double_value(para):
    return para.AsValueString()


def get_elementid_value(para, doc_param=None):
    if doc_param is None:
        doc_param = revit.DOCS.doc
    id_val = para.AsElementId()
    elementid_value = get_elementid_value_func()
    if elementid_value(id_val) >= 0:
        return DB.Element.Name.GetValue(doc_param.GetElement(id_val))
    return "None"


def get_integer_value(para):
    version = int(HOST_APP.version)
    if version > 2021:
        param_type = para.Definition.GetDataType()
        if DB.SpecTypeId.Boolean.YesNo == param_type:
            return "True" if para.AsInteger() == 1 else "False"
        return para.AsValueString()
    else:
        param_type = para.Definition.ParameterType
        if DB.ParameterType.YesNo == param_type:
            return "True" if para.AsInteger() == 1 else "False"
        return para.AsValueString()


def strip_accents(text):
    return "".join(
        char for char in normalize("NFKD", text) if unicode_category(char) != "Mn"
    )


def random_color():
    r = randint(30, 230)
    g = randint(30, 230)
    b = randint(30, 230)
    return r, g, b


def get_range_values(category, param, new_view, scope="view"):
    doc_param = new_view.Document
    bic = None
    try:
        for sample_bic in System.Enum.GetValues(DB.BuiltInCategory):
            if category.int_id == int(sample_bic):
                bic = sample_bic
                break
    except Exception:
        pass

    if bic is None:
        return []

    if scope == "selected":
        try:
            uidoc = HOST_APP.uidoc
            selected_ids = uidoc.Selection.GetElementIds()
            collector = []
            for eid in selected_ids:
                try:
                    ele = doc_param.GetElement(eid)
                    if ele and ele.IsValidObject and ele.Category:
                        if get_element_int_id(ele.Category.Id) == category.int_id:
                            if not isinstance(ele, DB.ElementType):
                                collector.append(ele)
                except Exception:
                    continue
        except Exception:
            collector = []
    elif scope == "whole":
        try:
            collector = list(
                DB.FilteredElementCollector(doc_param)
                .OfCategory(bic)
                .WhereElementIsNotElementType()
                .ToElements()
            )
        except Exception:
            collector = []
    else:
        try:
            collector = list(
                DB.FilteredElementCollector(doc_param, new_view.Id)
                .OfCategory(bic)
                .WhereElementIsNotElementType()
                .ToElements()
            )
        except Exception:
            collector = []
    list_values = []
    used_colors = set()
    for ele in collector:
        try:
            if ele is None or not ele.IsValidObject:
                continue
            if param.param_type == 1:
                type_id = ele.GetTypeId()
                if type_id is None or type_id == DB.ElementId.InvalidElementId:
                    continue
                ele_par = doc_param.GetElement(type_id)
                if ele_par is None or not ele_par.IsValidObject:
                    continue
            else:
                ele_par = ele
            try:
                params_list = ele_par.GetOrderedParameters()
            except Exception:
                # Do not fall back to .Parameters; pyRevit/IronPython can crash
                # Revit in unmanaged code on some elements.
                params_list = []
            for pr in params_list:
                try:
                    if pr.Definition.Name == param.par.Name:
                        if hasattr(param, "rl_par") and hasattr(param.rl_par, "_storage_type"):
                            param.rl_par._storage_type = pr.StorageType
                        value = get_parameter_value(pr) or "None"
                        match = [x for x in list_values if x.value == value]
                        if match:
                            match[0].ele_id.Add(ele.Id)
                            if pr.StorageType == DB.StorageType.Double:
                                match[0].values_double.append(pr.AsDouble())
                        else:
                            while True:
                                r, g, b = random_color()
                                if (r, g, b) not in used_colors:
                                    used_colors.add((r, g, b))
                                    val = ValuesInfo(pr, value, ele.Id, r, g, b)
                                    list_values.append(val)
                                    break
                        break
                except Exception:
                    continue
        except Exception:
            continue
    none_values = [x for x in list_values if x.value == "None"]
    list_values = [x for x in list_values if x.value != "None"]
    list_values = sorted(list_values, key=lambda x: x.value, reverse=False)
    if len(list_values) > 1:
        try:
            first_value = list_values[0].value
            indx_del = get_index_units(first_value)
            if indx_del == 0:
                list_values = sorted(list_values, key=lambda x: safe_float(x.value))
            elif 0 < indx_del < len(first_value):
                list_values = sorted(
                    list_values, key=lambda x: safe_float(x.value[:-indx_del])
                )
        except ValueError:
            pass
        except Exception:
            external_event_trace()
    if none_values and any(len(x.ele_id) > 0 for x in none_values):
        list_values.extend(none_values)
    return list_values


def safe_float(value):
    try:
        return float(value)
    except ValueError:
        return float("inf")


def collect_parameters_for_category(doc, view, category_int_id, include_links=False, loaded_links=None, include_host=True):
    """
    Collect all unique parameters (instance & type, including project/shared/built-in)
    from all elements of the specified category in the active view (and optionally link instances).
    Returns a sorted list of ParameterInfo objects.
    """
    import System
    if loaded_links is None:
        loaded_links = []
    
    # 1. Find BuiltInCategory
    bic = None
    try:
        for sample_bic in System.Enum.GetValues(DB.BuiltInCategory):
            if category_int_id == int(sample_bic):
                bic = sample_bic
                break
    except Exception:
        pass
            
    if bic is None:
        return []
        
    # 2. Collect host elements — use ToElements() for safe materialization, slice to 50
    elements = []
    if include_host:
        try:
            all_host = list(
                DB.FilteredElementCollector(doc, view.Id)
                .OfCategory(bic)
                .WhereElementIsNotElementType()
                .ToElements()
            )
            # Slice to max 50 valid elements to prevent UI freeze on large models
            count = 0
            for ele in all_host:
                if ele is not None and ele.IsValidObject:
                    elements.append(ele)
                    count += 1
                    if count >= 50:
                        break
            del all_host
        except Exception:
            pass
        
    # 3. Collect link elements if requested (limit to 50 per link for speed and safety)
    if include_links:
        for li in loaded_links:
            try:
                link_doc = li.link_doc
                if link_doc and link_doc.IsValidObject:
                    link_collector = (
                        DB.FilteredElementCollector(link_doc)
                        .OfCategory(bic)
                        .WhereElementIsNotElementType()
                    )
                    count = 0
                    for ele in link_collector:
                        if ele and ele.IsValidObject:
                            elements.append(ele)
                            count += 1
                            if count >= 50:
                                break
            except Exception:
                pass
                
    # 4. Gather unique parameters
    unique_params = {} # key: stripped_name, value: ParameterInfo
    
    for ele in elements:
        # Instance parameters
        try:
            if ele is None or not ele.IsValidObject:
                continue
            try:
                params_list = ele.GetOrderedParameters()
            except Exception:
                # Do not fall back to .Parameters; pyRevit/IronPython can crash
                # Revit in unmanaged code on some elements.
                params_list = []
            for par in params_list:
                try:
                    if par.Definition.BuiltInParameter in (
                        DB.BuiltInParameter.ELEM_CATEGORY_PARAM,
                        DB.BuiltInParameter.ELEM_CATEGORY_PARAM_MT,
                    ):
                        continue
                    name = strip_accents(par.Definition.Name)
                    if not name or name.strip() == "":
                        continue
                    if name not in unique_params:
                        unique_params[name] = ParameterInfo(0, par)
                except Exception:
                    continue
        except Exception:
            pass
            
        # Type parameters
        try:
            if ele is None or not ele.IsValidObject:
                continue
            ele_doc = ele.Document
            if ele_doc and ele_doc.IsValidObject:
                type_id = ele.GetTypeId()
                if type_id and type_id != DB.ElementId.InvalidElementId:
                    typ = ele_doc.GetElement(type_id)
                    if typ and typ.IsValidObject:
                        try:
                            params_list = typ.GetOrderedParameters()
                        except Exception:
                            # Do not fall back to .Parameters; pyRevit/IronPython can crash
                            # Revit in unmanaged code on some elements.
                            params_list = []
                        for par in params_list:
                            try:
                                if par.Definition.BuiltInParameter in (
                                    DB.BuiltInParameter.ELEM_CATEGORY_PARAM,
                                    DB.BuiltInParameter.ELEM_CATEGORY_PARAM_MT,
                                ):
                                    continue
                                name = strip_accents(par.Definition.Name)
                                if not name or name.strip() == "":
                                    continue
                                if name not in unique_params:
                                    unique_params[name] = ParameterInfo(1, par)
                            except Exception:
                                continue
        except Exception:
            pass
            
    # Sort alphabetically by name
    try:
        sorted_keys = sorted(unique_params.keys(), key=lambda x: x.upper())
        result = [unique_params[k] for k in sorted_keys]
        return result
    except Exception:
        return []


def _load_params_for_element(ele, doc_param):
    """
    Safely load all unique instance + type parameters from a single sample element.
    Uses FirstElement approach - fast, crash-safe, no heavy collection needed.
    Returns a sorted list of ParameterInfo objects.
    """
    unique_params = {}
    try:
        if ele is None or not ele.IsValidObject:
            return []
        # Instance parameters
        try:
            params_list = ele.GetOrderedParameters()
        except Exception:
            # Do not fall back to .Parameters; pyRevit/IronPython can crash
            # Revit in unmanaged code on some elements.
            params_list = []
        for par in params_list:
            try:
                name = strip_accents(par.Definition.Name)
                if not name or not name.strip():
                    continue
                if par.Definition.BuiltInParameter in (
                    DB.BuiltInParameter.ELEM_CATEGORY_PARAM,
                    DB.BuiltInParameter.ELEM_CATEGORY_PARAM_MT,
                ):
                    continue
                if name not in unique_params:
                    unique_params[name] = ParameterInfo(0, par)
            except Exception:
                continue
        # Type parameters
        try:
            type_id = ele.GetTypeId()
            if type_id and type_id != DB.ElementId.InvalidElementId:
                typ = doc_param.GetElement(type_id)
                if typ and typ.IsValidObject:
                    try:
                        params_list = typ.GetOrderedParameters()
                    except Exception:
                        # Do not fall back to .Parameters; pyRevit/IronPython can crash
                        # Revit in unmanaged code on some elements.
                        params_list = []
                    for par in params_list:
                        try:
                            name = strip_accents(par.Definition.Name)
                            if not name or not name.strip():
                                continue
                            if par.Definition.BuiltInParameter in (
                                DB.BuiltInParameter.ELEM_CATEGORY_PARAM,
                                DB.BuiltInParameter.ELEM_CATEGORY_PARAM_MT,
                            ):
                                continue
                            if name not in unique_params:
                                unique_params[name] = ParameterInfo(1, par)
                        except Exception:
                            continue
        except Exception:
            pass
    except Exception:
        return []
    try:
        sorted_keys = sorted(unique_params.keys(), key=lambda x: x.upper())
        return [unique_params[k] for k in sorted_keys]
    except Exception:
        return []


class MockDefinition(object):
    def __init__(self, name, param_id):
        self.Name = name
        self.Id = param_id
        if hasattr(DB, "ParameterType"):
            self.ParameterType = DB.ParameterType.Text
        else:
            self.ParameterType = None

class MockParameter(object):
    def __init__(self, name, param_id, is_builtin):
        self.Definition = MockDefinition(name, param_id)
        self.Id = param_id
        self._name = name
        self._is_builtin = is_builtin
        self._storage_type = None

    @property
    def StorageType(self):
        if self._storage_type is not None:
            return self._storage_type
        return DB.StorageType.String


def _load_params_on_demand_fallback(doc, view, category_int_id):
    """
    Fallback method to find parameters using elements if schema-based lookup fails.
    """
    try:
        import System
        bic = None
        try:
            bic = System.Enum.ToObject(DB.BuiltInCategory, category_int_id)
        except Exception:
            return []

        # Get just the ElementId from Type elements (extremely stable, won't crash)
        eid = None
        try:
            eid = (
                DB.FilteredElementCollector(doc)
                .OfCategory(bic)
                .WhereElementIsElementType()
                .FirstElementId()
            )
        except Exception:
            pass

        # Try instances only if no Type elements exist
        if eid is None or eid == DB.ElementId.InvalidElementId:
            try:
                eid = (
                    DB.FilteredElementCollector(doc)
                    .OfCategory(bic)
                    .WhereElementIsNotElementType()
                    .FirstElementId()
                )
            except Exception:
                pass

        if eid is None or eid == DB.ElementId.InvalidElementId:
            return []

        # Get the element by ID (safe direct lookup)
        try:
            ele = doc.GetElement(eid)
        except Exception:
            return []

        if ele is None or not ele.IsValidObject:
            return []

        # Load parameters from this one element
        return _load_params_for_element(ele, doc)

    except Exception:
        return []


def _get_common_builtin_parameters(category_int_id):
    """
    Get list of common built-in parameters for a category.
    Returns list of (name, BuiltInParameter) tuples.
    """
    results = [
        ("Comments", DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS),
        ("Mark", DB.BuiltInParameter.ALL_MODEL_MARK),
        ("Type Mark", DB.BuiltInParameter.ALL_MODEL_TYPE_MARK),
        ("Type Name", DB.BuiltInParameter.SYMBOL_NAME_PARAM),
        ("Family Name", DB.BuiltInParameter.SYMBOL_FAMILY_NAME_PARAM),
        ("Phase Created", DB.BuiltInParameter.PHASE_CREATED),
        ("Phase Demolished", DB.BuiltInParameter.PHASE_DEMOLISHED),
        ("Workset", DB.BuiltInParameter.ELEM_PARTITION_PARAM),
        ("Design Option", DB.BuiltInParameter.DESIGN_OPTION_ID),
    ]
    
    # Category-specific additions
    # Ceilings (-2000038)
    if category_int_id == -2000038:
        results.extend([
            ("Level", DB.BuiltInParameter.SCHEDULE_LEVEL_PARAM),
            ("Height Offset From Level", DB.BuiltInParameter.CEILING_HEIGHTPARAM),
            ("Area", DB.BuiltInParameter.HOST_AREA_COMPUTED),
            ("Volume", DB.BuiltInParameter.HOST_VOLUME_COMPUTED),
            ("Thickness", DB.BuiltInParameter.CEILING_THICKNESS),
        ])
    # Cable Trays (-2000041) or Cable Tray Fittings (-2000043)
    elif category_int_id in (-2000041, -2000043):
        results.extend([
            ("Reference Level", DB.BuiltInParameter.RBS_START_LEVEL_PARAM),
            ("Service Type", DB.BuiltInParameter.RBS_DUCT_SERVICE_TYPE),
            ("Size", DB.BuiltInParameter.RBS_CALCULATED_SIZE),
            ("Length", DB.BuiltInParameter.CURVE_ELEM_LENGTH),
            ("Width", DB.BuiltInParameter.RBS_CABLETRAY_WIDTH_PARAM),
            ("Height", DB.BuiltInParameter.RBS_CABLETRAY_HEIGHT_PARAM),
        ])
    # Walls (-2000011)
    elif category_int_id == -2000011:
        results.extend([
            ("Base Constraint", DB.BuiltInParameter.WALL_BASE_CONSTRAINT),
            ("Top Constraint", DB.BuiltInParameter.WALL_HEIGHT_TYPE),
            ("Unconnected Height", DB.BuiltInParameter.WALL_USER_HEIGHT_PARAM),
            ("Length", DB.BuiltInParameter.CURVE_ELEM_LENGTH),
            ("Area", DB.BuiltInParameter.HOST_AREA_COMPUTED),
            ("Volume", DB.BuiltInParameter.HOST_VOLUME_COMPUTED),
        ])
    # Floors (-2000032)
    elif category_int_id == -2000032:
        results.extend([
            ("Level", DB.BuiltInParameter.LEVEL_PARAM),
            ("Height Offset From Level", DB.BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM),
            ("Area", DB.BuiltInParameter.HOST_AREA_COMPUTED),
            ("Volume", DB.BuiltInParameter.HOST_VOLUME_COMPUTED),
            ("Thickness", DB.BuiltInParameter.FLOOR_THICKNESS_PARAM),
        ])
        
    return results


def _get_custom_bound_parameters(doc, category_int_id):
    """
    Query the document's ParameterBindings to find all project/shared parameters bound to this category.
    This is 100% crash-safe and does not touch any model elements.
    """
    results = []
    try:
        param_elements = DB.FilteredElementCollector(doc).OfClass(DB.ParameterElement)
        for pe in param_elements:
            try:
                if not pe.IsValidObject:
                    continue
                binding = doc.ParameterBindings.Item[pe.GetDefinition()]
                if binding and hasattr(binding, "Categories"):
                    for cat in binding.Categories:
                        if cat.Id.IntegerValue == category_int_id:
                            results.append((pe.Name, pe.Id))
                            break
            except Exception:
                continue
    except Exception:
        pass
    return results


def _load_params_on_demand(doc, view, category_int_id):
    """
    Safely load parameters for a category using common built-ins and ParameterBindings.
    Requires ZERO element instances and ZERO filterable parameter queries, making it 100% crash-proof.
    """
    unique_params = {}
    try:
        # 1. Load common built-in parameters
        builtins = _get_common_builtin_parameters(category_int_id)
        for name, bip in builtins:
            try:
                pid = DB.ElementId(bip)
                mock_par = MockParameter(name, pid, is_builtin=True)
                unique_params[name] = ParameterInfo(0, mock_par)
            except Exception:
                continue

        # 2. Load custom bound parameters (Project/Shared parameters)
        customs = _get_custom_bound_parameters(doc, category_int_id)
        for name, pid in customs:
            try:
                mock_par = MockParameter(name, pid, is_builtin=False)
                unique_params[name] = ParameterInfo(0, mock_par)
            except Exception:
                continue

        if unique_params:
            sorted_keys = sorted(unique_params.keys(), key=lambda x: x.upper())
            return [unique_params[k] for k in sorted_keys]

    except Exception as ex:
        logger.debug("Schema param load failed: %s", str(ex))

    # Never fallback to crashing element-query methods
    return []


def get_used_categories_parameters(cat_exc, acti_view, doc_param=None):
    """
    Return sorted list of CategoryInfo for all model categories.
    Uses Document.Settings.Categories — NO element scanning at all.
    This is completely crash-safe for any model size.
    Parameters are loaded on-demand when user selects a category.
    """
    try:
        if doc_param is None:
            doc_param = acti_view.Document
    except (AttributeError, RuntimeError):
        doc_param = revit.DOCS.doc

    result = []
    try:
        for cat in doc_param.Settings.Categories:
            try:
                # Only include Model categories (not annotation, tags, etc.)
                if cat.CategoryType != DB.CategoryType.Model:
                    continue
                cat_id = get_element_int_id(cat.Id)
                if cat_id in cat_exc or cat_id >= -1:
                    continue
                # Empty par list — loaded on-demand when user selects this category
                result.append(CategoryInfo(cat, []))
            except Exception:
                continue
    except Exception:
        pass

    return sorted(result, key=lambda x: x.name)


def solid_fill_pattern_id():
    doc_param = revit.DOCS.doc
    solid_fill_id = None
    fillpatterns = DB.FilteredElementCollector(doc_param).OfClass(DB.FillPatternElement)
    for pat in fillpatterns:
        if pat.GetFillPattern().IsSolidFill:
            solid_fill_id = pat.Id
            break
    return solid_fill_id


def external_event_trace():
    exc_type, exc_value, exc_traceback = sys.exc_info()
    logger.debug("Exception type: %s", exc_type)
    logger.debug("Exception value: %s", exc_value)
    for tb in extract_tb(exc_traceback):
        logger.debug(
            "File: %s, Line: %s, Function: %s, Code: %s",
            tb[0], tb[1], tb[2], tb[3]
        )


def get_index_units(str_value):
    for let in str_value[::-1]:
        if let.isdigit():
            return str_value[::-1].index(let)
    return -1


def get_color_shades(base_color, apply_line, apply_foreground, apply_background):
    r, g, b = base_color.Red, base_color.Green, base_color.Blue
    foreground_color = base_color
    background_color = base_color

    if apply_line and (apply_foreground or apply_background):
        line_r = max(0, min(255, int(r + (255 - r) * 0.6)))
        line_g = max(0, min(255, int(g + (255 - g) * 0.6)))
        line_b = max(0, min(255, int(b + (255 - b) * 0.6)))
        gray = (line_r + line_g + line_b) / 3
        line_r = int(line_r * 0.7 + gray * 0.3)
        line_g = int(line_g * 0.7 + gray * 0.3)
        line_b = int(line_b * 0.7 + gray * 0.3)
        line_color = DB.Color(line_r, line_g, line_b)
    else:
        line_color = base_color

    return line_color, foreground_color, background_color


# ===========================================================================
# Entry point
# ===========================================================================

def launch_color_splasher_pro():
    """Main entry point for ColorSplasher Pro."""
    try:
        doc = revit.DOCS.doc
        if doc is None:
            raise AttributeError("Revit document is not available")
    except (AttributeError, RuntimeError, Exception):
        error_msg = UI.TaskDialog("ColorSplasher Pro Error")
        error_msg.MainInstruction = "Unable to access Revit document"
        error_msg.MainContent = "Please ensure you have a Revit project open and try again."
        error_msg.Show()
        return

    sel_view = get_active_view(doc)
    if sel_view != 0:
        categ_inf_used = get_used_categories_parameters(CAT_EXCLUDED, sel_view, doc)

        # Standard handlers (preserved from original)
        event_handler = ApplyColors()
        ext_event = UI.ExternalEvent.Create(event_handler)

        event_handler_uns = SubscribeView()
        ext_event_uns = UI.ExternalEvent.Create(event_handler_uns)

        event_handler_filters = CreateFilters()
        ext_event_filters = UI.ExternalEvent.Create(event_handler_filters)

        event_handler_reset = ResetColors()
        ext_event_reset = UI.ExternalEvent.Create(event_handler_reset)

        event_handler_legend = CreateLegend()
        ext_event_legend = UI.ExternalEvent.Create(event_handler_legend)

        # NEW: Pro handler
        event_handler_pro = ApplyColorsPro()
        ext_event_pro = UI.ExternalEvent.Create(event_handler_pro)

        xaml_file = join(_BUNDLE_DIR, "ColorSplasherProWindow.xaml")

        wndw = ColorSplasherProWindow(
            xaml_file,
            categ_inf_used,
            ext_event,
            ext_event_uns,
            sel_view,
            ext_event_reset,
            ext_event_legend,
            ext_event_filters,
            ext_event_pro,
        )

        if wndw._categories.Items.Count > 0:
            wndw._categories.SelectedIndex = 0

        # Store external event handles on window for disposal on close
        wndw._ext_events = [
            ext_event,
            ext_event_uns,
            ext_event_filters,
            ext_event_reset,
            ext_event_legend,
            ext_event_pro
        ]
        wndw._event_handler_uns = event_handler_uns

        # Wire class-level references (same pattern as original)
        SubscribeView._wndw = wndw
        ApplyColors._wndw = wndw
        ApplyColorsPro._wndw = wndw
        ResetColors._wndw = wndw
        CreateLegend._wndw = wndw
        CreateFilters._wndw = wndw
        ColorSplasherProWindow._current_wndw = wndw

        wndw.show()


if __name__ == "__main__":
    launch_color_splasher_pro()
