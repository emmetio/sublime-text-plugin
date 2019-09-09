import re
import sublime
import sublime_plugin
from .emmet import extract, expand, get_options
from .emmet.marker import AbbreviationMarker, abbr_region_id

active_preview = False
active_preview_id = None
markers = {}

def plugin_unloaded():
    for wnd in sublime.windows():
        for view in wnd.views():
            view.erase_regions(abbr_region_id)
            if view.id() == active_preview_id:
                hide_preview(view)


def get_marker(view):
    vid = view.id()
    return vid in markers and markers[vid] or None


def set_marker(view, marker):
    markers[view.id()] = marker


def dispose_marker(view):
    vid = view.id()
    if vid in markers:
        marker = markers[vid]
        marker.reset()
        del markers[vid]


def is_abbreviation_context(view, pt):
    "Check if given location in view is allowed for abbreviation marking"
    return view.match_selector(pt, "text.html - (source - source text.html, meta)")


def is_abbreviation_bound(view, pt):
    "Check if given point in view is a possible abbreviation start"
    line_range = view.line(pt)
    bound_chars = ' \t'
    left = line_range.begin() == pt or view.substr(pt - 1) in bound_chars
    right = line_range.end() != pt and view.substr(pt) not in bound_chars
    return left and right


def abbr_from_line(view, pt):
    "Extracts abbreviation from line that matches given point in view"
    line_region = view.line(pt)
    line_start = line_region.begin()
    line = view.substr(line_region)
    opt = get_options(view, pt)
    abbr_data = extract(line, pt - line_start, opt)

    if abbr_data:
        start = line_start + abbr_data['start']
        end = line_start + abbr_data['end']
        return start, end, opt


def show_preview(view, marker):
    globals()['active_preview'] = True
    globals()['active_preview_id'] = view.id()
    view.show_popup(marker.preview(), sublime.COOPERATE_WITH_AUTO_COMPLETE,
        marker.region.begin(), 400, 300)


def hide_preview(view):
    if active_preview and active_preview_id == view.id():
        view.hide_popup()

    globals()['active_preview'] = False
    globals()['active_preview_id'] = None


def get_caret(view):
    return view.sel()[0].begin()


def nonpanel(fn):
    def wrapper(self, view):
        if not view.settings().get('is_widget'):
            fn(self, view)
    return wrapper

class AbbreviationMarkerListener(sublime_plugin.EventListener):
    def __init__(self):
        self.last_pos = -1

    def on_close(self, view):
        dispose_marker(view)

    @nonpanel
    def on_activated(self, view):
        self.last_pos = get_caret(view)

    @nonpanel
    def on_selection_modified(self, view):
        caret = get_caret(view)
        self.last_pos = caret
        marker = get_marker(view)

        if marker and not marker.simple and marker.contains(caret):
            # Caret is inside marked abbreviation, display preview
            show_preview(view, marker)
        else:
            hide_preview(view)

    @nonpanel
    def on_modified(self, view):
        caret = get_caret(view)
        marker = get_marker(view)

        if marker:
            if marker.contains(caret):
                # Modification made inside caret: validate current abbreviation
                return marker.validate()

            # Check if modification was made right after or before abbreviation marker
            line_range = view.line(caret)
            if line_range.contains(marker.region) and marker.contains(self.last_pos):
                start = min(marker.region.begin(), caret)
                end = max(marker.region.end(), caret)

                # In case if we receive space chacarter as input, check if it’s
                # not at abbreviation edge
                abbr = view.substr(sublime.Region(start, end))
                if abbr == abbr.strip():
                    marker.update(start, end)
                    return

        dispose_marker(view)

        if caret > self.last_pos and is_abbreviation_context(view, caret) and is_abbreviation_bound(view, self.last_pos):
            marker = AbbreviationMarker(view, self.last_pos, caret)
            if marker.valid:
                set_marker(view, marker)
            else:
                # Initially invalid abbreviation, abort
                marker.reset()

    def on_query_context(self, view: sublime.View, key: str, op: str, operand: str, match_all: bool):
        if key == 'emmet_abbreviation':
            # Check if caret is currently inside Emmet abbreviation
            marker = get_marker(view)
            if marker:
                for s in view.sel():
                    if marker.contains(s):
                        return True

            return False

        if key == 'has_emmet_abbreviation_mark':
            return get_marker(view) and True or False

        return None

    def on_query_completions(self, view, prefix, locations):
        marker = get_marker(view)
        caret = locations[0]
        if marker and not marker.contains(caret):
            dispose_marker(view)
            marker = None

        if not marker and is_abbreviation_context(view, caret):
            # Try to extract abbreviation from given location
            abbr_data = abbr_from_line(view, caret)
            if abbr_data:
                marker = AbbreviationMarker(view, abbr_data[0], abbr_data[1])
                if marker.valid:
                    set_marker(view, marker)
                else:
                    marker.reset()
                    marker = None

        if marker:
            return [
                ['%s\tExpand Emmet abbreviation' % marker.abbreviation, marker.snippet()]
            ]

        return None

    def on_text_command(self, view, command_name, args):
        if command_name == 'commit_completion':
            dispose_marker(view)


class ExpandAbbreviation(sublime_plugin.TextCommand):
    def run(self, edit, **kw):
        marker = get_marker(self.view)
        sel = self.view.sel()
        caret = get_caret(self.view)

        if marker.contains(caret):
            if marker.valid:
                region = marker.region
                snippet = expand(marker.abbreviation, marker.options)
                sel.clear()
                sel.add(sublime.Region(region.begin(), region.begin()))
                self.view.replace(edit, region, '')
                self.view.run_command('insert_snippet', {'contents': snippet})

            dispose_marker(self.view)

class ClearAbbreviationMarker(sublime_plugin.TextCommand):
    def run(self, edit, **kw):
        dispose_marker(self.view)
