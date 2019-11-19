import sublime
import sublime_plugin
from . import emmet_sublime as emmet
from . import syntax
from . import utils

html_comment = {
    'start': '<!--',
    'end': '-->'
}

css_comment = {
    'start': '/*',
    'end': '*/'
}

comment_selector = 'comment'

# NB: use `Emmet` prefix to distinguish default `toggle_comment` action
class EmmetToggleComment(sublime_plugin.TextCommand):
    def run(self, edit):
        view = self.view
        for s in view.sel():
            pt = s.begin()
            syntax_name = syntax.from_pos(view, pt)
            tokens = css_comment if syntax.is_css(syntax_name) else html_comment

            if view.match_selector(pt, comment_selector):
                # Caret inside comment, strip it
                comment_region = view.extract_scope(pt)
                remove_comments(view, edit, comment_region, tokens)
            elif s.empty():
                # Empty region, find tag
                region = get_range_for_comment(view, pt)
                if region is None:
                    # No tag found, comment line
                    region = utils.narrow_to_non_space(view, view.line(pt))

                # If there are any comments inside region, remove them
                comments = get_comment_regions(view, region, tokens)
                if comments:
                    removed = 0
                    comments.reverse()
                    for c in comments:
                        removed += remove_comments(view, edit, c, tokens)
                    region = sublime.Region(region.begin(), region.end() - removed)

                add_comment(view, edit, region, tokens)
            else:
                # Comment selection
                add_comment(view, edit, s, html_comment)


def remove_comments(view: sublime.View, edit: sublime.Edit, region: sublime.Region, tokens: dict):
    "Removes comment markers from given region. Returns amount of characters removed"
    text = view.substr(region)

    if text.startswith(tokens['start']) and text.endswith(tokens['end']):
        start_offset = region.begin() + len(tokens['start'])
        end_offset = region.end() - len(tokens['end'])

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
        return start_region.size() + end_region.size()

    return 0

def get_range_for_comment(view: sublime.View, pt: int):
    "Returns tag range for given text position, if possible"
    syntax_name = syntax.from_pos(view, pt)
    if syntax.is_css(syntax_name):
        m = emmet.match_css(utils.get_content(view), pt)
        if m:
            # TODO CSS might be an inline fragment of another document
            return sublime.Region(m.start, m.end)
    elif syntax.is_html(syntax_name):
        tag = emmet.get_tag_context(view, pt, syntax.is_xml(syntax_name))
        if tag:
            open_tag = tag.get('open')
            close_tag = tag.get('close')

            return open_tag.cover(close_tag) if close_tag else open_tag
    return None


def add_comment(view: sublime.View, edit: sublime.Edit, region: sublime.Region, tokens: dict):
    "Adds comments around given range"
    view.insert(edit, region.end(), ' ' + tokens['end'])
    view.insert(edit, region.begin(), tokens['start'] + ' ')


def get_comment_regions(view: sublime.View, region: sublime.Region, tokens: dict):
    "Finds comments inside given region and returns their regions"
    result = []
    text = view.substr(region)
    start = region.begin()
    offset = 0

    while True:
        c_start = text.find(tokens['start'], offset)
        if c_start != -1:
            offset = c_start + len(tokens['start'])

            # Find comment end
            c_end = text.find(tokens['end'], offset)
            if c_end != -1:
                offset = c_end + len(tokens['end'])
                result.append(sublime.Region(start + c_start, start + offset))
        else:
            break

    return result

def allow_emmet_comments(view: sublime.View):
    "Check if Emmet's Toggle Comment action can be applied at current view"
    if view.settings().get('emmet_comment'):
        selectors = view.settings().get('emmet_comment_scopes', [])
        caret = utils.get_caret(view)
        return syntax.matches_selector(view, caret, selectors)

    return False


class ToggleCommentListener(sublime_plugin.EventListener):
    def on_text_command(self, view, command_name, args):
        if command_name == 'toggle_comment' and allow_emmet_comments(view):
            return ('emmet_toggle_comment', None)
        return None
