import re
import html
import sublime
from ..emmet import Abbreviation as MarkupAbbreviation, markup_abbreviation, stylesheet_abbreviation
from ..emmet.config import Config
from ..emmet.stylesheet import CSSAbbreviationScope
from .emmet_sublime import JSX_PREFIX, expand, extract_abbreviation
from .utils import pairs, pairs_end, known_tags, replace_with_snippet
from .context import get_activation_context
from .config import get_preview_config, get_settings, get_user_css
from . import syntax
from . import html_highlight

ABBR_REGION_ID = 'emmet-abbreviation'
ABBR_PREVIEW_ID = 'emmet-abbreviation-preview'

re_jsx_abbr_start = re.compile(r'^[a-zA-Z.#\[\(]$')
re_word_bound = re.compile(r'^[\s>;"\'(){}]?[a-zA-Z.#!@\[\(]$')
re_stylesheet_word_bound = re.compile(r'^[\s;"\'(){}]?[a-zA-Z!@]$')
re_stylesheet_preview_check = re.compile(r'/^:\s*;?$/')
re_word_start = re.compile(r'^[a-z]', re.IGNORECASE)
re_bound_char = re.compile(r'^[\s>;"\']')
re_complex_abbr = re.compile(r'[.#>^+*\[\(\{\/]')
re_lorem = re.compile(r'^lorem')

_cache = {}
_trackers = {}
_last_pos = {}
_forced_indicator = {}
_phantom_preview = {}
_has_popup_preview = {}


class AbbreviationTracker:
    __slots__ = ('region', 'abbreviation', 'forced', 'forced', 'offset',
                 'last_pos', 'last_length', 'config', 'simple', 'preview', 'error', 'valid_candidate')
    def __init__(self, abbreviation: str, region: sublime.Region, config: Config, params: dict = None):
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

        self.valid_candidate = True
        "Indicates that current abbreviation is a valid candidate to expand"

        if params:
            for k, v in params.items():
                if hasattr(self, k) or k in self.__slots__:
                    setattr(self, k, v)


class AbbreviationTrackerValid(AbbreviationTracker):
    __slots__ = ('simple', 'preview', 'valid_candidate')

    def __init__(self, *args):
        self.simple = False
        self.preview = ''
        super().__init__(*args)

        self.valid_candidate = is_valid_candidate(self.abbreviation, self.config)

class AbbreviationTrackerError(AbbreviationTracker):
    def __init__(self, *args):
        self.error = None
        super().__init__(*args)


def get_last_pos(editor: sublime.View) -> int:
    "Returns last known location of caret in given editor"
    return _last_pos.get(editor.id())


def set_last_pos(editor: sublime.View, pos: int):
    "Sets last known caret location for given editor"
    _last_pos[editor.id()] = pos


def get_tracker(editor: sublime.View) -> AbbreviationTracker:
    "Returns abbreviation tracker for given editor, if any"
    return _trackers.get(editor.id())

def typing_abbreviation(editor: sublime.View, pos: int) -> AbbreviationTracker:
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

        config = get_activation_context(editor, pos)
        if config is not None:
            ctx_name = config.context['name'] if config.context else CSSAbbreviationScope.Global
            check_bounds_scope = (CSSAbbreviationScope.Global,
                                  CSSAbbreviationScope.Section,
                                  CSSAbbreviationScope.Property)
            if config.type == 'stylesheet' and ctx_name in check_bounds_scope and not re_stylesheet_word_bound.match(prefix):
                # Additional check for stylesheet abbreviation start: it’s slightly
                # differs from markup prefix, but we need activation context
                # to ensure that context under caret is CSS
                return

            tracker = start_tracking(editor, start, end, {'offset': offset, 'config': config})
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
                    stop_tracking(editor)
                    return

            if tracker:
                mark(editor, tracker)

            return tracker


def start_tracking(editor: sublime.View, start: int, pos: int, params: dict = None) -> AbbreviationTracker:
    """
    Starts abbreviation tracking for given editor
    :param start Location of abbreviation start
    :param pos Current caret position, must be greater that `start`
    """
    config = get_by_key(params, 'config') or get_activation_context(editor, start)

    tracker_params = {'config': config}
    if params:
        tracker_params.update(params)

    tracker = create_tracker(editor, sublime.Region(start, pos), tracker_params)

    if tracker:
        _trackers[editor.id()] = tracker
        mark(editor, tracker)
        return tracker

    _dispose_tracker(editor)


def stop_tracking(editor: sublime.View, params: dict = {}):
    "Stops abbreviation tracking in given editor instance"
    tracker = get_tracker(editor)
    if tracker:
        unmark(editor)

        if tracker and tracker.forced:
            edit = params.get('edit')
            if edit:
                # Contents of forced abbreviation must be removed
                editor.replace(edit, tracker.region, '')

        if params.get('force'):
            _dispose_cache_tracker(editor)
        else:
            # Store tracker in history to restore it if user continues editing
            store_tracker(editor, tracker)

        _dispose_tracker(editor)


def create_tracker(editor: sublime.View, region: sublime.Region, params: dict) -> AbbreviationTracker:
    """
    Creates abbreviation tracker for given range in editor. Parses contents
    of abbreviation in range and returns either valid abbreviation tracker,
    error tracker or `None` if abbreviation cannot be created from given range
    """
    config = get_by_key(params, 'config')
    offset = get_by_key(params, 'offset', 0)
    forced = get_by_key(params, 'forced', False)

    if region.a > region.b or (region.a == region.b and not forced):
        # Invalid range
        return

    abbreviation = editor.substr(region)
    if offset:
        abbreviation = abbreviation[offset:]

    # Basic validation: do not allow empty abbreviations
    # or newlines in abbreviations
    if (not abbreviation and not forced) or '\n' in abbreviation or '\r' in abbreviation:
        return

    tracker_params = {
        'forced': forced,
        'offset': offset,
        'last_pos': region.end(),
        'last_length': editor.size(),
    }

    try:
        tracker_params['simple'] = False

        if config.type == 'stylesheet':
            parsed_abbr = stylesheet_abbreviation(abbreviation, config)
        else:
            parsed_abbr = markup_abbreviation(abbreviation, config)
            jsx = config and syntax.is_jsx(config.syntax)
            tracker_params['simple'] = not jsx and is_simple_markup_abbreviation(parsed_abbr)

        preview_config = get_preview_config(config)
        tracker_params['preview'] = expand(abbreviation, preview_config)
        if tracker_params['preview'] or forced:
            # Create tracker only if preview is not empty for non-forced abbreviation.
            # Empty preview means Emmet was unable to find proper match for given
            # abbreviation. Most likely it happens in stylesheets in `Section` scope
            return AbbreviationTrackerValid(abbreviation, region, config, tracker_params)
    except Exception as err:
        tracker_params['error'] = {
            'message': err.message,
            'pos': err.pos,
            'pointer': '%s^' % ('-' * err.pos, ) if err.pos is not None else ''
        }
        return AbbreviationTrackerError(abbreviation, region, config, tracker_params)


def store_tracker(editor: sublime.View, tracker: AbbreviationTracker):
    "Stores given tracker in separate cache to restore later"
    _cache[editor.id()] = tracker


def get_stored_tracker(editor: sublime.View) -> AbbreviationTracker:
    "Returns stored tracker for given editor proxy, if any"
    return _cache.get(editor.id())


def restore_tracker(editor: sublime.View, pos: int) -> AbbreviationTracker:
    "Tries to restore abbreviation tracker for given editor at specified position"
    tracker = get_stored_tracker(editor)

    if tracker and tracker.region.contains(pos):
        r = sublime.Region(tracker.region.begin() + tracker.offset, tracker.region.end())

        if editor.substr(r) == tracker.abbreviation:
            if tracker.config and tracker.config.type == 'stylesheet' and not at_word_bound(editor, r):
                # NB: dirty check for word bound on the right of abbreviation.
                # For example, expanding `p` would produce `padding: ;`, but moving
                # caret to first `p` will expand tracker since it matches
                # original abbreviation. This dirty check tries to ensure that we
                # actually trying to restore tracker
                return None

            _trackers[editor.id()] = tracker
            mark(editor, tracker)
            tracker.last_length = editor.size()
            return tracker

    return None


def at_word_bound(editor: sublime.View, r: sublime.Region) -> bool:
    ch = editor.substr(r.end())
    return not ch or re_bound_char.match(ch)


def suggest_abbreviation_tracker(view: sublime.View, pos: int) -> AbbreviationTracker:
    "Tries to extract abbreviation from given position and returns tracker for it, if available"
    trk = get_tracker(view)
    if trk and not trk.region.contains(pos):
        stop_tracking(view)
        trk = None

    if not trk:
        # Try to extract abbreviation from current location
        config = get_activation_context(view, pos)
        if config:
            abbr = extract_abbreviation(view, pos, config)
            if abbr:
                offset = abbr.location - abbr.start
                return start_tracking(view, abbr.start, abbr.end, {'config': config, 'offset': offset})


def handle_change(editor: sublime.View, pos: int) -> AbbreviationTracker:
    "Handle content change in given editor instance"
    tracker = get_tracker(editor)
    editor_last_pos = get_last_pos(editor)
    set_last_pos(editor, pos)

    if not tracker:
        # No active tracker, check if we user is actually typing abbreviation
        if editor_last_pos is not None and editor_last_pos == pos - 1 and allow_tracking(editor, pos):
            return typing_abbreviation(editor, pos)
        return None

    last_pos = tracker.last_pos
    region = tracker.region

    if last_pos < region.begin() or last_pos > region.end():
        # Updated content outside abbreviation: reset tracker
        stop_tracking(editor)
        return None

    length = editor.size()
    delta = length - tracker.last_length
    region = sublime.Region(region.a, region.b)

    # Modify region and validate it: if it leads to invalid abbreviation, reset tracker
    update_region(region, delta, last_pos)

    # Handle edge case: empty forced abbreviation is allowed
    if region.empty() and tracker.forced:
        tracker.abbreviation = ''
        return tracker

    next_tracker = create_tracker(editor, region, tracker)

    if not next_tracker or (not tracker.forced and not is_valid_tracker(next_tracker, region, pos)):
        stop_tracking(editor)
        return

    next_tracker.last_pos = pos
    _trackers[editor.id()] = next_tracker
    mark(editor, next_tracker)

    return next_tracker


def handle_selection_change(editor: sublime.View, pos: int) -> AbbreviationTracker:
    "Handle selection (caret) change in given editor instance"
    last_pos = _last_pos.get(editor.id(), -1)
    set_last_pos(editor, pos)

    # Do not restore tracker if selection wasn’t changed.
    # Otherwise, it will restore just expanded tracker in some cases,
    # like `#ddd` (e.g. abbreviation is the same as result)
    tracker = get_tracker(editor) or (last_pos != pos and restore_tracker(editor, pos))
    if tracker:
        tracker.last_pos = pos
        return tracker


def dispose_editor(editor: sublime.View):
    """
    Method should be called when given editor instance will be no longer
    available to clean up cached data
    """
    stop_tracking(editor)
    _dispose_cache_tracker(editor)
    _dispose_tracker(editor)
    remove_cache_item(editor, _last_pos)


def _dispose_tracker(editor: sublime.View):
    remove_cache_item(editor, _trackers)


def _dispose_cache_tracker(editor: sublime.View):
    remove_cache_item(editor, _cache)


def remove_cache_item(editor: sublime.View, cache: dict):
    e_id = editor.id()
    if e_id in cache:
        del cache[e_id]


def get_by_key(obj, key, default_value=None):
    "A universal method for accessing deep property by dot-separated key"
    if isinstance(key, str):
        key = key.split('.')

    for k in key:
        if obj is None:
            break

        if isinstance(obj, dict):
            obj = obj.get(k)
        elif hasattr(obj, k):
            obj = getattr(obj, k)

    return obj if obj is not None else default_value


def update_region(region: sublime.Region, delta: int, last_pos: int) -> sublime.Region:
    if delta < 0:
        # Content removed
        if last_pos == region.begin():
            # Updated content at the abbreviation edge
            region.a += delta
            region.b += delta
        elif region.begin() < last_pos <= region.end():
            region.b += delta
    elif delta > 0 and region.begin() <= last_pos <= region.end():
        # Content inserted
        region.b += delta

    return region


def is_valid_tracker(tracker: AbbreviationTracker, region: sublime.Region, pos: int) -> bool:
    "Check if given tracker is in valid state for keeping it marked"
    if isinstance(tracker, AbbreviationTrackerError):
        if region.end() == pos:
            # Last entered character is invalid
            return False

        abbreviation = tracker.abbreviation
        start = region.begin()
        target_pos = region.end()
        while target_pos > start:
            ch = abbreviation[target_pos - start - 1]
            if ch in pairs_end:
                target_pos -= 1
            else:
                break

        return target_pos != pos

    return True


def is_simple_markup_abbreviation(abbr: MarkupAbbreviation) -> bool:
    if len(abbr.children) == 1 and not abbr.children[0].children:
        # Single element: might be a HTML element or text snippet
        first = abbr.children[0]
        # XXX silly check for common snippets like `!`. Should read contents
        # of expanded abbreviation instead
        return not first.name or re_word_start.match(first.name)

    return not abbr.children


def allow_tracking(editor: sublime.View, pos: int) -> bool:
    "Check if abbreviation tracking is allowed in editor at given location"
    if is_enabled(editor, pos):
        syntax_name = syntax.from_pos(editor, pos)
        return syntax.is_supported(syntax_name) or syntax.is_jsx(syntax_name)

    return False


def is_enabled(view: sublime.View, pos: int, skip_selector=False) -> bool:
    "Check if Emmet abbreviation tracking is enabled"
    auto_mark = get_settings('auto_mark', False)

    if auto_mark is False or (not skip_selector and not syntax.in_activation_scope(view, pos)):
        return False

    if auto_mark is True:
        return True

    syntax_info = syntax.info(view, pos)
    return syntax_info['type'] == auto_mark


def mark(editor: sublime.View, tracker: AbbreviationTracker):
    "Marks tracker in given view"
    scope = get_settings('marker_scope', 'region.accent')
    editor.erase_regions(ABBR_REGION_ID)

    if tracker.valid_candidate:
        # Do not mark abbreviation if it’s not known candidate
        mark_opt = sublime.DRAW_SOLID_UNDERLINE | sublime.DRAW_NO_FILL | sublime.DRAW_NO_OUTLINE
        editor.add_regions(ABBR_REGION_ID, [tracker.region], scope, '', mark_opt)

    if isinstance(tracker, AbbreviationTrackerValid) and tracker.forced:
        phantoms = [
            sublime.Phantom(tracker.region, forced_indicator('⋮>'), sublime.LAYOUT_INLINE)
        ]

        key = editor.id()
        if key not in _forced_indicator:
            _forced_indicator[key] = sublime.PhantomSet(editor, ABBR_REGION_ID)
        _forced_indicator[key].update(phantoms)


def unmark(editor: sublime.View):
    "Remove current tracker marker from given view"
    editor.erase_regions(ABBR_REGION_ID)
    editor.erase_phantoms(ABBR_REGION_ID)
    hide_preview(editor)


def is_preview_enabled(tracker: AbbreviationTracker) -> bool:
    "Check if preview is enabled for given tracker"
    preview = get_settings('abbreviation_preview', True)
    return preview is True or preview == tracker.config.type


def show_preview(editor: sublime.View, tracker: AbbreviationTracker):
    "Displays expanded preview of abbreviation in current tracker in given view"
    if not is_preview_enabled(tracker):
        return

    key = editor.id()
    content = None
    as_phantom = tracker.config.type == 'stylesheet'

    if isinstance(tracker, AbbreviationTrackerError):
        # Display error snippet
        err = tracker.error
        snippet = html.escape( re.sub(r'\s+at\s\d+$', '', err['message']), False)
        content = '<div class="error pointer">%s</div><div class="error message">%s</div>' % (err['pointer'], snippet)
    elif isinstance(tracker, AbbreviationTrackerValid) and tracker.abbreviation and (tracker.forced or as_phantom or not tracker.simple):
        snippet = tracker.preview
        if tracker.config.type != 'stylesheet':
            if syntax.is_html(tracker.config.syntax):
                snippet = html_highlight.highlight(snippet)
            else:
                snippet = html.escape(snippet, False)
            content = '<div class="markup-preview">%s</div>' % format_snippet(snippet)
        else:
            content = format_snippet(snippet)

    if not content:
        hide_preview(editor)
        return

    if as_phantom:
        pos = tracker.region.end()
        r = sublime.Region(pos, pos)
        phantoms = [sublime.Phantom(r, preview_phantom_html(content), sublime.LAYOUT_INLINE)]

        if key not in _phantom_preview:
            _phantom_preview[key] = sublime.PhantomSet(editor, ABBR_PREVIEW_ID)
        _phantom_preview[key].update(phantoms)
    else:
        _has_popup_preview[key] = True
        editor.show_popup(
            preview_popup_html(content),
            flags=sublime.COOPERATE_WITH_AUTO_COMPLETE,
            location=tracker.region.begin(),
            max_width=400,
            max_height=300)

def hide_preview(editor: sublime.View):
    "Hides preview of current abbreviation in given view"
    key = editor.id()
    if _has_popup_preview.get(key):
        editor.hide_popup()
        del _has_popup_preview[key]
    if _phantom_preview.get(key):
        editor.erase_phantoms(ABBR_PREVIEW_ID)
        del _phantom_preview[key]


def preview_popup_html(content: str):
    return """
    <body id="emmet-preview-popup">
        <style>
            body { line-height: 1.5rem; }
            .error { color: red }
            .error.message { font-size: 11px; line-height: 1.3rem; }
            .markup-preview { font-size: 11px; line-height: 1.3rem; }
            %s
            %s
        </style>
        <div>%s</div>
    </body>
    """ % (html_highlight.styles(), get_user_css(), content)


def preview_phantom_html(content: str):
    return """
    <body id="emmet-preview-phantom">
        <style>
            body {
                background-color: #1D9B45;
                color: #fff;
                border-radius: 3px;
                padding: 0 3px;
                position: relative;
            }

            .error { color: red }
            %s
        </style>
        <div class="main">%s</div>
    </body>
    """ % (get_user_css(), content)


def forced_indicator(content: str):
    "Returns HTML content of forced abbreviation indicator"
    return """
        <body id="emmet-forced-abbreviation">
            <style>
                #emmet-forced-abbreviation .indicator {
                    background-color: var(--greenish);
                    color: #fff;
                    border-radius: 3px;
                    padding: 0 3px;
                }
                %s
            </style>
            <div class="indicator">%s</div>
        </body>
        """ % (get_user_css(), content)


def format_snippet(text: str, class_name=None):
    class_attr = (' class="%s"' % class_name) if class_name else ''
    line_html = '<div%s style="padding-left: %dpx"><code>%s</code></div>'
    lines = [line_html % (class_attr, indent_size(line, 20), line) for line in text.splitlines()]

    return '\n'.join(lines)


def indent_size(line, width=1):
    m = re.match(r'\t+', line)
    return len(m.group(0)) * width if m else 0


def plugin_unloaded():
    for wnd in sublime.windows():
        for view in wnd.views():
            unmark(view)

def main_view(fn):
    "Method decorator for running actions in code views only"
    def wrapper(self, view):
        if not view.settings().get('is_widget'):
            fn(self, view)

    return wrapper


def expand_tracker(editor: sublime.View, edit: sublime.Edit, tracker: AbbreviationTracker):
    "Expands abbreviation from given tracker"
    if isinstance(tracker, AbbreviationTrackerValid):
        snippet = expand(tracker.abbreviation, tracker.config)
        replace_with_snippet(editor, edit, tracker.region, snippet)


def is_valid_candidate(abbr: str, config: Config) -> bool:
    "Check if given string is a valid candidate for Emmet abbreviation"
    if re_complex_abbr.search(abbr):
        return True

    # Looks like a single-word abbreviation, check if it’s a valid candidate:
    # * contains dash (web components)
    # * upper-cased (JSX, Svelte components)
    # * known HTML tags
    # * known Emmet snippets
    if config.type == 'markup' and config.syntax in get_settings('known_snippets_only', []):
        return '-' in abbr \
            or abbr[0].isupper() \
            or abbr in known_tags \
            or abbr in config.snippets \
            or re_lorem.match(abbr)

    return True
