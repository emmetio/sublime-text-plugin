import re
import sublime
import sublime_plugin
from . import emmet
from . import preview
from . import marker
from . import syntax
from . import utils


def in_activation_context(view, caret, prev_pos, completion_contex=False):
    """
    Check that given caret position is inside abbreviation activation context,
    e.g. caret is in location where user expects abbreviation.
    """
    syntax_info = syntax.info(view, caret)

    if syntax_info:
        s_name = syntax_info['syntax']
        in_scope = syntax.in_activation_scope(view, caret)
        if syntax_info['type'] == 'stylesheet':
            # In stylesheet scope, we should either be inside selector block
            # (outside of CSS property) or inside property value but typing CSS color
            return in_scope or is_stylesheet_color(view, prev_pos, caret)
        elif s_name in ('html', 'xml', 'xsl'):
            # For HTML-like syntaxes, we should detect if we are at abbreviation bound
            return in_scope and is_abbreviation_bound(view, prev_pos)
        elif s_name == 'jsx':
            # In JSX, we rely on prefixed match: we should activate abbreviation
            # only of its prefixed with `<`
            return prev_pos > 0 and view.substr(prev_pos - 1) == '<' or completion_contex

        # In all other cases just check if we are in abbreviation scope
        return in_scope


def is_stylesheet_color(view, begin, end):
    return view.match_selector(end, 'meta.property-value | punctuation.terminator.rule') and\
        view.substr(sublime.Region(begin, end)) == '#'


def is_abbreviation_bound(view, pt):
    "Check if given point in view is a possible abbreviation start"
    line_range = view.line(pt)
    bound_chars = ' \t'
    left = line_range.begin() == pt or view.substr(pt - 1) in bound_chars or\
        view.match_selector(pt - 1, 'punctuation.definition.tag.end.html')
    right = line_range.end() != pt and view.substr(pt) not in bound_chars
    return left and right


def preview_as_phantom(marker):
    return marker.type == 'stylesheet'


def activate_marker(view, pt):
    "Explicitly activates abbreviation marker at given location"
    mrk = marker.get(view)

    if mrk and not mrk.contains(pt):
        marker.dispose(view)
        mrk = None

    if not mrk and syntax.in_activation_scope(view, pt):
        # Try to extract abbreviation from given location
        mrk = marker.extract(view, pt)

    if mrk and mrk.valid:
        preview.toggle(view, mrk, pt, preview_as_phantom(mrk))


def update_marker(view, mrk, loc):
    abbr_data = emmet.extract_abbreviation(view, loc)
    if abbr_data:
        mrk.update(abbr_data[0])
    else:
        # Unable to extract abbreviation or abbreviation is invalid
        marker.dispose(view)

def nonpanel(fn):
    def wrapper(self, view):
        if not view.settings().get('is_widget'):
            fn(self, view)
    return wrapper


class AbbreviationMarkerListener(sublime_plugin.EventListener):
    def __init__(self):
        self.last_pos = -1
        self.last_command = None

    def on_close(self, view):
        marker.dispose(view)

    def on_activated(self, view):
        self.last_pos = utils.get_caret(view)

    @nonpanel
    def on_selection_modified(self, view):
        self.last_pos = utils.get_caret(view)
        mrk = marker.get(view)

        if mrk:
            # Caret is inside marked abbreviation, display preview
            preview.toggle(view, mrk, self.last_pos, preview_as_phantom(mrk))
        else:
            preview.hide(view)

    @nonpanel
    def on_modified(self, view):
        last_pos = self.last_pos
        caret = utils.get_caret(view)
        mrk = marker.get(view)

        if mrk:
            mrk.validate()
            if not mrk.valid:
                # User removed marked abbreviation
                marker.dispose(view)
                return

            # Check if modification was made inside marked region
            prev_inside = mrk.contains(last_pos)
            next_inside = mrk.contains(caret)

            if prev_inside and next_inside:
                # Modifications made completely inside abbreviation, should be already validated
                pass
            elif prev_inside:
                # Modifications made right after marker
                # To properly track updates, we can't just add a [prev_caret, caret]
                # substring since user may type `[` which will automatically insert `]`
                # as a snippet and we won't be able to properly track it.
                # We should extract abbreviation instead.
                update_marker(view, mrk, caret)
            elif next_inside and caret > last_pos:
                # Modifications made right before marker, ensure it results
                # # in valid abbreviation
                update_marker(view, mrk, (last_pos, mrk.region.end()))
            elif not next_inside:
                # Modifications made outside marker
                marker.dispose(view)
                mrk = None

        if not mrk and caret > last_pos and view.settings().get('emmet_auto_mark') and\
            in_activation_context(view, caret, last_pos):
            mrk = marker.extract(view, caret)


    def on_query_context(self, view: sublime.View, key: str, op: str, operand: str, match_all: bool):
        if key == 'emmet_abbreviation':
            # Check if caret is currently inside Emmet abbreviation
            mrk = marker.get(view)
            if mrk:
                for s in view.sel():
                    if mrk.contains(s):
                        return True

            return False

        if key == 'has_emmet_abbreviation_mark':
            return marker.get(view) and True or False

        return None

    def on_query_completions(self, view, prefix, locations):
        # Check if completion list was populated by manually invoking autocomplete popup
        if self.last_command == 'auto_complete':
            # Produce auto-complete option only when completion popup invoked manually
            activate_marker(view, locations[0])

    def on_text_command(self, view, command_name, args):
        self.last_command = command_name
        if command_name == 'commit_completion':
            marker.dispose(view)

    def on_post_text_command(self, view, command_name, args):
        if command_name == 'undo':
            # In case of undo, editor may restore previously marked range.
            # If so, restore marker from it
            r = marker.get_region(view)
            if r:
                marker.clear_region(view)
                mrk = marker.extract(view, r)
                if mrk:
                    preview.toggle(view, mrk, utils.get_caret(view), preview_as_phantom(mrk))


class ExpandAbbreviation(sublime_plugin.TextCommand):
    def run(self, edit, **kw):
        mrk = marker.get(self.view)
        caret = utils.get_caret(self.view)

        if mrk.contains(caret):
            if mrk.valid:
                snippet = emmet.expand(mrk.abbreviation, mrk.options)
                utils.replace_with_snippet(self.view, edit, mrk.region, snippet)

            marker.dispose(self.view)
