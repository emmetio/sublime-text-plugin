import sublime
import sublime_plugin
from . import emmet_sublime as emmet
from . import utils

class EmmetRemoveTag(sublime_plugin.TextCommand):
    def run(self, edit):
        view = self.view
        for sel in view.sel():
            tag = emmet.get_tag_context(view, sel.begin())
            if tag:
                remove_tag(view, edit, tag)


def remove_tag(view: sublime.View, edit: sublime.Edit, tag: dict):
    if 'close' in tag:
        # Remove open and close tag and dedent inner content
        open_tag = tag['open']
        close_tag = tag['close']
        inner_region = utils.narrow_to_non_space(view, sublime.Region(open_tag.end(), close_tag.begin()))
        if inner_region:
            # Gracefully remove open and close tags and tweak indentation on tag contents
            view.erase(edit, sublime.Region(inner_region.end(), close_tag.end()))

            start_line = view.line(open_tag.begin())
            base_indent = get_line_indent(view, start_line)
            inner_lines = view.lines(inner_region)[1:]
            inner_lines.reverse()

            for line in inner_lines:
                indent = get_line_indent(view, line)
                indent_region = sublime.Region(line.begin(), line.begin() + len(indent))
                view.replace(edit, indent_region, base_indent)

            view.erase(edit, sublime.Region(open_tag.begin(), inner_region.begin()))
        else:
            view.erase(edit, open_tag.cover(close_tag))
    else:
        view.erase(edit, tag['open'])

def get_line_indent(view: sublime.View, line: sublime.Region) -> str:
    "Returns indentation for given line"
    pos = line.begin()
    end = line.end()
    while pos < end and view.substr(pos).isspace():
        pos += 1

    return view.substr(sublime.Region(line.begin(), pos))
