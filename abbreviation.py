import sublime
import sublime_plugin
from . import emmet_sublime as emmet
from . import utils
from . import marker2 as marker

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
            marker.create(self.view, caret)


class EmmetExpandAbbreviation(sublime_plugin.TextCommand):
    def run(self, edit):
        mrk = marker.get(self.view)
        caret = utils.get_caret(self.view)

        # if not mrk:
        #     # No marker, try to extract abbreviation for current context
        #     mrk = marker.extract(self.view, caret)

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


def nonpanel(fn):
    "Method decorator for running actions in code views only"

    def wrapper(self, view):
        if not view.settings().get('is_widget'):
            fn(self, view)

    return wrapper

class AbbreviationMarkerListener(sublime_plugin.EventListener):
    def __init__(self):
        self.last_pos = -1
        self.last_command = None

    def on_close(self, view):
        marker.dispose_in_view(view)

    def on_activated(self, view: sublime.View):
        self.last_pos = utils.get_caret(view)

    @nonpanel
    def on_selection_modified(self, view: sublime.View):
        if not view.settings().get('emmet_abbreviation_preview', False):
            return

        self.last_pos = utils.get_caret(view)
        mrk = marker.get(view)

        if mrk:
            # Caret is inside marked abbreviation, display preview
            mrk.toggle_preview(self.last_pos)

    @nonpanel
    def on_selection_modified_async(self, view: sublime.View):
        mrk = marker.get(view)
        if mrk and 'context' not in mrk.options:
            # Context is not attached due to large document (to reduce typing lag)
            emmet.attach_context(view, mrk.region.begin(), mrk.options)
            mrk.toggle_preview(utils.get_caret(view))

    @nonpanel
    def on_modified(self, view: sublime.View):
        caret = utils.get_caret(view)
        mrk = marker.get(view)
        last_pos = self.last_pos
        self.last_pos = caret

        if mrk and mrk.forced:
            # User in forced abbreviation mode: try to put everything user types
            # into marker, even if it’s invalid
            print('caret: %d, last caret: %d, region: %s' % (caret, last_pos, mrk.region))
            same_line = view.line(caret).contains(mrk.region)
            if same_line and (mrk.region.contains(caret) or mrk.region.contains(last_pos)):
                changed_region = sublime.Region(min(caret, last_pos), max(caret, last_pos))
                print('changed region: %s' % changed_region)
                mrk.region = mrk.region.cover(changed_region)
                # mrk.validate(mrk.region.cover(changed_region))

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

    def on_text_command(self, view: sublime.View, command_name: str, args: list):
        self.last_command = command_name
        if command_name == 'commit_completion':
            marker.dispose_in_view(view)

