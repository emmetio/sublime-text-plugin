import re
import sublime
import sublime_plugin
from .emmet import extract, expand, get_options
from .emmet.marker import get_marker, dispose_marker

active_preview = False
active_preview_id = None

def plugin_unloaded():
    dispose_marker()

    for wnd in sublime.windows():
        for view in wnd.views():
            if view.id() == active_preview_id:
                hide_preview(view)

def is_abbreviation_context(view, pt):
    "Check if given location in view is allowed for abbreviation marking"
    return view.match_selector(pt, "text.html - (source - source text.html, meta)")


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


class ExpandAbbreviation(sublime_plugin.TextCommand):
    def run(self, edit, **kw):
        marker = get_marker(self.view)
        sel = self.view.sel()
        caret = sel[0]

        if marker.contains(caret):
            if marker.valid:
                region = marker.region
                snippet = expand(marker.abbreviation, marker.options)
                sel.clear()
                sel.add(sublime.Region(region.begin(), region.begin()))
                self.view.replace(edit, region, '')
                self.view.run_command('insert_snippet', {'contents': snippet})

            marker.reset()


class AbbreviationMarkerListener(sublime_plugin.EventListener):
    def on_modified(self, view: sublime.View):
        sel = list(view.sel())
        marker = get_marker(view)

        if len(sel) != 1 or not sel[0].empty():
            # Multiple selections are not supported yet
            return marker.reset()

        caret = sel[0].begin()

        if marker.contains(caret):
            # Modification made inside caret: validate current abbreviation
            return marker.validate()

        # Try to find abbreviation from current caret position, if available
        marker.reset()

        if is_abbreviation_context(view, caret):
            abbr_data = abbr_from_line(view, caret)
            if abbr_data:
                marker.update(*abbr_data)

    def on_selection_modified(self, view: sublime.View):
        sel = list(view.sel())
        marker = get_marker(view)

        if len(sel) == 1 and not marker.simple and marker.contains(sel[0]):
            # Caret is inside marked abbreviation, display preview
            show_preview(view, marker)
        else:
            hide_preview(view)

    def on_query_context(self, view: sublime.View, key: str, op: str, operand: str, match_all: bool):
        if key == 'emmet_abbreviation':
            # Check if caret is currently inside Emmet abbreviation
            marker = get_marker(view)
            for s in view.sel():
                if marker.contains(s):
                    return True

            return False

        return None
