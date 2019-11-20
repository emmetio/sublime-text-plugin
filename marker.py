import sublime
import sublime_plugin
from . import emmet_sublime as emmet
from .emmet.extract_abbreviation import ExtractedAbbreviation

markers = {}
abbr_region_id = 'emmet-abbreviation'

def plugin_unloaded():
    "Lifecycle hook when plugin is unloaded"
    for wnd in sublime.windows():
        for view in wnd.views():
            dispose(view)


class AbbreviationMarker:
    def __init__(self, view: sublime.View, abbr_data: ExtractedAbbreviation, options: dict=None):
        self.view = view
        self.abbr_data = None
        # Do not capture context for large documents since it may reduce performance
        max_doc_size = view.settings().get('emmet_context_size_limit', 0)
        with_context = max_doc_size > 0 and view.size() < max_doc_size
        self.options = options or emmet.get_options(view, abbr_data.start, with_context)
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
        """
        Returns extracted abbreviation for current marker.
        Note that it may differ from *selected* abbreviation by current marker
        """
        return self.abbr_data.abbreviation if self.region else None

    @property
    def type(self):
        return self.options['type']

    @property
    def valid(self):
        "Check if current abbreviation is valid"
        return self._data.get('valid', False) if self._data else False

    @property
    def simple(self):
        "Check if current abbreviation is simple, e.g. looks like a regular word"
        return self._data.get('simple', False) if self._data else False

    @property
    def matched(self):
        """
        Check if current simple abbreviation is matched with known snippets or
        HTML tags, e.g. hints that current "simple" word is actually an expected
        tag
        """
        return self._data.get('matched', False) if self._data else False

    @property
    def error(self):
        "Check if currently extracted abbreviation can’t be expanded"
        return self._data and self._data.get('error')

    @property
    def error_snippet(self):
        "Returns code snippet for current invalid abbreviation"
        return self._data and self._data.get('snippet')

    @property
    def error_pos(self):
        "Returns error location in currently invalid abbreviation"
        return self._data.get('pos', -1) if self._data else -1

    def update(self, abbr_data: ExtractedAbbreviation):
        "Updated marked data from given extracted abbreviation"
        self.abbr_data = abbr_data
        self.validate(sublime.Region(abbr_data.start, abbr_data.end))

    def validate(self, region: sublime.Region=None):
        "Validates currently marked abbreviation"
        if region is None:
            region = get_region(self.view)

        if region and not region.empty():
            prefix = self.options.get('prefix', '')
            abbr = self.view.substr(region)[len(prefix):]
            self._data = emmet.validate(abbr, self.options)
            self.abbr_data.abbreviation = abbr
            self.region = region
            self.mark()
        else:
            self.reset()

        return self.valid

    def _validate_region(self, region: sublime.Region):
        "Validates abbreviation found in given region in current view"
        if region and not region.empty():
            prefix = self.options.get('prefix', '')
            abbr = self.view.substr(region)[len(prefix):]
            return emmet.validate(abbr, self.options)
        return None

    def mark(self):
        "Marks abbreviation in view with current state"
        clear_region(self.view)
        if self.region:
            scope = '%s.emmet' % ('entity' if self.valid else 'error',)
            self.view.add_regions(abbr_region_id, [self.region], scope, '',
                sublime.DRAW_SOLID_UNDERLINE | sublime.DRAW_NO_FILL | sublime.DRAW_NO_OUTLINE)

    def reset(self):
        "Resets current marker"
        clear_region(self.view)
        self.region = self.abbr_data = self._data = None

    def contains(self, pt):
        "Check if current abbreviation range contains given point"
        return self.region and self.region.contains(pt)

    def snippet(self):
        "Returns expanded preview of current abbreviation"
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

        return None


def create(view: sublime.View, abbr_data: ExtractedAbbreviation, options=None) -> AbbreviationMarker:
    "Creates abbreviation marker"
    return AbbreviationMarker(view, abbr_data, options)


def get(view: sublime.View) -> AbbreviationMarker:
    "Returns current marker for given view, if any"
    return markers.get(view.id())


def attach(view: sublime.View, marker: AbbreviationMarker):
    "Attaches current marker for given view"
    markers[view.id()] = marker


def dispose(view: sublime.View):
    "Removes markers from given view"
    vid = view.id()
    if vid in markers:
        marker = markers[vid]
        marker.reset()
        del markers[vid]


def get_region(view: sublime.View) -> sublime.Region:
    "Returns range of currently marked abbreviation in given view, if any"
    regions = view.get_regions(abbr_region_id)
    return regions[0] if regions else None


def clear_region(view: sublime.View):
    "Removes any abbreviation markers from given view"
    view.erase_regions(abbr_region_id)


def extract(view: sublime.View, loc: int) -> AbbreviationMarker:
    "Extracts abbreviation from given location and, if it's valid, returns marker for it"
    abbr_data = emmet.extract_abbreviation(view, loc)
    if abbr_data:
        marker = create(view, abbr_data[0])
        if marker.valid:
            attach(view, marker)
            return marker

        # Invalid abbreviation in marker, dispose it
        marker.reset()
    return None


class EmmetClearAbbreviationMarker(sublime_plugin.TextCommand):
    def run(self, edit):
        dispose(self.view)
