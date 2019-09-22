import re
import sublime
import sublime_plugin
from . import emmet

active_preview = False
active_preview_id = None
markers = {}
abbr_region_id = 'emmet-abbreviation'


# List of scope selectors where abbreviation should automatically
# start abbreviation marking
marker_selectors = [
    "text.html - (entity, punctuation.definition.tag.end)",
    "source.css - meta.selector - meta.property-value - string - punctuation - comment"
]

def plugin_unloaded():
    for wnd in sublime.windows():
        for view in wnd.views():
            clear_marker_region(view)
            if view.id() == active_preview_id:
                hide_preview(view)


def clear_marker_region(view):
    "Removes any abbreviation markers from given view"
    view.erase_regions(abbr_region_id)


def get_marker_region(view):
    "Returns range of currently marked abbreviation in given view, if any"
    regions = view.get_regions(abbr_region_id)
    return regions and regions[0] or None


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
    for sel in marker_selectors:
        if view.match_selector(pt, sel):
            return True

    return False


def is_css_value_context(view, pt):
    "Check if given location in view is a CSS property value"
    return view.match_selector(pt, 'meta.property-value | punctuation.terminator.rule')


def is_css_color_start(view, begin, end):
    "Check if given view substring is a hex CSS color"
    return view.substr(sublime.Region(begin, end)) == '#'


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
    opt = emmet.get_options(view, pt)
    abbr_data = emmet.extract(line, pt - line_start, opt)

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

phantom_sets_by_buffer = {}

def show_preview(view, marker):
    globals()['active_preview'] = True
    globals()['active_preview_id'] = view.id()

    content = None
    try:
        content = format_snippet(marker.preview())
    except Exception as e:
        content = '<div class="error">%s</div>' % format_snippet(str(e))

    if content:
        if marker.type == 'stylesheet':
            buffer_id = view.buffer_id()
            if buffer_id not in phantom_sets_by_buffer:
                phantom_set = sublime.PhantomSet(view, 'emmet')
                phantom_sets_by_buffer[buffer_id] = phantom_set
            else:
                phantom_set = phantom_sets_by_buffer[buffer_id]

            r = sublime.Region(marker.region.end(), marker.region.end())
            phantoms = [sublime.Phantom(r, phantom_content(content), sublime.LAYOUT_INLINE)]
            phantom_set.update(phantoms)
        else:
            view.show_popup(popup_content(content), 0, marker.region.begin(), 400, 300)


def hide_preview(view):
    if active_preview and active_preview_id == view.id():
        view.hide_popup()

    buffer_id = view.buffer_id()
    if buffer_id in phantom_sets_by_buffer:
        del phantom_sets_by_buffer[buffer_id]
        view.erase_phantoms('emmet')

    globals()['active_preview'] = False
    globals()['active_preview_id'] = None


def toggle_preview_for_pos(view, marker, pos):
    "Toggle Emmet abbreviation preview display for given marker and location"
    if marker.contains(pos) and (not marker.simple or marker.type == 'stylesheet'):
        show_preview(view, marker)
    else:
        hide_preview(view)


def get_caret(view):
    return view.sel()[0].begin()


def validate_marker(view, marker):
    "Validates given marker right after modifications *inside* it"
    marker.validate()
    if not marker.region:
        # In case if user removed abbreviation, `marker` will end up
        # with empty state
        dispose_marker(view)


def format_snippet(text, class_name=None):
    class_attr = class_name and (' class="%s"' % class_name) or ''
    lines = [
        '<div%s style="padding-left: %dpx"><code>%s</code></div>' % (class_attr, indent_size(line, 20), escape_html(line)) for line in text.splitlines()
    ]

    return '\n'.join(lines)


def popup_content(content):
    return """
    <body>
        <style>
            body { line-height: 1.5rem; }
            .error { color: red }
        </style>
        <div>%s</div>
    </body>
    """ % content


def phantom_content(content):
    return """
    <body>
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


def escape_html(text):
    escaped = { '<': '&lt;', '&': '&amp;', '>': '&gt;' }
    return re.sub(r'[<>&]', lambda m: escaped[m.group(0)], text)


def indent_size(line, width=1):
    m = re.match(r'\t+', line)
    if m:
        return len(m.group(0)) * width
    return 0


def nonpanel(fn):
    def wrapper(self, view):
        if not view.settings().get('is_widget'):
            fn(self, view)
    return wrapper


class AbbreviationMarker:
    def __init__(self, view, start, end, options=None):
        self.view = view
        self.options = options or emmet.get_options(view, start, True)
        self.region = None
        self.valid = False
        self.simple = False
        self.matched = False
        self.error = self.error_snippet = None
        self.error_pos = -1
        self.update(start, end)

    def __del__(self):
        regions = self.view.get_regions(abbr_region_id)
        if regions and self.region:
            r1 = regions[0]
            r2 = self.region
            if r1.begin() == r2.begin() and r1.end() == r2.end():
                self.view.erase_regions(abbr_region_id)

        self.view = self.region = self.options = None

    @property
    def abbreviation(self):
        return self.region and self.view.substr(self.region) or None

    @property
    def type(self):
        return self.options['type']

    def update(self, start, end):
        self.region = sublime.Region(start, end)
        self.mark()
        self.validate()

    def validate(self):
        "Validates currently marked abbreviation"
        self.region = get_marker_region(self.view)
        if self.region and not self.region.empty():
            data = emmet.validate(self.abbreviation, self.options)

            if data['valid']:
                self.valid = True
                self.simple = data['simple']
                self.matched = data['matched']
                self.error = self.error_snippet = None
                self.error_pos = -1
            else:
                self.valid = self.simple = self.matched = False
                self.error = data['error']
                self.error_snippet = data['snippet']
                self.error_pos = data['pos']
            self.mark()
        else:
            self.reset()

        return self.valid

    def mark(self):
        "Marks abbreviation in view with current state"
        clear_marker_region(self.view)
        if self.region:
            scope = '%s.emmet' % (self.valid and 'string' or 'invalid',)
            self.view.add_regions(abbr_region_id, [self.region], scope, '',
                sublime.DRAW_SOLID_UNDERLINE | sublime.DRAW_NO_FILL | sublime.DRAW_NO_OUTLINE)

    def reset(self):
        self.valid = self.simple = self.matched = False
        self.region = self.error = self.error_snippet = None
        self.error_pos = -1
        clear_marker_region(self.view)

    def contains(self, pt):
        "Check if current abbreviation range contains given point"
        return self.region and self.region.contains(pt)

    def snippet(self):
        if self.valid:
            return emmet.expand(self.abbreviation, self.options)
        return ''

    def preview(self):
        """
        Returns generated preview of current abbreviation: if abbreviation is valid,
        returns expanded snippet, otherwise raises error
        """
        if not self.valid or self.error:
            raise RuntimeError('%s\n%s' % (self.error_snippet, self.error))

        if self.region:
            opt = self.options.copy()
            opt['preview'] = True
            return emmet.expand(self.abbreviation, opt)

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
                # Modifications made completely inside abbreviation, should be already validated
                pass
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
            elif next_inside and caret > last_pos:
                # Modifications made right before marker
                marker.update(last_pos, marker_region.end())
            elif not next_inside:
                # Modifications made outside marker
                dispose_marker(view)
                marker = None

        if not marker and caret > last_pos:
            # We’re able to start abbreviation mark
            if is_abbreviation_bound(view, last_pos) and is_abbreviation_context(view, caret):
                # User started abbreviation typing
                marker_from_line(view, caret)
            elif is_css_value_context(view, caret) and is_css_color_start(view, last_pos, caret):
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

        if marker and marker.valid:
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
        sel = self.view.sel()
        marker = get_marker(self.view)
        caret = get_caret(self.view)

        if marker.contains(caret):
            if marker.valid:
                region = marker.region
                snippet = emmet.expand(marker.abbreviation, marker.options)
                sel.clear()
                sel.add(sublime.Region(region.begin(), region.begin()))
                self.view.replace(edit, region, '')
                self.view.run_command('insert_snippet', {'contents': snippet})

            dispose_marker(self.view)

class ClearAbbreviationMarker(sublime_plugin.TextCommand):
    def run(self, edit, **kw):
        dispose_marker(self.view)
