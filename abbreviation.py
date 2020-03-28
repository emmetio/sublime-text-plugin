import re
import sublime
import sublime_plugin
from . import syntax
from . import tracker
from . import utils
from . import emmet_sublime as emmet

re_valid_abbr_end = re.compile(r'[a-z0-9*$.#!@>^+\)\]\}]')
re_jsx_abbr_start = re.compile(r'^[a-zA-Z.#\[\(]$')
re_word_bound = re.compile(r'^[\s>;"\']?[a-zA-Z.#!@\[\(]$')
pairs = {
    '{': '}',
    '[': ']',
    '(': ')'
}

JSX_PREFIX = '<'
ABBR_REGION_ID = 'emmet-abbreviation'

def allow_tracking(view: sublime.View, pos: int) -> bool:
    "Check if abbreviation tracking is allowed in editor at given location"
    return is_enabled(view) and syntax.in_activation_scope(view, pos)


def is_enabled(view: sublime.View) -> bool:
    "Check if Emmet abbreviation tracking is enabled"
    return view.settings().get('emmet_abbreviation_tracking', False)


def main_view(fn):
    "Method decorator for running actions in code views only"

    def wrapper(self, view):
        if not view.settings().get('is_widget'):
            fn(self, view)

    return wrapper


class EmmetExpandAbbreviation(sublime_plugin.TextCommand):
    def run(self, edit):
        caret = utils.get_caret(self.view)
        trk = tracker.get_tracker(self.view)

        if trk and trk.region.contains(caret):
            if trk.abbreviation and 'error' not in trk.abbreviation:
                if 'context' not in trk.config:
                    # No context captured, might be due to performance optimization
                    # in large document
                    emmet.attach_context(self.view, caret, trk.config)

                snippet = emmet.expand(trk.abbreviation['abbr'], trk.config)
                utils.replace_with_snippet(self.view, edit, trk.region, snippet)

            tracker.stop_tracking(self.view)


class EmmetExtractAbbreviation(sublime_plugin.TextCommand):
    def run(self, edit):
        trk = suggest_abbreviation_tracker(self.view, utils.get_caret(self.view))
        if trk:
            trk.show_preview(self.view)


class EmmetEnterAbbreviation(sublime_plugin.TextCommand):
    def run(self, edit):
        trk = tracker.get_tracker(self.view)
        tracker.stop_tracking(self.view, edit)
        if trk and trk.forced:
            # Already have forced abbreviation: act as toggler
            return

        primary_sel = self.view.sel()[0]
        trk = tracker.start_tracking(self.view, primary_sel.begin(), primary_sel.end(), forced=True)
        print('create tracker')
        if not primary_sel.empty():
            trk.show_preview(self.view)
            sel = self.view.sel()
            sel.clear()
            sel.add(sublime.Region(primary_sel.end(), primary_sel.end()))


class EmmetClearAbbreviationMarker(sublime_plugin.TextCommand):
    def run(self, edit):
        tracker.stop_tracking(self.view, edit)


class AbbreviationMarkerListener(sublime_plugin.EventListener):
    def __init__(self):
        self.last_pos_tracker = {}
        self.pending_completions_request = False

    @main_view
    def on_close(self, view: sublime.View):
        tracker.stop_tracking(view)
        key = view.id()
        if key in self.last_pos_tracker:
            del self.last_pos_tracker[key]

    @main_view
    def on_activated(self, view: sublime.View):
        tracker.handle_selection_change(view)
        self.last_pos_tracker[view.id()] = utils.get_caret(view)

    @main_view
    def on_selection_modified(self, view: sublime.View):
        if not is_enabled(view):
            return

        trk = tracker.handle_selection_change(view)
        caret = utils.get_caret(view)

        # print('sel modified at %d' % caret)

        if trk and trk.abbreviation and trk.region.contains(caret):
            trk.show_preview(view)
        elif trk:
            trk.hide_preview(view)

        self.last_pos_tracker[view.id()] = caret

    @main_view
    def on_modified(self, view: sublime.View):
        key = view.id()
        pos = utils.get_caret(view)
        last_pos = self.last_pos_tracker.get(key)
        # print('track change %d → %d' % (last_pos, pos))

        trk = tracker.handle_change(view)
        if not trk and last_pos is not None and allow_tracking(view, last_pos) and last_pos == pos - 1:
            trk = start_abbreviation_tracking(view, pos)

        if trk and should_stop_tracking(trk, pos):
            # print('got tracker at %s, validate "%s"' % (trk.region, view.substr(trk.region)))
            tracker.stop_tracking(view)

        self.last_pos_tracker[key] = pos

    def on_query_context(self, view: sublime.View, key: str, *args):
        if key == 'emmet_abbreviation':
            # Check if caret is currently inside Emmet abbreviation
            trk = tracker.get_tracker(view)
            if trk:
                for s in view.sel():
                    if trk.region.contains(s):
                        return trk.forced or (trk.abbreviation and 'error' not in trk.abbreviation)

            return False

        if key == 'has_emmet_abbreviation_mark':
            return bool(tracker.get_tracker(view))

        if key == 'has_emmet_forced_abbreviation_mark':
            trk = tracker.get_tracker(view)
            return trk.forced if trk else False

        return None

    def on_query_completions(self, view: sublime.View, prefix: str, locations: list):
        pos = locations[0]
        if self.pending_completions_request:
            self.pending_completions_request = False

            trk = suggest_abbreviation_tracker(view, pos)
            if trk:
                abbr_str = view.substr(trk.region)
                snippet = emmet.expand(trk.abbreviation['abbr'], trk.config)
                return [('%s\tEmmet' % abbr_str, snippet)]

    def on_text_command(self, view: sublime.View, command_name: str, args: list):
        if command_name == 'auto_complete' and is_enabled(view):
            self.pending_completions_request = True
        elif command_name == 'commit_completion':
            print('commit completion %s' % repr(args))
            tracker.stop_tracking(view)

    def on_post_text_command(self, view: sublime.View, command_name: str, args: list):
        if command_name == 'auto_complete':
            self.pending_completions_request = False

    # def on_post_text_command(self, view: sublime.View, command_name: str, args: list):
    #     if command_name == 'undo':
    #         # In case of undo, editor may restore previously marked range.
    #         # If so, restore marker from it
    #         print('undo; has range? %s' % (bool(view.get_regions(ABBR_REGION_ID))))

def should_stop_tracking(trk: tracker.RegionTracker, pos: int) -> bool:
    if trk.forced:
        # Never reset forced abbreviation: it’s up to user how to handle it
        return False

    if re.search(r'[\n\r]', trk.abbreviation['abbr']):
        # Never allow new lines in auto-tracked abbreviation
        return True


    # Reset if user entered invalid character at the end of abbreviation
    return 'error' in trk.abbreviation and trk.region.end() == pos


def is_invalid_abbr(abbr: str):
    # Check if given abbreviation cannot be valid
    return bool(re.match(r'[\n\r]', abbr))


def start_abbreviation_tracking(view: sublime.View, pos: int) -> tracker.RegionTracker:
    "Check if we can start abbreviation tracking at given location in editor"
    # Start tracking only if user starts abbreviation typing: entered first
    # character at the word bound
    # NB: get last 2 characters: first should be a word bound (or empty),
    # second must be abbreviation start
    prefix_region = sublime.Region(max(0, pos - 2), pos)
    prefix = view.substr(prefix_region)
    start = -1
    end = pos

    # print('check prefix "%s"' % prefix)
    if syntax.from_pos(view, pos) == 'jsx':
        # In JSX, abbreviations for completions should be prefixed
        if len(prefix) == 2 and prefix[0] == JSX_PREFIX and re_jsx_abbr_start.match(prefix[1]):
            start = pos - 2
    elif re_word_bound.match(prefix):
        start = pos - 1

    if start >= 0:
        last_ch = prefix[-1]
        if last_ch in pairs:
            # Check if there’s paired character
            next_char_region = sublime.Region(pos, min(pos + 1, view.size()))
            if view.substr(next_char_region) == pairs[last_ch]:
                end += 1

        return tracker.start_tracking(view, start, end)

def suggest_abbreviation_tracker(view: sublime.View, pos: int) -> tracker.RegionTracker:
    "Tries to extract abbreviation from given position and returns tracker for it, if available"
    if not allow_tracking(view, pos):
        return None

    trk = tracker.get_tracker(view)
    if trk and not trk.region.contains(pos):
        tracker.stop_tracking(view)
        trk = None

    if not trk:
        # Try to extract abbreviation from current location
        config = emmet.get_options(view, pos, True)
        abbr, _ = emmet.extract_abbreviation(view, pos, config)
        if abbr:
            return tracker.start_tracking(view, abbr.start, abbr.end, config=config)


def plugin_unloaded():
    for wnd in sublime.windows():
        for view in wnd.views():
            tracker.stop_tracking(view)
