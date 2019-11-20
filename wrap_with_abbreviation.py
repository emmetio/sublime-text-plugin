import re
import sublime
import sublime_plugin
from . import emmet_sublime as emmet
from . import preview
from . import utils

re_indent = re.compile(r'^\s+')
last_abbreviation = None

class EmmetWrapWithAbbreviation(sublime_plugin.TextCommand):
    def run(self, edit, wrap_abbreviation):
        global last_abbreviation # pylint: disable=global-statement
        if wrap_abbreviation:
            snippet = emmet.expand(wrap_abbreviation, self.options)
            utils.replace_with_snippet(self.view, edit, self.region, snippet)
            last_abbreviation = wrap_abbreviation


    def input(self, *args, **kwargs):
        # pylint: disable=attribute-defined-outside-init
        sel = self.view.sel()[0]

        self.options = emmet.get_options(self.view, sel.begin(), True)
        self.region = get_wrap_region(self.view, sel, self.options)
        self.lines = get_content(self.view, self.region, True)
        self.options['text'] = self.lines

        return WrapAbbreviationInputHandler(self.options)


class WrapAbbreviationInputHandler(sublime_plugin.TextInputHandler):
    def __init__(self, options: dict):
        self.options = options.copy()
        self.options['preview'] = True

    def placeholder(self):
        return 'Enter abbreviation'

    def initial_text(self):
        return last_abbreviation

    def validate(self, text: str):
        data = emmet.validate(text, self.options)
        return data and data.get('valid')

    def preview(self, text: str):
        abbr = text.strip()
        snippet = None
        if abbr:
            try:
                result = emmet.expand(abbr, self.options)
                snippet = preview.format_snippet(result)
            except:
                snippet = '<div class="error">Invalid abbreviation</div>'

        if snippet:
            return sublime.Html(popup_content(snippet))


def in_range(region: sublime.Region, pt: int):
    return region.begin() < pt < region.end()


def get_content(view: sublime.View, region: sublime.Region, lines=False):
    "Returns contents of given region, properly de-indented"
    base_line = view.substr(view.line(region.begin()))
    m = re_indent.match(base_line)
    indent = m.group(0) if m else ''
    src_lines = view.substr(region).splitlines()
    dest_lines = []

    for line in src_lines:
        if dest_lines and line.startswith(indent):
            line = line[len(indent):]
        dest_lines.append(line)

    return dest_lines if lines else '\n'.join(dest_lines)


def popup_content(content: str):
    return """
    <body>
        <style>
            body { font-size: 0.8rem; }
            .error { color: red }
        </style>
        <div>%s</div>
    </body>
    """ % content


def get_wrap_region(view: sublime.View, sel: sublime.Region, options: dict) -> sublime.Region:
    "Returns region to wrap with abbreviation"
    if sel.empty() and options.get('context'):
        # If there’s no selection than user wants to wrap current tag container
        ctx = options['context']
        pt = sel.begin()

        # Check how given point relates to matched tag:
        # if it's in either open or close tag, we should wrap tag itself,
        # otherwise we should wrap its contents
        open_tag = ctx.get('open')
        close_tag = ctx.get('close')

        if in_range(open_tag, pt) or (close_tag and in_range(close_tag, pt)):
            return sublime.Region(open_tag.begin(), close_tag and close_tag.end() or open_tag.end())

        if close_tag:
            r = sublime.Region(open_tag.end(), close_tag.begin())
            return utils.narrow_to_non_space(view, r)

    return sel
