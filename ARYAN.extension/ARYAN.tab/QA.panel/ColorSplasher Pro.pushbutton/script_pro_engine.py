# -- coding: utf-8 --
"""
ColorSplasher Pro Engine
ARYAN extension upgrade of pyRevit ColorSplasher.

Contains:
  - Compatibility wrappers (Revit 2019-2027, IronPython)
  - Multi-parameter compound key coloring
  - Numeric heat map engine
  - Revit link element collection
  - Export engine (CSV, JSON)
  - Value search/filter helpers
  - Count aggregation helpers

DO NOT modify existing ColorSplasher classes.
All functions here are NEW additions.
"""

import sys
import os
import json
import math
from datetime import datetime
from random import randint
from unicodedata import normalize
from unicodedata import category as unicode_category

def strip_accents(text):
    if not text:
        return ""
    try:
        if isinstance(text, str):
            text = text.decode('utf-8') if hasattr(text, 'decode') else text
        return "".join(
            char for char in normalize("NFKD", text) if unicode_category(char) != "Mn"
        )
    except Exception:
        return text

try:
    from pyrevit import DB, HOST_APP, revit
    from pyrevit.compat import get_elementid_value_func
except ImportError:
    pass

try:
    import clr
    clr.AddReference('RevitAPI')
    from Autodesk.Revit.DB import (
        FilteredElementCollector,
        RevitLinkInstance,
        RevitLinkType,
        BuiltInCategory,
        FillPatternElement,
        StorageType,
        ElementId,
        Color as RevitColor,
    )
except Exception:
    pass


# ---------------------------------------------------------------------------
# Compatibility helpers
# ---------------------------------------------------------------------------

def get_revit_version():
    """Return Revit version as integer (e.g. 2024). Safe across all versions."""
    try:
        return int(HOST_APP.version)
    except Exception:
        try:
            return int(revit.app.VersionNumber)
        except Exception:
            return 2021


def get_element_int_id(element_id):
    """Cross-version ElementId integer value (2019-2027)."""
    if element_id is None:
        return -1
    try:
        return int(element_id.Value)  # 2024+
    except AttributeError:
        pass
    try:
        return int(element_id.IntegerValue)  # 2019-2023
    except AttributeError:
        pass
    try:
        func = get_elementid_value_func()
        return func(element_id)
    except Exception:
        return -1


def create_equals_rule_string(parameter_id, value, version):
    """Create a string equals filter rule compatible with Revit 2019-2027."""
    try:
        from pyrevit import DB as _DB
        if version > 2023:
            return _DB.ParameterFilterRuleFactory.CreateEqualsRule(
                parameter_id, value
            )
        else:
            return _DB.ParameterFilterRuleFactory.CreateEqualsRule(
                parameter_id, value, True
            )
    except Exception:
        return None


def solid_fill_pattern_id_for_doc(doc):
    """Find the solid fill pattern Id in the given document."""
    try:
        from pyrevit import DB as _DB
        patterns = _DB.FilteredElementCollector(doc).OfClass(_DB.FillPatternElement)
        for p in patterns:
            if p.GetFillPattern().IsSolidFill:
                return p.Id
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Multi-parameter compound key helpers
# ---------------------------------------------------------------------------

DELIMITER = u' | '


def get_param_value_safe(element, param_name, doc):
    """
    Read parameter value from element (instance first, then type).
    Returns string representation or 'None'.
    """
    try:
        from pyrevit import DB as _DB
        # Instance parameters
        for pr in element.Parameters:
            try:
                if strip_accents(pr.Definition.Name) == strip_accents(param_name):
                    return _read_single_param(pr, doc)
            except Exception:
                continue
        # Type parameters
        typ = element.Document.GetElement(element.GetTypeId())
        if typ:
            for pr in typ.Parameters:
                try:
                    if strip_accents(pr.Definition.Name) == strip_accents(param_name):
                        return _read_single_param(pr, doc)
                except Exception:
                    continue
    except Exception:
        pass
    return u'None'


def _read_single_param(pr, doc):
    """Read a single parameter object to string."""
    try:
        from pyrevit import DB as _DB
        if not pr.HasValue:
            return u'None'
        if pr.StorageType == _DB.StorageType.String:
            v = pr.AsString()
            return v if v else u'None'
        if pr.StorageType == _DB.StorageType.Double:
            v = pr.AsValueString()
            return v if v else u'None'
        if pr.StorageType == _DB.StorageType.Integer:
            version = get_revit_version()
            if version > 2021:
                pt = pr.Definition.GetDataType()
                if _DB.SpecTypeId.Boolean.YesNo == pt:
                    return u'True' if pr.AsInteger() == 1 else u'False'
            else:
                pt = pr.Definition.ParameterType
                if _DB.ParameterType.YesNo == pt:
                    return u'True' if pr.AsInteger() == 1 else u'False'
            v = pr.AsValueString()
            return v if v else str(pr.AsInteger())
        if pr.StorageType == _DB.StorageType.ElementId:
            id_val = pr.AsElementId()
            if get_element_int_id(id_val) >= 0:
                elem = doc.GetElement(id_val)
                if elem:
                    try:
                        return elem.Name or u'None'
                    except Exception:
                        pass
            return u'None'
    except Exception:
        pass
    return u'None'


def build_compound_key(element, param_names, doc):
    """
    Build compound key string from multiple parameter names.
    E.g. 'Generic 8" | Level 01'
    """
    parts = []
    for name in param_names:
        if name:
            parts.append(get_param_value_safe(element, name, doc))
    return DELIMITER.join(parts) if parts else u'None'


# ---------------------------------------------------------------------------
# Numeric Heat Map engine
# ---------------------------------------------------------------------------

class HeatMapRange(object):
    """Represents one range band in a heat map."""

    def __init__(self, label, min_val, max_val, r, g, b):
        self.label = label
        self.min_val = min_val
        self.max_val = max_val
        self.r = r
        self.g = g
        self.b = b


def _lerp_color(r1, g1, b1, r2, g2, b2, t):
    """Linear interpolation between two RGB colours. t in [0,1]."""
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))


def build_heat_map_ranges(numeric_values, num_bands=5, custom_ranges=None):
    """
    Build heat map colour bands from a list of numeric values.

    Args:
        numeric_values: list of float
        num_bands: number of auto bands (ignored if custom_ranges given)
        custom_ranges: optional list of (label, min, max) tuples

    Returns:
        list of HeatMapRange
    """
    # Colour stops: green to yellow to orange to red
    stops = [
        (0,   200,  80),
        (255, 220,   0),
        (255, 140,   0),
        (220,  30,  30),
    ]

    if not numeric_values:
        return []

    if custom_ranges:
        ranges = []
        total = len(custom_ranges)
        for idx, (label, mn, mx) in enumerate(custom_ranges):
            t = float(idx) / max(total - 1, 1)
            stop_idx = t * (len(stops) - 1)
            s0 = int(stop_idx)
            s1 = min(s0 + 1, len(stops) - 1)
            local_t = stop_idx - s0
            r, g, b = _lerp_color(
                stops[s0][0], stops[s0][1], stops[s0][2],
                stops[s1][0], stops[s1][1], stops[s1][2],
                local_t
            )
            ranges.append(HeatMapRange(label, mn, mx, r, g, b))
        return ranges

    min_v = min(numeric_values)
    max_v = max(numeric_values)
    if max_v == min_v:
        r, g, b = stops[0]
        return [HeatMapRange(str(min_v), min_v, max_v, r, g, b)]

    band_size = (max_v - min_v) / float(num_bands)
    ranges = []
    for i in range(num_bands):
        band_min = min_v + i * band_size
        band_max = min_v + (i + 1) * band_size
        t = float(i) / max(num_bands - 1, 1)
        stop_idx = t * (len(stops) - 1)
        s0 = int(stop_idx)
        s1 = min(s0 + 1, len(stops) - 1)
        local_t = stop_idx - s0
        r, g, b = _lerp_color(
            stops[s0][0], stops[s0][1], stops[s0][2],
            stops[s1][0], stops[s1][1], stops[s1][2],
            local_t
        )
        label = '{0:.2f} - {1:.2f}'.format(band_min, band_max)
        ranges.append(HeatMapRange(label, band_min, band_max, r, g, b))
    return ranges


def classify_heat_map(float_value, ranges):
    """
    Return the HeatMapRange that contains float_value.
    Returns the last range if value exceeds all ranges.
    """
    if not ranges:
        return None
    for rng in ranges:
        if rng.min_val <= float_value <= rng.max_val:
            return rng
    if float_value > ranges[-1].max_val:
        return ranges[-1]
    return ranges[0]


def try_parse_float(value_string):
    """
    Attempt to parse a numeric value from a Revit parameter string.
    Strips trailing units (e.g. ' m', ' m2', ' kN').
    Returns float or None.
    """
    if value_string is None or value_string == 'None':
        return None
    s = value_string.strip()
    for sep in [' ', '\t']:
        parts = s.rsplit(sep, 1)
        if len(parts) == 2:
            try:
                return float(parts[0].replace(',', '.'))
            except ValueError:
                pass
    try:
        return float(s.replace(',', '.'))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Revit Link support
# ---------------------------------------------------------------------------

class LinkInfo(object):
    """Metadata about a loaded Revit link."""

    def __init__(self, link_instance, link_doc, link_name):
        self.link_instance = link_instance
        self.link_doc = link_doc
        self.link_name = link_name


def get_loaded_links(doc):
    """
    Return list of LinkInfo for all loaded Revit links in the host document.
    """
    results = []
    try:
        from pyrevit import DB as _DB
        collector = _DB.FilteredElementCollector(doc).OfClass(_DB.RevitLinkInstance)
        for link_inst in collector:
            try:
                link_doc = link_inst.GetLinkDocument()
                if link_doc is None:
                    continue
                link_name = link_inst.Name or 'Unknown Link'
                results.append(LinkInfo(link_inst, link_doc, link_name))
            except Exception:
                continue
    except Exception:
        pass
    return results


def collect_elements_from_link(link_info, category_int_id, view=None):
    """
    Collect elements from a Revit link document by category.
    Note: View-scoped collection is not available for links;
    we collect all elements of the category in the link.

    Args:
        link_info: LinkInfo object
        category_int_id: integer built-in category id
        view: ignored (links do not support view-scoped collection)

    Returns:
        list of (element, link_name)
    """
    results = []
    try:
        from pyrevit import DB as _DB
        link_doc = link_info.link_doc
        link_name = link_info.link_name

        import System
        bic = None
        for sample_bic in System.Enum.GetValues(_DB.BuiltInCategory):
            if category_int_id == int(sample_bic):
                bic = sample_bic
                break
        if bic is None:
            try:
                bic = _DB.BuiltInCategory(category_int_id)
            except Exception:
                pass
        if bic is None:
            return results

        collector = (
            _DB.FilteredElementCollector(link_doc)
            .OfCategory(bic)
            .WhereElementIsNotElementType()
            .ToElements()
        )
        for ele in collector:
            results.append((ele, link_name))
    except Exception:
        pass
    return results


def get_categories_from_link(link_info, cat_excluded):
    """
    Return set of (category_name, int_category_id) tuples from a link document.
    """
    results = set()
    try:
        from pyrevit import DB as _DB
        link_doc = link_info.link_doc
        collector = (
            _DB.FilteredElementCollector(link_doc)
            .WhereElementIsNotElementType()
            .ToElements()
        )
        for ele in collector:
            if ele.Category is None:
                continue
            cat_id_int = get_element_int_id(ele.Category.Id)
            if cat_id_int in cat_excluded or cat_id_int >= -1:
                continue
            results.add((ele.Category.Name, cat_id_int))
    except Exception:
        pass
    return results


# ---------------------------------------------------------------------------
# Value search / filter helpers
# ---------------------------------------------------------------------------

def filter_value_items(all_items, search_text):
    """
    Filter a list of value items by search_text (case-insensitive).
    all_items: list of objects with .value attribute (string)
    Returns filtered list.
    """
    if not search_text:
        return all_items
    lower = search_text.lower().strip()
    if not lower:
        return all_items
    return [item for item in all_items if lower in (item.value or '').lower()]


def sort_value_items(items, sort_mode):
    """
    Sort items by sort_mode.
    sort_mode: 'az' | 'za' | 'count_asc' | 'count_desc'
    items: list of objects with .value and .ele_id attributes
    """
    if sort_mode == 'az':
        return sorted(items, key=lambda x: (x.value or '').lower())
    elif sort_mode == 'za':
        return sorted(items, key=lambda x: (x.value or '').lower(), reverse=True)
    elif sort_mode == 'count_asc':
        return sorted(items, key=lambda x: x.ele_id.Count if hasattr(x.ele_id, 'Count') else len(x.ele_id))
    elif sort_mode == 'count_desc':
        return sorted(items, key=lambda x: x.ele_id.Count if hasattr(x.ele_id, 'Count') else len(x.ele_id), reverse=True)
    return items


def get_item_count(value_item):
    """Return element count for a ValuesInfo object."""
    try:
        ele_id = value_item.ele_id
        if hasattr(ele_id, 'Count'):
            return ele_id.Count
        return len(ele_id)
    except Exception:
        return 0


def build_display_key_with_count(value, count):
    """Format: 'Generic 8" (214)'"""
    return u'{0}  ({1})'.format(value, count)


# ---------------------------------------------------------------------------
# Export engine (CSV and JSON)
# ---------------------------------------------------------------------------

def export_to_csv(items, filepath, category_name, param_name, view_name):
    """
    Export value/color/count data to CSV.

    Args:
        items: list of ValuesInfo objects
        filepath: string path to output .csv file
        category_name: string
        param_name: string
        view_name: string

    Returns:
        (success, message)
    """
    try:
        date_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        lines = [
            'Value,Count,HEX,R,G,B,Category,Parameter,ViewName,Date'
        ]
        for item in items:
            count = get_item_count(item)
            r, g, b = item.n1, item.n2, item.n3
            hex_color = '#{0:02X}{1:02X}{2:02X}'.format(r, g, b)
            value = _escape_csv(item.value)
            cat = _escape_csv(category_name)
            par = _escape_csv(param_name)
            vn = _escape_csv(view_name)
            lines.append(u'{0},{1},{2},{3},{4},{5},{6},{7},{8},{9}'.format(
                value, count, hex_color, r, g, b, cat, par, vn, date_str
            ))
        content = u'\n'.join(lines)
        with open(filepath, 'w') as f:
            f.write(content)
        return True, u'Exported {0} rows to: {1}'.format(len(items), filepath)
    except Exception as ex:
        return False, u'Export failed: {0}'.format(str(ex))


def export_to_json(items, filepath, category_name, param_name, view_name):
    """
    Export value/color/count data to JSON.

    Returns:
        (success, message)
    """
    try:
        date_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        data = {
            'metadata': {
                'category': category_name,
                'parameter': param_name,
                'view': view_name,
                'date': date_str,
                'tool': 'ARYAN ColorSplasher Pro'
            },
            'entries': []
        }
        for item in items:
            count = get_item_count(item)
            r, g, b = item.n1, item.n2, item.n3
            hex_color = '#{0:02X}{1:02X}{2:02X}'.format(r, g, b)
            entry = {
                'value': item.value,
                'count': count,
                'hex': hex_color,
                'rgb': {'r': r, 'g': g, 'b': b}
            }
            data['entries'].append(entry)
        json_str = json.dumps(data, indent=2, ensure_ascii=False)
        with open(filepath, 'w') as f:
            f.write(json_str)
        return True, u'Exported {0} entries to: {1}'.format(len(items), filepath)
    except Exception as ex:
        return False, u'JSON export failed: {0}'.format(str(ex))


def _escape_csv(value):
    """Escape a value for CSV output."""
    if value is None:
        return u''
    text = str(value)
    if u',' in text or u'"' in text or u'\n' in text:
        text = text.replace(u'"', u'""')
        return u'"' + text + u'"'
    return text


# ---------------------------------------------------------------------------
# Multi-parameter value list builder
# ---------------------------------------------------------------------------

def get_range_values_multi(
    category_info,
    primary_param_info,
    additional_param_names,
    view,
    doc,
    link_elements=None,
    scope="view"
):
    """
    Build a value list with compound keys from any number of parameters.
    Formats compound keys as 'Param1 = Val1 | Param2 = Val2' for readability.
    """
    try:
        from pyrevit import DB as _DB
        from pyrevit import HOST_APP
        import System
        from pyrevit.framework import List
    except Exception:
        return []

    bic = None
    try:
        for sample_bic in System.Enum.GetValues(_DB.BuiltInCategory):
            if category_info.int_id == int(sample_bic):
                bic = sample_bic
                break
    except Exception:
        pass

    if bic is None:
        return []

    host_elements = []
    if scope != "none":
        try:
            if scope == "selected":
                uidoc = HOST_APP.uidoc
                selected_ids = uidoc.Selection.GetElementIds()
                collector = []
                for eid in selected_ids:
                    try:
                        ele = doc.GetElement(eid)
                        if ele and ele.IsValidObject and ele.Category:
                            # Use helper function or manual int id retrieval
                            # Let's import get_element_int_id from script_pro_engine
                            if int(ele.Category.Id.IntegerValue) == category_info.int_id:
                                if not isinstance(ele, _DB.ElementType):
                                    collector.append(ele)
                    except Exception:
                        continue
            elif scope == "whole":
                collector = (
                    _DB.FilteredElementCollector(doc)
                    .OfCategory(bic)
                    .WhereElementIsNotElementType()
                    .ToElements()
                )
            else:
                # Default: current view
                collector = (
                    _DB.FilteredElementCollector(doc, view.Id)
                    .OfCategory(bic)
                    .WhereElementIsNotElementType()
                    .ToElements()
                )
            host_elements = [(ele, None) for ele in collector]
        except Exception:
            host_elements = []

    all_element_pairs = list(host_elements)
    if link_elements:
        all_element_pairs.extend(link_elements)

    list_values = []
    used_colors = set()
    primary_param_name = primary_param_info.par.Name

    for (ele, link_name) in all_element_pairs:
        ele_doc = ele.Document if hasattr(ele, 'Document') else doc

        primary_val = get_param_value_safe(ele, primary_param_name, ele_doc)

        parts = [u"{} = {}".format(primary_param_name, primary_val)]
        for name in additional_param_names:
            if name:
                parts.append(u"{} = {}".format(name, get_param_value_safe(ele, name, ele_doc)))
        if link_name:
            parts.append(u"Link = {}".format(link_name))

        compound_key = DELIMITER.join(parts)

        raw_param = None
        for pr in ele.Parameters:
            try:
                if strip_accents(pr.Definition.Name) == strip_accents(primary_param_name):
                    raw_param = pr
                    break
            except Exception:
                continue
        if raw_param is None:
            try:
                typ = ele_doc.GetElement(ele.GetTypeId())
                if typ:
                    for pr in typ.Parameters:
                        if strip_accents(pr.Definition.Name) == strip_accents(primary_param_name):
                            raw_param = pr
                            break
            except Exception:
                pass

        if raw_param is None:
            continue

        match = None
        for vi in list_values:
            if vi.value == compound_key:
                match = vi
                break

        if match:
            try:
                match.ele_id.Add(ele.Id)
            except Exception:
                match.ele_id.append(ele.Id)
            if raw_param.StorageType == _DB.StorageType.Double:
                match.values_double.append(raw_param.AsDouble())
        else:
            attempts = 0
            while attempts < 200:
                r = randint(30, 230)
                g = randint(30, 230)
                b = randint(30, 230)
                if (r, g, b) not in used_colors:
                    used_colors.add((r, g, b))
                    break
                attempts += 1
            vi = ValuesInfoPro(
                raw_param,
                compound_key,
                ele.Id,
                r, g, b,
                link_name=link_name
            )
            list_values.append(vi)

    none_vals = [x for x in list_values if x.value == 'None']
    non_none = [x for x in list_values if x.value != 'None']
    non_none = sorted(non_none, key=lambda x: (x.value or '').lower())
    list_values = non_none + none_vals

    return list_values


# ---------------------------------------------------------------------------
# Extended ValuesInfo with count and link support
# ---------------------------------------------------------------------------

try:
    from pyrevit.framework import List
    from pyrevit import DB as _DB

    class ValuesInfoPro(object):
        """
        Extended ValuesInfo with compound key, count, and link support.
        Compatible with original ValuesInfo interface.
        """

        def __init__(self, para, val, idt, num1, num2, num3, link_name=None):
            try:
                from pyrevit.framework import List as _List
                from pyrevit import DB as _DB2
                from pyrevit.framework import Drawing
                self.par = para
                self.value = val
                self.name = val
                self.ele_id = _List[_DB2.ElementId]()
                self.ele_id.Add(idt)
                self.n1 = num1
                self.n2 = num2
                self.n3 = num3
                self.colour = Drawing.Color.FromArgb(self.n1, self.n2, self.n3)
                self.values_double = []
                self.link_name = link_name or ''
                if para and para.StorageType == _DB2.StorageType.Double:
                    self.values_double.append(para.AsDouble())
            except Exception as ex:
                self.par = para
                self.value = val
                self.name = val
                self.n1 = num1
                self.n2 = num2
                self.n3 = num3
                self.values_double = []
                self.link_name = link_name or ''
                try:
                    from pyrevit.framework import List as _L
                    from pyrevit import DB as _D
                    self.ele_id = _L[_D.ElementId]()
                    self.ele_id.Add(idt)
                except Exception:
                    self.ele_id = [idt]
                try:
                    from pyrevit.framework import Drawing as _Drw
                    self.colour = _Drw.Color.FromArgb(num1, num2, num3)
                except Exception:
                    self.colour = None

except Exception:
    class ValuesInfoPro(object):
        """Fallback minimal implementation."""

        def __init__(self, para, val, idt, num1, num2, num3, link_name=None):
            self.par = para
            self.value = val
            self.name = val
            self.n1 = num1
            self.n2 = num2
            self.n3 = num3
            self.values_double = []
            self.link_name = link_name or ''
            self.ele_id = [idt]
            self.colour = None


# ---------------------------------------------------------------------------
# Heat map value list builder
# ---------------------------------------------------------------------------

def get_range_values_heatmap(
    category_info,
    primary_param_info,
    view,
    doc,
    num_bands=5,
    custom_ranges=None,
    link_elements=None,
    scope="view"
):
    """
    Build a value list for heat map mode.
    Only works with numeric parameters (Double / Integer).

    Returns:
        (list of ValuesInfoPro, list of HeatMapRange, list of parse_errors)
        or ([], [], ['error message'])
    """
    try:
        from pyrevit import DB as _DB
        from pyrevit import HOST_APP
        import System
    except Exception:
        return [], [], ['Could not import Revit API']

    primary_param_name = primary_param_info.par.Name
    bic = None
    try:
        for sample_bic in System.Enum.GetValues(_DB.BuiltInCategory):
            if category_info.int_id == int(sample_bic):
                bic = sample_bic
                break
    except Exception:
        pass

    if bic is None:
        return [], [], ['Category BuiltInCategory not found']

    host_elements = []
    if scope != "none":
        try:
            if scope == "selected":
                uidoc = HOST_APP.uidoc
                selected_ids = uidoc.Selection.GetElementIds()
                collector = []
                for eid in selected_ids:
                    try:
                        ele = doc.GetElement(eid)
                        if ele and ele.IsValidObject and ele.Category:
                            if int(ele.Category.Id.IntegerValue) == category_info.int_id:
                                if not isinstance(ele, _DB.ElementType):
                                    collector.append(ele)
                    except Exception:
                        continue
            elif scope == "whole":
                collector = (
                    _DB.FilteredElementCollector(doc)
                    .OfCategory(bic)
                    .WhereElementIsNotElementType()
                    .ToElements()
                )
            else:
                # Default: current view
                collector = (
                    _DB.FilteredElementCollector(doc, view.Id)
                    .OfCategory(bic)
                    .WhereElementIsNotElementType()
                    .ToElements()
                )
            host_elements = [(ele, None) for ele in collector]
        except Exception:
            host_elements = []

    all_element_pairs = list(host_elements)
    if link_elements:
        all_element_pairs.extend(link_elements)

    numeric_pairs = []
    parse_errors = []

    for (ele, link_name) in all_element_pairs:
        ele_doc = ele.Document if hasattr(ele, 'Document') else doc
        val_str = get_param_value_safe(ele, primary_param_name, ele_doc)
        f = try_parse_float(val_str)
        if f is not None:
            numeric_pairs.append((ele.Id, f))
        else:
            parse_errors.append(ele.Id)

    if not numeric_pairs:
        return [], [], parse_errors + ['No numeric values found for parameter']

    all_floats = [v for (_, v) in numeric_pairs]

    ranges = build_heat_map_ranges(all_floats, num_bands=num_bands, custom_ranges=custom_ranges)

    range_values = []
    for rng in ranges:
        try:
            from pyrevit.framework import List as _List
            vi_ele_id = _List[_DB.ElementId]()
        except Exception:
            vi_ele_id = []

        vi = ValuesInfoPro.__new__(ValuesInfoPro)
        vi.par = None
        vi.value = rng.label
        vi.name = rng.label
        vi.n1 = rng.r
        vi.n2 = rng.g
        vi.n3 = rng.b
        vi.values_double = []
        vi.link_name = ''
        vi.ele_id = vi_ele_id
        try:
            from pyrevit.framework import Drawing
            vi.colour = Drawing.Color.FromArgb(rng.r, rng.g, rng.b)
        except Exception:
            vi.colour = None
        range_values.append((vi, rng))

    for (ele_id, f_val) in numeric_pairs:
        rng = classify_heat_map(f_val, ranges)
        if rng is not None:
            for vi, vi_rng in range_values:
                if vi_rng is rng:
                    try:
                        vi.ele_id.Add(ele_id)
                    except Exception:
                        vi.ele_id.append(ele_id)
                    vi.values_double.append(f_val)
                    break

    return [vi for (vi, _) in range_values], ranges, parse_errors
