import sublime
import sublime_plugin
from . import emmet_sublime as emmet
from . import utils
from . import marker

class EmmetEnterAbbreviation(sublime_plugin.TextCommand):
    def run(self, edit: sublime.Edit):
        caret = utils.get_caret(self.view)
        mrk = marker.get(self.view)
        has_caret = mrk and mrk.contains(caret)

        # Clear any existing marker
        if mrk:
            marker.dispose(mrk)

        # If caret was inside marker, just clear it (use as toggle),
        # otherwise create new marker at given location
        if not has_caret:
            marker.create(self.view, caret, True)


class EmmetExpandAbbreviation(sublime_plugin.TextCommand):
    def run(self, edit):
        mrk = marker.get(self.view)
        caret = utils.get_caret(self.view)

        if mrk and mrk.contains(caret):
            if mrk.valid:
                if 'context' not in mrk.options:
                    # No context captured, might be due to performance optimization
                    # in large document
                    emmet.attach_context(self.view, caret, mrk.options)

                snippet = emmet.expand(mrk.value, mrk.options)
                mrk.unmark()
                utils.replace_with_snippet(self.view, edit, mrk.region, snippet)

            marker.dispose(mrk)


def main_view(fn):
    "Method decorator for running actions in code views only"

    def wrapper(self, view):
        if not view.settings().get('is_widget'):
            fn(self, view)

    return wrapper


def inserted_text_size(view: sublime.View) -> int:
    "Returns length of inserted text from last command"
    command, args, _ = view.command_history(0, True)

    if command == 'insert_snippet':
        return len(sublime.expand_variables(args.get('contents', ''), {}))

    return None


def handle_forced_marker_update(view: sublime.View, mrk: marker.AbbreviationMarker, caret: int, last_pos: int) -> bool:
    """
    Handles text update of marker content in forced mode
    """
    # In forced abbreviation mode, try to put everything user types
    # into marker, even if it’s invalid
    region, _ = marker.marked_region(view)
    # print('caret: %d, last caret: %d, region: %s, actual region: %s' % (caret, last_pos, mrk.region, region))
    same_line = view.line(caret).contains(region)

    # TODO handle Tab key at the beginning of abbreviation
    # TODO handle/prevent new lines in abbreviation

    if not same_line:
        # print('not same line, abort: %s' % view.line(caret))
        return

    if caret > last_pos:
        # Detect inserted text region
        # To properly track updates, we can't just add a [prev_caret, caret]
        # substring since user may type `[` which will automatically insert `]`
        # as a snippet. Try to detect inserted text from last command
        text_len = inserted_text_size(view)
        if text_len is None:
            text_len = caret - last_pos

        inserted_region = sublime.Region(last_pos, last_pos + text_len)
        if mrk.contains(inserted_region.a) or mrk.contains(inserted_region.b):
            # print('changed region: %s' % inserted_region)
            mrk.region = region.cover(inserted_region)
        # else:
        #     print('text %s inserted outside %s' % (inserted_region, mrk.region))
    elif mrk.contains(caret):
        # Modifications made completely inside abbreviation, update region
        # print('deleted inside')
        mrk.region = region


class AbbreviationMarkerListener(sublime_plugin.EventListener):
    def __init__(self):
        self.last_pos = -1
        self.last_command = None

    def on_close(self, view):
        marker.dispose_in_view(view)

    def on_activated(self, view: sublime.View):
        self.last_pos = utils.get_caret(view)

    @main_view
    def on_selection_modified(self, view: sublime.View):
        if not view.settings().get('emmet_abbreviation_preview', False):
            return

        self.last_pos = utils.get_caret(view)
        mrk = marker.get(view)

        if mrk:
            # Caret is inside marked abbreviation, display preview
            mrk.toggle_preview(self.last_pos)

    @main_view
    def on_selection_modified_async(self, view: sublime.View):
        mrk = marker.get(view)
        if mrk and 'context' not in mrk.options:
            # Context is not attached due to large document (to reduce typing lag)
            emmet.attach_context(view, mrk.region.begin(), mrk.options)
            mrk.toggle_preview(utils.get_caret(view))

    @main_view
    def on_modified(self, view: sublime.View):
        caret = utils.get_caret(view)
        mrk = marker.get(view)
        last_pos = self.last_pos
        self.last_pos = caret

        if mrk and mrk.forced:
            handle_forced_marker_update(view, mrk, caret, last_pos)

    def on_query_context(self, view: sublime.View, key: str, *args):
        if key == 'emmet_abbreviation':
            # Check if caret is currently inside Emmet abbreviation
            mrk = marker.get(view)
            if mrk:
                for s in view.sel():
                    if mrk.contains(s):
                        return mrk.forced or mrk.valid

            return False

        if key == 'has_emmet_abbreviation_mark':
            return bool(marker.get(view))

        return None

    def on_text_command(self, view: sublime.View, command_name: str, args: list):
        self.last_command = command_name
        if command_name == 'commit_completion':
            marker.dispose_in_view(view)

    def on_post_text_command(self, view: sublime.View, command_name: str, args: list):
        if command_name == 'undo':
            # In case of undo, editor may restore previously marked range.
            # If so, restore marker from it
            mrk = marker.restore(view)
            if mrk:
                mrk.toggle_preview(utils.get_caret(view))


class EmmetClearAbbreviationMarker(sublime_plugin.TextCommand):
    def run(self, edit):
        mrk = marker.get(self.view)
        if mrk:
            # If marker is forced, we should remove abbreviation as well
            region = mrk.region if mrk.forced else None
            marker.dispose(mrk)
            if region:
                self.view.erase(edit, region)
