import re
import sublime
import sublime_plugin
from . import emmet
from . import syntax
from . import utils

html_comment_start = re.compile(r'<!--\s*')
html_comment_end = re.compile(r'\s*-->')

# NB: use `Emmet` prefix to distinguish default `toggle_comment` action
class EmmetToggleComment(sublime_plugin.TextCommand):
    def run(self, edit, regions=None):
        if regions is None:
            regions = get_regions(self.view)

        if regions:
            regions = regions[:]
            regions.reverse()

            for r in regions:
                add_html_comment(self.view, edit, r)


def append_overlap(r, regions):
    """
    Appends given `r` region to `regions` list and ensures ranges are not overlapped.
    If so, merges `r` with last range
    """
    if r is None:
        return

    if not regions:
        regions.append(r)
    else:
        last = regions[-1]
        if last.intersects(r):
            regions[-1] = last.cover(r)
        else:
            regions.append(r)

def get_regions(view, non_empty=False):
    "Returns regions for tab commening, if any"
    regions = []
    for s in view.sel():
        if s.empty():
            syntax_name = syntax.from_pos(view, s.begin())
            if syntax.is_html(syntax_name):
                tag = emmet.get_tag_context(view, s.begin(), syntax.is_xml(syntax_name))
                if tag:
                    open_tag = tag.get('open')
                    close_tag = tag.get('close')
                    r = close_tag and open_tag.cover(close_tag) or open_tag
                    append_overlap(r, regions)
        elif not non_empty:
            return None
        else:
            append_overlap(s, regions)

    return regions

def add_html_comment(view: sublime.View, edit: sublime.Edit, r: sublime.Region):
    "Adds HTML comments around given range and removes any existing comments inside it"
    text = view.substr(r)
    clean_text = remove_html_comments(text)

    view.insert(edit, r.end(), ' -->')

    if text != clean_text:
        view.replace(edit, r, clean_text)

    view.insert(edit, r.begin(), '<!-- ')


def remove_html_comments(text: str):
    "Removes HTML comments from given text."
    result = ''
    offset = 0
    while True:
        m = html_comment_start.search(text, offset)
        if m:
            result += text[offset:m.start(0)]
            offset = m.end(0)

            # Find comment end
            m = html_comment_end.search(text, offset)
            if m:
                result += text[offset:m.start(0)]
                offset = m.end(0)
        else:
            break

    return result + text[offset:]

