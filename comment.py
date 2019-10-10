import re
import sublime
import sublime_plugin
from . import emmet
from . import syntax
from . import utils

html_comment_start = '<!--'
html_comment_end = '-->'

re_html_comment_start = re.compile(r'<!--\s*')
re_html_comment_end = re.compile(r'\s*-->')

comment_selector = 'comment'

# NB: use `Emmet` prefix to distinguish default `toggle_comment` action
class EmmetToggleComment(sublime_plugin.TextCommand):
    def run(self, edit):
        view = self.view
        for s in view.sel():
            pt = s.begin()
            if view.match_selector(pt, comment_selector):
                # Caret inside comment, strip it
                comment_region = view.extract_scope(pt)
                remove_comments(view, edit, comment_region)
            elif s.empty():
                # Empty region, find tag
                pass



        if regions is None:
            regions = get_regions(self.view)

        if regions:
            regions = regions[:]
            regions.reverse()

            for r in regions:
                add_html_comment(self.view, edit, r)


def remove_comments(view: sublime.View, edit: sublime.Edit, region: sublime.Region):
    "Removes comment markers from given region"
    text = view.substr(region)

    if text.startswith(html_comment_start) and text.endswith(html_comment_end):
        start_offset = region.begin() + len(html_comment_start)
        end_offset = region.end() - len(html_comment_end)

        # Narrow down offsets for whitespace
        if view.substr(start_offset).isspace():
            start_offset += 1

        if view.substr(end_offset - 1).isspace():
            end_offset -= 1

        start_region = sublime.Region(region.begin(), start_offset)
        end_region = sublime.Region(end_offset, region.end())

        # It's faster to erase the start region first
        # See comment in Default/comment.py plugin
        view.erase(edit, start_region)

        end_region = sublime.Region(
            end_region.begin() - start_region.size(),
            end_region.end() - start_region.size())

        view.erase(edit, end_region)

def get_tag_range(view: sublime.View, edit: sublime.Edit, pt: int, strip_comments=False):
    "Returns tag range for given text position, if possible"
    syntax_name = syntax.from_pos(view, pt)
    print('syntax is %s' % syntax_name)
    if syntax.is_html(syntax_name):
        tag = emmet.get_tag_context(view, pt, syntax.is_xml(syntax_name))
        print('tag found: %s' % tag)
        if tag:
            open_tag = tag.get('open')
            close_tag = tag.get('close')
            r = open_tag

            if close_tag:
                r = open_tag.cover(close_tag)

                # Check if we should strip inner comments
                text = view.substr(r)
                clean_text = strip_html_comments(text)
                if text != clean_text and strip_comments:
                    view.replace(edit, r, clean_text)
                    r = sublime.Region(r.begin(), r.begin() + len(clean_text))

            return r


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
    clean_text = strip_html_comments(text)

    view.insert(edit, r.end(), ' -->')

    if text != clean_text:
        view.replace(edit, r, clean_text)

    view.insert(edit, r.begin(), '<!-- ')


def strip_html_comments(text: str):
    """
    Removes HTML comment markers from given text: does not removes comment itself
    but `<!--` and `-->` only
    """
    result = ''
    offset = 0
    while True:
        m = re_html_comment_start.search(text, offset)
        if m:
            result += text[offset:m.start(0)]
            offset = m.end(0)

            # Find comment end
            m = re_html_comment_end.search(text, offset)
            if m:
                result += text[offset:m.start(0)]
                offset = m.end(0)
        else:
            break

    return result + text[offset:]

class ToggleCommentListener(sublime_plugin.EventListener):
    def on_text_command(self, view, command_name, args):
        if command_name == 'toggle_comment':
            print('run toggle comment with %s' % args)
