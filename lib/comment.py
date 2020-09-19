import sublime
from . import emmet_sublime as emmet
from . import syntax
from .utils import get_content, get_caret
from ..emmet.css_matcher import match as match_css

html_comment = {
    'start': '<!--',
    'end': '-->'
}

css_comment = {
    'start': '/*',
    'end': '*/'
}

comment_selector = 'comment'
embedded_style = 'source.css.embedded | source.less.embedded | source.scss.embedded | source.sass.embedded | source.sss.embedded'

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
        offset = 0
        inner_region = None
        if view.match_selector(pt, embedded_style):
            # Looks like embedded CSS, find matching region
            for r in view.find_by_selector(embedded_style):
                if r.contains(pt):
                    inner_region = r
                    offset = r.begin()
                    break


        content = view.substr(inner_region) if inner_region else get_content(view)
        m = match_css(content, pt - offset)
        if m:
            return sublime.Region(m.start + offset, m.end + offset)
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
    if emmet.get_settings('toggle_comment'):
        selectors = emmet.get_settings('comment_scopes', [])
        caret = get_caret(view)
        return syntax.matches_selector(view, caret, selectors)

    return False
