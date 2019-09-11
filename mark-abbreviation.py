import re
import sublime
import sublime_plugin
from .emmet import extract, expand, get_options
from .emmet.marker import AbbreviationMarker, clear_marker_region, get_marker_region

active_preview = False
active_preview_id = None
markers = {}

def plugin_unloaded():
    for wnd in sublime.windows():
        for view in wnd.views():
            clear_marker_region(view)
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
    return view.match_selector(pt, "text.html - (entity, punctuation.definition.tag.end)")


def is_abbreviation_bound(view, pt):
    "Check if given point in view is a possible abbreviation start"
    line_range = view.line(pt)
    bound_chars = ' \t>'
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


def marker_from_line(view, pt):
    "Extracts abbreviation from given location and, if it's valid, returns marker for it"
    abbr_data = abbr_from_line(view, pt)
    if abbr_data:
        marker = AbbreviationMarker(view, abbr_data[0], abbr_data[1])
        if marker.valid:
            set_marker(view, marker)
            return marker

        # Invalid abbreviation in marker, dispose it
        marker.reset()


def show_preview(view, marker):
    globals()['active_preview'] = True
    globals()['active_preview_id'] = view.id()
    view.show_popup(marker.preview(), sublime.COOPERATE_WITH_AUTO_COMPLETE,
        marker.region.begin(), 400, 300)


def toggle_preview_for_pos(view, marker, pos):
    "Toggle Emmet abbreviation preview display for given marker and location"
    if not marker.simple and marker.contains(pos):
        show_preview(view, marker)
    else:
        hide_preview(view)


def hide_preview(view):
    if active_preview and active_preview_id == view.id():
        view.hide_popup()

    globals()['active_preview'] = False
    globals()['active_preview_id'] = None


def get_caret(view):
    return view.sel()[0].begin()


def validate_marker(view, marker):
    "Validates given marker right after modifications *inside* it"
    marker.validate()
    if not marker.region:
        # In case if user removed abbreviation, `marker` will end up
        # with empty state
        dispose_marker(view)


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
        self.last_pos = get_caret(view)
        marker = get_marker(view)

        if marker:
            # Caret is inside marked abbreviation, display preview
            toggle_preview_for_pos(view, marker, self.last_pos)
        else:
            hide_preview(view)

    @nonpanel
    def on_modified(self, view):
        last_pos = self.last_pos
        caret = get_caret(view)
        marker = get_marker(view)

        if marker:
            marker.validate()
            marker_region = get_marker_region(view)
            if not marker_region or marker_region.empty():
                # User removed marked abbreviation
                dispose_marker(view)
                return

            # Check if modification was made inside marked region
            prev_inside = marker_region.contains(last_pos)
            next_inside = marker_region.contains(caret)

            if prev_inside and next_inside:
                # Modifications made completely inside abbreviation
                marker.validate()
            elif prev_inside:
                # Modifications made right after marker
                # To properly track updates, we can't just add a [prev_caret, caret]
                # substring since user may type `[` which will automatically insert `]`
                # as a snippet and we won't be able to properly track it.
                # We should extract abbreviation instead.
                abbr_data = abbr_from_line(view, caret)
                if abbr_data:
                    marker.update(abbr_data[0], abbr_data[1])
                else:
                    # Unable to extract abbreviation or abbreviation is invalid
                    dispose_marker(view)
            elif next_inside:
                # Modifications made right before marker
                marker.update(last_pos, marker_region.end())
            else:
                # Modifications made outside marker
                dispose_marker(view)
                marker = None

        if not marker and caret > last_pos and is_abbreviation_context(view, caret) and is_abbreviation_bound(view, last_pos):
            # User started abbreviation typing
            marker_from_line(view, caret)


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
                    toggle_preview_for_pos(view, marker, caret)
                else:
                    marker.reset()
                    marker = None

        if marker:
            return [
                ['%s\tEmmet' % marker.abbreviation, marker.snippet()]
            ]

        return None

    def on_text_command(self, view, command_name, args):
        if command_name == 'commit_completion':
            dispose_marker(view)

    def on_post_text_command(self, view, command_name, args):
        if command_name == 'undo':
            # In case of undo, editor may restore previously marked range.
            # If so, restore marker from it
            r = get_marker_region(view)
            if r:
                clear_marker_region(view)
                marker = AbbreviationMarker(view, r.begin(), r.end())
                if marker.valid:
                    set_marker(view, marker)
                    toggle_preview_for_pos(view, marker, get_caret(view))
                else:
                    marker.reset()


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
