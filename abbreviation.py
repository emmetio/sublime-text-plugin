import sublime
import sublime_plugin
from . import emmet_sublime as emmet
from . import preview
from . import marker
from . import syntax
from . import utils


def in_activation_context(view: sublime.View, caret: int, prev_pos: int, completion_contex=False) -> bool:
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
        if s_name in ('html', 'xml', 'xsl'):
            # For HTML-like syntaxes, we should detect if we are at abbreviation bound
            return in_scope and is_abbreviation_bound(view, prev_pos)
        if s_name == 'jsx':
            # In JSX, we rely on prefixed match: we should activate abbreviation
            # only of its prefixed with `<`
            return view.substr(prev_pos - 1) == '<' if prev_pos > 0 else completion_contex

        # In all other cases just check if we are in abbreviation scope
        return in_scope
    return False


def is_stylesheet_color(view, begin, end) -> bool:
    "Check if given range is inside CSS color value"
    return view.match_selector(end, 'meta.property-value | punctuation.terminator.rule') and \
        view.substr(sublime.Region(begin, end)) == '#'


def is_abbreviation_bound(view: sublime.View, pt: int) -> bool:
    "Check if given point in view is a possible abbreviation start"
    line_range = view.line(pt)
    bound_chars = ' \t'
    left = line_range.begin() == pt or view.substr(pt - 1) in bound_chars or\
        view.match_selector(pt - 1, 'punctuation.definition.tag.end.html')
    right = line_range.end() != pt and view.substr(pt) not in bound_chars
    return left and right


def preview_as_phantom(mark: marker.AbbreviationMarker) -> bool:
    "Should display preview of given marker as phantom?"
    return mark.type == 'stylesheet'


def activate_marker(view: sublime.View, pt: int):
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


def update_marker(view: sublime.View, mrk: marker.AbbreviationMarker, loc: int):
    """
    Updates marker with newly extracted abbreviation from given location.
    If abbreviation is not fount or invalid, disposes it
    """
    abbr_data = emmet.extract_abbreviation(view, loc, mrk.options)
    if abbr_data:
        mrk.update(abbr_data[0])
        return mrk

    # Unable to extract abbreviation or abbreviation is invalid
    marker.dispose(view)
    return None


def nonpanel(fn):
    "Method dectorator for running actions in code views only"
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

    def on_activated(self, view: sublime.View):
        self.last_pos = utils.get_caret(view)

    @nonpanel
    def on_selection_modified_async(self, view: sublime.View):
        self.last_pos = utils.get_caret(view)
        mrk = marker.get(view)

        if mrk:
            # Caret is inside marked abbreviation, display preview
            preview.toggle(view, mrk, self.last_pos, preview_as_phantom(mrk))
        else:
            preview.hide(view)

    @nonpanel
    def on_modified_async(self, view: sublime.View):
        last_pos = self.last_pos
        caret = utils.get_caret(view)
        mrk = marker.get(view)
        self.last_pos = caret

        if mrk:
            mrk.validate()

            # Check if modification was made inside marked region or at marker edges
            same_line = view.line(caret).contains(mrk.region)
            modified_before = same_line and caret <= mrk.region.begin()
            modified_after = same_line and caret >= mrk.region.end()

            if mrk.contains(caret):
                # Modifications made completely inside abbreviation, should be already validated
                pass
            elif modified_after:
                # Modifications made right after marker
                # To properly track updates, we can't just add a [prev_caret, caret]
                # substring since user may type `[` which will automatically insert `]`
                # as a snippet and we won't be able to properly track it.
                # We should extract abbreviation instead.
                mrk = update_marker(view, mrk, caret)
            elif modified_before:
                # Modifications made right before marker, ensure it results
                # # in valid abbreviation
                mrk = update_marker(view, mrk, mrk.region.end())
            else:
                # Modifications made outside marker
                marker.dispose(view)
                mrk = None

        if not mrk and caret >= last_pos and view.settings().get('emmet_auto_mark') and \
            in_activation_context(view, caret, last_pos):
            mrk = marker.extract(view, caret)


    def on_query_context(self, view: sublime.View, key: str, *args):
        if key == 'emmet_abbreviation':
            # Check if caret is currently inside Emmet abbreviation
            mrk = marker.get(view)
            if mrk:
                for s in view.sel():
                    if mrk.contains(s):
                        return True

            return False

        if key == 'has_emmet_abbreviation_mark':
            return bool(marker.get(view))

        return None

    def on_query_completions(self, view: sublime.View, prefix: str, locations: list):
        # Check if completion list was populated by manually invoking autocomplete popup
        if self.last_command == 'auto_complete':
            # Produce auto-complete option only when completion popup invoked manually
            activate_marker(view, locations[0])

    def on_text_command(self, view: sublime.View, command_name: str, args: list):
        self.last_command = command_name
        if command_name == 'commit_completion':
            marker.dispose(view)

    def on_post_text_command(self, view: sublime.View, command_name: str, args: list):
        if command_name == 'undo':
            # In case of undo, editor may restore previously marked range.
            # If so, restore marker from it
            r = marker.get_region(view)
            if r:
                marker.clear_region(view)
                mrk = marker.extract(view, r)
                if mrk:
                    preview.toggle(view, mrk, utils.get_caret(view), preview_as_phantom(mrk))


class EmmetExpandAbbreviation(sublime_plugin.TextCommand):
    def run(self, edit):
        mrk = marker.get(self.view)
        caret = utils.get_caret(self.view)

        if mrk.contains(caret):
            if mrk.valid:
                snippet = emmet.expand(mrk.abbreviation, mrk.options)
                utils.replace_with_snippet(self.view, edit, mrk.region, snippet)

            marker.dispose(self.view)
