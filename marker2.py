import re
import html
import sublime
from . import emmet_sublime as emmet

abbr_region_id = 'emmet-abbreviation'
abbr_preview_id = 'emmet-preview'
markers = {}

class AbbreviationMarker:
    def __init__(self, view: sublime.View, region: sublime.Region, forced: bool=False):
        # Do not capture context for large documents since it may reduce performance
        max_doc_size = view.settings().get('emmet_context_size_limit', 0)
        with_context = max_doc_size > 0 and view.size() < max_doc_size

        self.view = view
        self.forced = forced
        self.options = emmet.get_options(view, region.begin(), with_context)
        self._region = None
        self._data = None
        self._indicator = sublime.PhantomSet(view, abbr_region_id) if forced else None
        self._preview = None
        self._popup_visible = False

        self.region = region

    def __del__(self):
        self.dispose()

    @property
    def region(self):
        return self._region

    @region.setter
    def region(self, value):
        self._region = value
        abbr = self.value

        if abbr:
            self._data = emmet.validate(abbr, self.options)
            self.mark_if_required()
        else:
            self._data = None
            self.unmark()

    @property
    def value(self):
        "Returns current marker value"
        return self.view.substr(self.region) if self.region else None

    @property
    def type(self):
        "Returns current syntax of marked abbreviation, either 'markup' or 'stylesheet'"
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

    def contains(self, pt):
        "Check if current abbreviation range contains given point"
        if self.region is None:
            return False

        # For empty regions, check if given point is equal to region start
        return self.region.contains(pt) if self.region else self.region.begin() == pt

    def mark(self):
        "Marks current abbreviation region in host view"
        scope = 'keyword.operator'
        mark_opt = sublime.DRAW_SOLID_UNDERLINE | sublime.DRAW_NO_FILL | sublime.DRAW_NO_OUTLINE
        self.view.add_regions(abbr_region_id, [self.region], scope, '', mark_opt)

        if self._indicator:
            phantom_region = sublime.Region(self.region.end(), self.region.end())
            phantoms = [sublime.Phantom(phantom_region, self.forced_indicator('>'), sublime.LAYOUT_INLINE)]
            self._indicator.update(phantoms)

    def unmark(self):
        "Removes abbreviation mark from view"
        self.view.erase_regions(abbr_region_id)
        self.view.erase_phantoms(abbr_region_id)

    def mark_if_required(self):
        "Toggles abbreviation mark in view depending on current abbreviation state"
        if self.should_mark():
            self.mark()
        else:
            self.unmark()

    def should_mark(self):
        "Check if current abbreviation should be displayed (e.g. marked) in current view"
        if self.forced:
            # Forced abbreviation should always be marked
            return True

        return self.valid

    ###################################
    ## Expanded abbreviation preview ##
    ###################################

    def get_snippet(self):
        "Returns expanded preview of current abbreviation"
        if self.valid:
            return emmet.expand(self.value, self.options)
        return ''

    def get_preview(self):
        """
        Returns generated preview of current abbreviation: if abbreviation is valid,
        returns expanded snippet, otherwise raises error
        """
        if not self.valid or self.error:
            raise RuntimeError('%s\n%s' % (self.error_snippet, self.error))

        abbr = self.value
        if abbr:
            opt = self.options.copy()
            opt['preview'] = True
            return emmet.expand(abbr, opt)

        return None

    def toggle_preview(self, pos: int, as_phantom=False):
        "Toggles abbreviation preview depending on its state and given location"
        if self.contains(pos) and self.value and (not self.simple or self.type == 'stylesheet'):
            self.show_preview(as_phantom)
        else:
            self.hide_preview()

    def show_preview(self, as_phantom=False):
        "Displays expanded preview of current abbreviation"
        content = None

        try:
            content = format_snippet(self.get_preview())
        except Exception as e:
            content = '<div class="error">%s</div>' % format_snippet(str(e))

        if not content:
            self.hide_preview()
            return

        if as_phantom:
            if self._popup_visible:
                self.view.hide_popup()

            if not self._preview:
                self._preview = sublime.PhantomSet(self.view, abbr_preview_id)

            r = sublime.Region(self.region.end(), self.region.end())
            phantoms = [sublime.Phantom(r, self.preview_phantom_html(content), sublime.LAYOUT_INLINE)]
            self._preview.update(phantoms)
        else:
            def _on_hide():
                self._popup_visible = False
            self.view.show_popup(
                self.preview_popup_html(content),
                flags=sublime.COOPERATE_WITH_AUTO_COMPLETE,
                location=self.region.begin(),
                max_width=400,
                max_height=300,
                on_hide=_on_hide)
            self._popup_visible = True

    def hide_preview(self):
        "Hides preview of current abbreviation"
        if self._popup_visible:
            self.view.hide_popup()
        if self._preview:
            self.view.erase_phantoms(abbr_preview_id)
            self._preview = None

    def preview_popup_html(self, content):
        return """
        <body id="emmet-preview-popup">
            <style>
                body { line-height: 1.5rem; }
                .error { color: red }
            </style>
            <div>%s</div>
        </body>
        """ % content


    def preview_phantom_html(self, content):
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

    def forced_indicator(self, content):
        "Returns HTML content of forced abbreviation indicator"
        return """
        <body>
            <style>
                #emmet-forced-abbreviation {
                    background-color: var(--greenish);
                    color: #fff;
                    border-radius: 3px;
                    padding: 1px 3px;
                    position: relative;
                }
            </style>
            <div id="emmet-forced-abbreviation">%s</div>
        </body>
        """ % content

    def dispose(self):
        "Resets current marker"
        self.unmark()
        self.hide_preview()
        self.view = self.region = self._data = None


def create(view: sublime.View, region: sublime.Region) -> AbbreviationMarker:
    """
    Creates abbreviation marker. If location (insread of region) is provided,
    abbreviation is treated as forced
    """
    forced = False
    if isinstance(region, int):
        # If location is passed, create abbreviation as forced
        forced = True
        region = sublime.Region(region, region)
    marker = AbbreviationMarker(view, region, forced)
    markers[view.buffer_id()] = marker
    return marker


def get(view: sublime.View) -> AbbreviationMarker:
    "Returns current marker for given view, if any"
    return markers.get(view.buffer_id())


def dispose(marker: AbbreviationMarker):
    "Disposes given abbreviation marker"
    buff_id = marker.view.buffer_id()
    if buff_id in markers:
        del markers[buff_id]
    marker.dispose()


def format_snippet(text, class_name=None):
    class_attr = (' class="%s"' % class_name) if class_name else ''
    line_html = '<div%s style="padding-left: %dpx"><code>%s</code></div>'
    lines = [line_html % (class_attr, indent_size(line, 20), html.escape(line, False)) for line in text.splitlines()]

    return '\n'.join(lines)


def indent_size(line, width=1):
    m = re.match(r'\t+', line)
    return len(m.group(0)) * width if m else 0


def plugin_unloaded():
    "Lifecycle hook when plugin is unloaded"
    for marker in markers.values():
        marker.dispose()
