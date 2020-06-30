import re
import sublime
from .emmet.scanner import ScannerException
from .emmet.stylesheet import CSSAbbreviationScope
from . import syntax
from .utils import pairs, get_content

JSX_PREFIX = '<'

re_jsx_abbr_start = re.compile(r'^[a-zA-Z.#\[\(]$')
re_word_bound = re.compile(r'^[\s>;"\']?[a-zA-Z.#!@\[\(]$')
re_stylesheet_word_bound = re.compile(r'^[\s;"\']?[a-zA-Z!@]$')
re_stylesheet_preview_check = re.compile(r'/^:\s*;?$/')

class AbbreviationTrackerType:
    Abbreviation = 'abbreviation'
    Error = 'error'

class AbbreviationTracker:
    __slots__ = ('region', 'abbreviation', 'forced', 'forced', 'offset',
                 'last_pos', 'last_length', 'config', 'simple', 'preview', 'error')
    def __init__(self, abbreviation: str, region: sublime.Region, config: dict, **kwargs):
        self.abbreviation = abbreviation
        "Range in editor for abbreviation"

        self.region = region
        "Actual abbreviation, tracked by current tracker"

        self.config = config

        self.forced = False
        """
        Abbreviation was forced, e.g. must remain in editor even if empty or contains
        invalid abbreviation
        """

        self.offset = 0
        """
        Relative offset from range start where actual abbreviation starts.
        Used to handle prefixes in abbreviation
        """

        self.last_pos = 0
        "Last character location in editor"

        self.last_length = 0
        "Last editor size"

        for k, v in kwargs.items():
            if hasattr(self, k) or k in self.__slots__:
                setattr(self, k, v)


class AbbreviationTrackerValid(AbbreviationTracker):
    __slots__ = ('simple', 'preview')

    def __init__(self, *args, **kwargs):
        self.simple = False
        self.preview = ''
        super().__init__(*args, **kwargs)

class AbbreviationTrackerError(AbbreviationTracker):
    def __init__(self, *args, **kwargs):
        self.error = None
        super().__init__(*args, **kwargs)


class AbbreviationTrackingController:
    "Controller for tracking Emmet abbreviations in editor as user types."

    __slots__ = ('_cache', '_trackers', '_last_pos')

    def __init__(self):
        self._cache = {}
        self._trackers = {}
        self._last_pos = {}

    def get_last_pos(self, editor: sublime.View) -> int:
        "Returns last known location of caret in given editor"
        return self._last_pos.get(editor.id())


    def set_last_pos(self, editor: sublime.View, pos: int):
        "Sets last known caret location for given editor"
        self._last_pos[editor.id()] = pos


    def get_tracker(self, editor: sublime.View) -> AbbreviationTracker:
        "Returns abbreviation tracker for given editor, if any"
        return self._trackers.get(editor.id())

    def typing_abbreviation(self, editor: sublime.View, pos: int) -> AbbreviationTracker:
        "Detects if user is typing abbreviation at given location"
        # Start tracking only if user starts abbreviation typing: entered first
        # character at the word bound
        # NB: get last 2 characters: first should be a word bound(or empty),
        # second must be abbreviation start
        prefix = editor.substr(sublime.Region(max(0, pos - 2), pos))
        syntax_name = syntax.from_pos(editor, pos)
        start = -1
        end = pos
        offset = 0

        if syntax.is_jsx(syntax_name):
            # In JSX, abbreviations should be prefixed
            if len(prefix) == 2 and prefix[0] == JSX_PREFIX and re_jsx_abbr_start.match(prefix[1]):
                start = pos - 2
                offset = len(JSX_PREFIX)
        elif re_word_bound.match(prefix):
            start = pos - 1

        if start >= 0:
            # Check if there’s paired character
            last_ch = prefix[-1]
            if last_ch in pairs and editor.substr(sublime.Region(pos, pos + 1)) == pairs[last_ch]:
                end += 2

            config = self.get_activation_context(editor, pos)
            if config is not None:
                if config['type'] == 'stylesheet' and not re_stylesheet_word_bound.match(prefix):
                    # Additional check for stylesheet abbreviation start: it’s slightly
                    # differs from markup prefix, but we need activation context
                    # to ensure that context under caret is CSS
                    return

                tracker = self.start_tracking(editor, start, end, {'offset': offset, 'config': config})
                if tracker and isinstance(tracker, AbbreviationTrackerValid) and \
                    get_by_key(config, 'context.name') == CSSAbbreviationScope.Section:
                    # Make a silly check for section context: if user start typing
                    # CSS selector at the end of file, it will be treated as property
                    # name and provide unrelated completion by default.
                    # We should check if captured abbreviation actually matched
                    # snippet to continue. Otherwise, ignore this abbreviation.
                    # By default, unresolved abbreviations are converted to CSS properties,
                    # e.g. `a` → `a: ;`. If that’s the case, stop tracking
                    preview = tracker.preview
                    abbreviation = tracker.abbreviation

                    if preview.startswith(abbreviation) and \
                        re_stylesheet_preview_check.match(preview[len(abbreviation):]):
                        self.stop_tracking(editor)
                        return

                return tracker


    def start_tracking(self, editor: sublime.View, start: int, pos: int, params=None) -> AbbreviationTracker:
        """
        Starts abbreviation tracking for given editor
        :param start Location of abbreviation start
        :param pos Current caret position, must be greater that `start`
        """
        config = get_by_key(params, 'config') or get_config(editor, start)

        tracker_params = {'config': config}
        if params:
            tracker_params.update(params)
        tracker = self.create_tracker(editor, (start, pos), tracker_params)

        if tracker:
            self._trackers[editor.id()] = tracker
            return tracker

        self._dispose_tracker(editor)


    def stop_tracking(self, editor: sublime.View, params={}):
        "Stops abbreviation tracking in given editor instance"
        tracker = self.get_tracker(editor)
        if tracker:
            unmark(editor, tracker)
            # TODO imprement forced tracker remove
            # if tracker.forced and not get_by_key(params, 'skip_remove'):
            #     # Contents of forced abbreviation must be removed
            #     editor.replace('', tracker.range[0], tracker.range[1])

            if params.get('force'):
                self._dispose_cache_tracker(editor)
            else:
                # Store tracker in history to restore it if user continues editing
                self.store_tracker(editor, tracker)

            self._dispose_tracker(editor)

    def create_tracker(self, editor: sublime.View, rng: tuple, params: dict) -> AbbreviationTracker:
        """
        Creates abbreviation tracker for given range in editor. Parses contents
        of abbreviation in range and returns either valid abbreviation tracker,
        error tracker or `None` if abbreviation cannot be created from given range
        """
        if rng[0] >= rng[1]:
            # Invalid range
            return

        config = params.get('config')
        offset = params.get('offset', 0)
        abbreviation = editor.substr(sublime.Region(*rng))
        if offset:
            abbreviation = abbreviation[offset:]

        # Basic validation: do not allow empty abbreviations
        # or newlines in abbreviations
        if not abbreviation or '\n' in abbreviation or '\r' in abbreviation:
            return

        region = sublime.Region(*rng)
        tracker_params = {
            'forced': params.get('forced', False),
            'offset': offset,
            'last_pos': rng[1],
            'last_length': editor.size(),
        }

        try:
            tracker_params['simple'] = False

            if config.get('type') == 'stylesheet':
                parsed_abbr = stylesheet_abbreviation(abbreviation)
            else:
                parsed_abbr = markup_abbreviation(abbreviation, {
                    'jsx': config.get('syntax') == 'jsx'
                })
                tracker_params['simple'] = self.is_simple_markup_abbreviation(parsed_abbr)

            preview_config = get_preview_config(editor, config)
            tracker_params['preview'] = expand(parsed_abbr, preview_config)
            return AbbreviationTrackerValid(abbreviation, region, config, tracker_params)
        except ScannerException as err:
            tracker_params['error'] = err
            return AbbreviationTrackerError(abbreviation, region, config, tracker_params)


    def store_tracker(self, editor: sublime.View, tracker: AbbreviationTracker):
        "Stores given tracker in separate cache to restore later"
        self._cache[editor.id()] = tracker


    def get_stored_tracker(self, editor: sublime.View) -> AbbreviationTracker:
        "Returns stored tracker for given editor proxy, if any"
        return self._cache.get(editor.id())


    def restore_tracker(self, editor: sublime.View, pos: int) -> AbbreviationTracker:
        "Tries to restore abbreviation tracker for given editor at specified position"
        tracker = self.get_stored_tracker(editor)

        if tracker and tracker.region.contains(pos):
            # Tracker can be restored at given location. Make sure it’s contents matches
            # contents of editor at the same location. If it doesn’t, reset stored tracker
            # since it’s not valid anymore

            self._dispose_cache_tracker(editor)
            r = sublime.Region(tracker.region.begin() + tracker.offset, tracker.region.end())

            if editor.substr(r) == tracker.abbreviation:
                self._trackers[editor.id()] = tracker
                return tracker

        return None

    def handle_change(self, editor: sublime.View, pos: int) -> AbbreviationTracker:
        "Handle content change in given editor instance"
        tracker = self.get_tracker(editor)
        editor_last_pos = self.get_last_post(editor)
        self.set_last_pos(editor, pos)

        if not tracker:
            # No active tracker, check if we user is actually typing it
            if editor_last_pos is not None and editor_last_pos == pos - 1 and allow_tracking(editor, pos):
                return self.typing_abbreviation(editor, pos)
            return None

        last_pos = tracker.last_pos
        region = tracker.region

        if last_pos < region.begin() or last_pos > region.end():
            # Updated content outside abbreviation: reset tracker
            self.stop_tracking(editor)

        length = editor.size()
        delta = length - tracker.last_Length
        region = sublime.Region(region.a, region.b)

        # Modify region and validate it: if it leads to invalid abbreviation, reset tracker
        update_region(region, delta, last_pos)

        # Handle edge case: empty forced abbreviation is allowed
        if region.empty() and tracker.forced:
            tracker.abbreviation = ''
            return tracker

        # TODO поменять последний аргумент
        next_tracker = self.create_tracker(editor, region, tracker)

        if not next_tracker or (not tracker.forced and not is_valid_tracker(next_tracker, region, pos)):
            self.stop_tracking(editor)
            return

        next_tracker.last_pos = pos
        self._trackers[editor.id()] = next_tracker
        mark(editor, next_tracker)

        return next_tracker


    def handle_selection_change(self, editor: sublime.View, pos: int) -> AbbreviationTracker:
        "Handle selection (caret) change in given editor instance"
        self.set_last_pos(editor, pos)
        tracker = self.get_tracker(editor) or self.restore_tracker(editor, pos)
        if tracker:
            tracker.last_pos = pos
            return tracker


    def get_activation_context(self, editor: sublime.View, pos: int) -> dict:
        """
        Detects and returns valid abbreviation activation context for given location
        in editor which can be used for abbreviation expanding.
        For example, in given HTML code:
        `<div title="Sample" style="">Hello world</div>`
        it’s not allowed to expand abbreviations inside `<div ...>` or `</div>`,
        yet it’s allowed inside `style` attribute and between tags.

        This method ensures that given `pos` is inside location allowed for expanding
        abbreviations and returns context data about it.

        Default implementation works for any editor since it uses own parsers for HTML
        and CSS but might be slow: if your editor supports low-level access to document
        parse tree or tokens, authors should override this method and provide alternative
        based on editor native features.
        """
        syntax_name = syntax.from_pos(editor, pos)
        content = get_content(editor)

        if syntax.is_css(syntax_name):
            return self.get_css_activation_context(editor, pos, syntax_name, get_css_context(content, pos))

        if syntax.is_html(syntax_name):
            ctx = get_html_context(content, pos, {'xml': syntax.is_xml(syntax_name)})

            if not ctx.get('current'):
                return {
                    'syntax': syntax_name,
                    'type': 'markup',
                    'context': get_markup_abbreviation_context(content, ctx),
                    'options': get_output_options(editor, pos)
                }
        else:
            return {
                'syntax': syntax_name,
                'type': 'markup'
            }

    def _dispose_tracker(self, editor: sublime.View):
        e_id = editor.id()
        if e_id in self._trackers:
            del self._trackers[e_id]


    def _dispose_cache_tracker(self, editor: sublime.View):
        e_id = editor.id()
        if e_id in self._cache:
            del self._cache[e_id]



def get_by_key(obj, key):
    "A universal method for accessing deep key property"
    if isinstance(key, str):
        key = key.split('.')

    for k in key:
        if obj is None:
            break

        if isinstance(obj, dict):
            obj = obj.get(k)
        elif hasattr(obj, k):
            obj = getattr(obj, k)

    return obj
