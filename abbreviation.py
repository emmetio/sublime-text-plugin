import re
import html
import sublime
import sublime_plugin
from . import syntax
from . import tracker
from . import utils
from . import emmet_sublime as emmet
from .emmet import ScannerException
from .emmet.token_scanner import TokenScannerException
from .emmet.abbreviation import parse as markup_parse, Abbreviation as MarkupAbbreviation
from .emmet.css_abbreviation import parse as stylesheet_parse

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

            stop_tracking(self.view)


class EmmetExtractAbbreviation(sublime_plugin.TextCommand):
    def run(self, edit):
        trk = suggest_abbreviation_tracker(self.view, utils.get_caret(self.view))
        if trk:
            draw_marker(self.view, trk)
            show_preview(self.view, trk)


class EmmetEnterAbbreviation(sublime_plugin.TextCommand):
    def run(self, edit):
        trk = tracker.get_tracker(self.view)
        if trk:
            stop_tracking(self.view)
            if trk.forced:
                # Already have forced abbreviation: act as toggler, remove it
                self.view.erase(edit, trk.region)
                return

        primary_sel = self.view.sel()[0]
        trk = tracker.start_tracking(self.view, primary_sel.begin(), primary_sel.end(), True)
        trk.forced_indicator = sublime.PhantomSet(self.view, ABBR_REGION_ID)
        print('create tracker')
        draw_marker(self.view, trk)
        if not primary_sel.empty():
            trk.abbreviation = parse_abbreviation(self.view, trk)
            show_preview(self.view, trk)
            sel = self.view.sel()
            sel.clear()
            sel.add(sublime.Region(primary_sel.end(), primary_sel.end()))


class EmmetClearAbbreviationMarker(sublime_plugin.TextCommand):
    def run(self, edit):
        trk = tracker.get_tracker(self.view)
        if trk:
            # If tracker is forced, we should remove abbreviation as well
            region = trk.region if trk.forced else None
            stop_tracking(self.view)
            if region:
                self.view.erase(edit, region)


class AbbreviationMarkerListener(sublime_plugin.EventListener):
    def __init__(self):
        self.last_pos_tracker = {}
        self.pending_completions_request = False

    def on_close(self, view: sublime.View):
        stop_tracking(view)
        key = view.id()
        if key in self.last_pos_tracker:
            del self.last_pos_tracker[key]

    def on_activated(self, view: sublime.View):
        tracker.handle_selection_change(view)
        self.last_pos_tracker[view.id()] = utils.get_caret(view)

    @main_view
    def on_selection_modified(self, view: sublime.View):
        if not is_enabled(view):
            return

        tracker.handle_selection_change(view)

        key = view.id()
        trk = tracker.get_tracker(view)
        caret = utils.get_caret(view)

        # print('sel modified at %d' % caret)

        if trk and trk.abbreviation and trk.region.contains(caret):
            show_preview(view, trk)
        else:
            hide_preview(view)

        self.last_pos_tracker[key] = caret

    @main_view
    def on_modified(self, view: sublime.View):
        key = view.id()
        pos = utils.get_caret(view)
        last_pos = self.last_pos_tracker.get(key)
        # print('track change %d → %d' % (last_pos, pos))

        trk = tracker.handle_change(view)
        if not trk and last_pos is not None and allow_tracking(view, last_pos) and last_pos == pos - 1:
            trk = start_abbreviation_tracking(view, pos)

        if trk:
            # print('got tracker at %s, validate "%s"' % (trk.region, view.substr(trk.region)))
            trk.abbreviation = parse_abbreviation(view, trk)
            if should_stop_tracking(trk, pos):
                stop_tracking(view)
                trk = None

        clear_marker(view)
        if trk:
            draw_marker(view, trk)
            # show_preview(view, trk)

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
                draw_marker(view, trk)
                abbr_str = view.substr(trk.region)
                snippet = emmet.expand(trk.abbreviation['abbr'], trk.config)
                return [('%s\tEmmet' % abbr_str, snippet)]

    def on_text_command(self, view: sublime.View, command_name: str, args: list):
        if command_name == 'auto_complete' and is_enabled(view):
            self.pending_completions_request = True
        elif command_name == 'commit_completion':
            print('commit completion %s' % repr(args))
            stop_tracking(view)

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

        trk = tracker.start_tracking(view, start, end)
        trk.config = emmet.get_options(view, start, True)
        return trk

def suggest_abbreviation_tracker(view: sublime.View, pos: int) -> tracker.RegionTracker:
    "Tries to extract abbreviation from given position and returns tracker for it, if available"
    if not allow_tracking(view, pos):
        return None

    trk = tracker.get_tracker(view)
    if trk and not trk.region.contains(pos):
        stop_tracking(view)

    if not trk:
        # Try to extract abbreviation from current location
        config = emmet.get_options(view, pos, True)
        abbr, _ = emmet.extract_abbreviation(view, pos, config)
        if abbr:
            trk = tracker.start_tracking(view, abbr.start, abbr.end)
            trk.config = config
            trk.abbreviation = parse_abbreviation(view, trk)
            return trk


def stop_tracking(view: sublime.View):
    "Stops abbreviation tracking in given view"
    clear_marker(view)
    tracker.stop_tracking(view)


def clear_marker(view: sublime.View):
    "Removes all tracker markers from given view"
    view.erase_regions(ABBR_REGION_ID)
    view.erase_phantoms(ABBR_REGION_ID)
    hide_preview(view)


def draw_marker(view: sublime.View, trk: tracker.RegionTracker):
    "Draws marker for given tracker in view"
    scope = 'region.greenish'
    mark_opt = sublime.DRAW_SOLID_UNDERLINE | sublime.DRAW_NO_FILL | sublime.DRAW_NO_OUTLINE
    view.add_regions(ABBR_REGION_ID, [trk.region], scope, '', mark_opt)
    if trk.forced:
        print('draw forced indicator')
        phantoms = [sublime.Phantom(trk.region, forced_indicator('⋮>'), sublime.LAYOUT_INLINE)]
        trk.forced_indicator.update(phantoms)


def parse_abbreviation(view: sublime.View, trk: tracker.RegionTracker):
    "Parses abbreviation from given tracker and attaches result to it"
    # TODO consider prefix in JSX
    abbr = view.substr(trk.region)

    if not trk.config:
        trk.config = emmet.get_options(view, trk.region.a, True)

    try:
        # print('parse abbreviation "%s"' % abbr)
        if trk.config['type'] == 'stylesheet':
            parsed_abbr = stylesheet_parse(abbr, trk.config)
            simple = True
        else:
            parsed_abbr = markup_parse(abbr, trk.config)
            simple = is_simple_markup_abbreviation(parsed_abbr)

        preview_config = trk.config.copy()
        preview_config['preview'] = True
        return {
            'abbr': abbr,
            'simple': simple,
            'preview': emmet.expand(parsed_abbr, preview_config)
        }

    except (ScannerException, TokenScannerException) as err:
        return {
            'abbr': abbr,
            'error': {
                'message': err.message,
                'pos': err.pos,
                'snippet': '%s^' % ('-' * err.pos, ) if err.pos is not None else ''
            }
        }


def is_simple_markup_abbreviation(abbr: MarkupAbbreviation) -> bool:
    """
    Check if given parsed markup abbreviation is simple. A simple abbreviation
    may not be displayed to user as preview to reduce distraction
    """
    return len(abbr.children) == 1 and not abbr.children[0].children


def show_preview(view: sublime.View, trk: tracker.RegionTracker, as_phantom=None):
    "Displays expanded preview of abbreviation in given tracker"
    content = None

    if 'error' in trk.abbreviation:
        # Display error snippet
        content = '<div class="error">%s</div>' % format_snippet(trk.abbreviation['error']['snippet'])
    elif trk.forced or not trk.abbreviation['simple']:
        content = format_snippet(trk.abbreviation['preview'])

    if not content:
        hide_preview(view)
        return

    if as_phantom is None:
        # By default, display preview for CSS abbreviation as phantom to not
        # interfere with default autocomplete popup
        as_phantom = trk.config['type'] == 'stylesheet'

    if as_phantom:
        pass
        # TODO support phantoms
        # view.hide_popup()

        # if not self._preview:
        #     self._preview = sublime.PhantomSet(self.view, abbr_preview_id)

        # r = sublime.Region(self.region.end(), self.region.end())
        # phantoms = [sublime.Phantom(r, self.preview_phantom_html(content), sublime.LAYOUT_INLINE)]
        # self._preview.update(phantoms)
    else:
        view.show_popup(
            preview_popup_html(content),
            flags=sublime.COOPERATE_WITH_AUTO_COMPLETE,
            location=trk.region.begin(),
            max_width=400,
            max_height=300)


def hide_preview(view: sublime.View):
    "Hides preview of tracked abbreviation"
    # TODO since `hide_popup()` hides any visible popup, we should check if
    # abbreviation preview is displayed for given view
    view.hide_popup()
    # TODO clear phantoms
    # if self._preview:
    #     self.view.erase_phantoms(abbr_preview_id)
    #     self._preview = None


def preview_popup_html(content: str):
    return """
    <body id="emmet-preview-popup">
        <style>
            body { line-height: 1.5rem; }
            .error { color: red }
        </style>
        <div>%s</div>
    </body>
    """ % content


def preview_phantom_html(content: str):
    return """
    <body id="emmet-preview-phantom">
        <style>
            body {
                background-color: var(--orangish);
                color: #fff;
                border-radius: 3px;
                padding: 1px 3px;
                position: relative;
            }

            .error { color: red }
        </style>
        <div class="main">%s</div>
    </body>
    """ % content


def forced_indicator(content: str):
    "Returns HTML content of forced abbreviation indicator"
    return """
        <body>
            <style>
                #emmet-forced-abbreviation {
                    background-color: var(--greenish);
                    color: #fff;
                    border-radius: 3px;
                    padding: 1px 3px;
                }
            </style>
            <div id="emmet-forced-abbreviation">%s</div>
        </body>
        """ % content


def format_snippet(text, class_name=None):
    class_attr = (' class="%s"' % class_name) if class_name else ''
    line_html = '<div%s style="padding-left: %dpx"><code>%s</code></div>'
    lines = [line_html % (class_attr, indent_size(line, 20), html.escape(line, False)) for line in text.splitlines()]

    return '\n'.join(lines)


def indent_size(line, width=1):
    m = re.match(r'\t+', line)
    return len(m.group(0)) * width if m else 0


def plugin_unloaded():
    for wnd in sublime.windows():
        for view in wnd.views():
            clear_marker(view)
