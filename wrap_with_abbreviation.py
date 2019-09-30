import re
import sublime
import sublime_plugin
from . import emmet
from . import syntax
from . import preview

re_indent = re.compile(r'^\s+')

class WrapWithAbbreviation(sublime_plugin.TextCommand):
    def run(self, edit, wrap_abbreviation):
        print('will wrap with %s' % wrap_abbreviation)

    def get_range(self):
        sel = self.view.sel()[0]
        opt = syntax.info(self.view, sel.begin(), 'html')
        region = sel.empty() and find_context_tag(self.view, sel.begin(), opt) or sel
        return region

    def input(self, *args, **kw):
        sel = self.view.sel()[0]
        opt = syntax.info(self.view, sel.begin(), 'html')
        region = self.get_range()
        lines = get_content(self.view, region, True)
        opt['text'] = lines

        return WrapAbbreviationInputHandler(opt)


class WrapAbbreviationInputHandler(sublime_plugin.TextInputHandler):
    def __init__(self, options):
        self.options = options

    def placeholder(self):
        return 'Enter abbreviation'

    def validate(self, text):
        print('validate "%s"' % text)
        return True

    def preview(self, text):
        opt = self.options.copy()
        opt['preview'] = True
        abbr = text.strip()
        if abbr:
            result = emmet.expand(abbr, opt)
            snippet = preview.format_snippet(result)
            return sublime.Html(preview.popup_content(snippet))

def find_context_tag(view, pt, syntax_info=None):
    "Finds tag context for given location and returns its range, if found"
    if syntax_info is None:
        syntax_info = syntax.info(view, pt, 'html')
    syntax_name = syntax_info.get('syntax')
    is_xml = syntax_name in emmet.xml_syntaxes

    if is_xml or syntax_name in emmet.html_syntaxes:
        ctx = emmet.get_tag_context(view, pt, is_xml)
        if ctx:
            # Check how given point relates to matched tag:
            # if it's in either open or close tag, we should wrap tag itself,
            # otherwise we should wrap its contents
            open_tag = ctx.get('open')
            close_tag = ctx.get('close')

            if in_range(open_tag, pt) or (close_tag and in_range(close_tag, pt)):
                return sublime.Region(open_tag.begin(), close_tag and close_tag.end() or open_tag.end())

            if close_tag:
                r = sublime.Region(open_tag.end(), close_tag.begin())
                return narrow_to_non_space(view, region)


def in_range(region, pt):
    return pt > region.begin() and pt < region.end()


def get_content(view, region, lines=False):
    "Returns contents of given region, properly de-indented"
    base_line = view.substr(view.line(region.begin()))
    m = re_indent.match(base_line)
    indent = m and m.group(0) or ''
    src_lines = view.substr(region).splitlines()
    dest_lines = []

    for line in src_lines:
        if len(dest_lines) and line.startswith(indent):
            line = line[len(indent):]
        dest_lines.append(line)

    return lines and dest_lines or '\n'.join(dest_lines)


def narrow_to_non_space(view, region):
    "Returns copy of region which starts and ends at non-space character"
    begin = region.begin()
    end = region.end()

    while begin < end:
        if not view.substr(begin).isspace():
            break
        begin += 1

    while end > begin:
        if not view.substr(end - 1).isspace():
            break
        end -= 1

    return sublime.Region(begin, end)
