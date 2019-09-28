import sublime
import sublime_plugin
from . import emmet

markers = {}
abbr_region_id = 'emmet-abbreviation'

def plugin_unloaded():
    for wnd in sublime.windows():
        for view in wnd.views():
            dispose(view)


def create(view, abbr_data, options=None):
    "Creates abbreviation marker"
    return AbbreviationMarker(view, abbr_data, options)


def get(view):
    "Returns current marker for given view, if any"
    global markers
    vid = view.id()
    return vid in markers and markers[vid] or None


def attach(view, marker):
    "Attaches current marker for given view"
    markers[view.id()] = marker


def dispose(view):
    vid = view.id()
    if vid in markers:
        marker = markers[vid]
        marker.reset()
        del markers[vid]


def get_region(view):
    "Returns range of currently marked abbreviation in given view, if any"
    regions = view.get_regions(abbr_region_id)
    return regions and regions[0] or None


def clear_region(view):
    "Removes any abbreviation markers from given view"
    view.erase_regions(abbr_region_id)


def extract(view, loc):
    "Extracts abbreviation from given location and, if it's valid, returns marker for it"
    abbr_data = emmet.extract_abbreviation(view, loc)
    if abbr_data:
        marker = create(view, abbr_data[0], abbr_data[1])
        if marker.valid:
            attach(view, marker)
            return marker

        # Invalid abbreviation in marker, dispose it
        marker.reset()

def from_region(view, begin, end):
    "Extracts abbreviation from given region and, if it's valid, returns marker for it"

class AbbreviationMarker:
    def __init__(self, view, abbr_data, options=None):
        self.view = view
        self.abbr_data = None
        self.options = options or emmet.get_options(view, abbr_data['start'], True)
        self.region = None
        self._data = None
        self.update(abbr_data)

    def __del__(self):
        region = get_region(self.view)
        if region and self.region:
            r1 = region
            r2 = self.region
            if r1.begin() == r2.begin() and r1.end() == r2.end():
                clear_region(self.view)

        self.view = self.region = self.options = None

    @property
    def abbreviation(self):
        return self.region and self.abbr_data['abbreviation'] or None

    @property
    def type(self):
        return self.options['type']

    @property
    def valid(self):
        return self._data and self._data.get('valid', False) or False

    @property
    def simple(self):
        return self._data and self._data.get('simple', False) or False

    @property
    def matched(self):
        return self._data and self._data.get('matched', False) or False

    @property
    def error(self):
        return self._data and self._data.get('error')

    @property
    def error_snippet(self):
        return self._data and self._data.get('snippet')

    @property
    def error_pos(self):
        return self._data and self._data.get('pos', -1) or -1

    def update(self, abbr_data):
        self.abbr_data = abbr_data
        self.region = sublime.Region(abbr_data['start'], abbr_data['end'])
        self.mark()
        self.validate()

    def validate(self):
        "Validates currently marked abbreviation"
        self.region = get_region(self.view)
        if self.region and not self.region.empty():
            prefix = self.options.get('prefix', '')
            abbr = self.view.substr(self.region)[len(prefix):]
            self._data = emmet.validate(abbr, self.options)
            self.abbr_data['abbreviation'] = abbr
        else:
            self.reset()

        return self.valid

    def mark(self):
        "Marks abbreviation in view with current state"
        clear_region(self.view)
        if self.region:
            scope = '%s.emmet' % (self.valid and 'string' or 'invalid',)
            self.view.add_regions(abbr_region_id, [self.region], scope, '',
                sublime.DRAW_SOLID_UNDERLINE | sublime.DRAW_NO_FILL | sublime.DRAW_NO_OUTLINE)

    def reset(self):
        clear_region(self.view)
        self.region = self.abbr_data = self._data = None

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

class ClearAbbreviationMarker(sublime_plugin.TextCommand):
    def run(self, edit, **kw):
        dispose(self.view)
