import re
import sublime
from . import expand, validate, get_options

abbr_region_id = 'emmet-abbreviation'

def clear_marker_region(view):
    "Removes any abbreviation markers from given view"
    view.erase_regions(abbr_region_id)


def get_marker_region(view):
    "Returns range of currently marked abbreviation in given view, if any"
    regions = view.get_regions(abbr_region_id)
    return regions and regions[0] or None


class AbbreviationMarker:
    def __init__(self, view, start, end):
        self.view = view
        self.options = get_options(view, start)
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

    def update(self, start, end):
        self.region = sublime.Region(start, end)
        self.mark()
        self.validate()

    def validate(self):
        "Validates currently marked abbreviation"
        regions = self.view.get_regions(abbr_region_id)
        self.region = get_marker_region(self.view)
        if self.region and not self.region.empty():
            data = validate(self.abbreviation, self.options)

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
            return expand(self.abbreviation, self.options)
        return ''

    def preview(self):
        """
        Returns generated preview of current abbreviation: if abbreviation is valid,
        returns expanded snippet, otherwise returns error snippet
        """
        if self.region and self.valid:
            try:
                opt = self.options.copy()
                opt['preview'] = True
                snippet = expand(self.abbreviation, opt)
                return popup_content(format_snippet(snippet))

            except Exception as e:
                return popup_content('<div class="error">%s</div>' % format_snippet(str(e)))
        else:
            msg = '%s\n%s' % (self.error_snippet, self.error)
            return popup_content('<div class="error">%s</div>' % format_snippet(msg))


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


def escape_html(text):
    escaped = { '<': '&lt;', '&': '&amp;', '>': '&gt;' }
    return re.sub(r'[<>&]', lambda m: escaped[m.group(0)], text)


def indent_size(line, width=1):
    m = re.match(r'\t+', line)
    if m:
        return len(m.group(0)) * width
    return 0
