import re
import os.path
import urllib.request
import sublime
from ..emmet.html_matcher import AttributeToken
from ..emmet.action_utils import CSSProperty

pairs = {
    '{': '}',
    '[': ']',
    '(': ')'
}

pairs_end = {}
for k, v in pairs.items():
    pairs_end[v] = k


def narrow_to_non_space(view: sublime.View, region: sublime.Region) -> sublime.Region:
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


def replace_with_snippet(view: sublime.View, edit: sublime.Edit, region: sublime.Region, snippet: str):
    "Replaces given region view with snippet contents"
    sel = view.sel()
    sel.clear()
    sel.add(sublime.Region(region.begin(), region.begin()))
    view.replace(edit, region, '')
    view.run_command('insert_snippet', {
        'contents': snippet
    })


def get_caret(view: sublime.View) -> int:
    "Returns current caret position for single selection"
    sel = view.sel()
    return sel[0].begin() if len(sel) else 0


def get_content(view: sublime.View) -> str:
    "Returns contents of given view"
    return view.substr(sublime.Region(0, view.size()))


def go_to_pos(view: sublime.View, pos: int):
    "Scroll editor to given position in code"
    sel = view.sel()
    sel.clear()
    sel.add(sublime.Region(pos, pos))
    view.show(pos)


def is_url(file_path: str):
    "Check if given file path is an URL"
    return re.match(r'^\w+?://', file_path)


def read_file(file_path: str, size=-1):
    "Reads content of given file. If `size` if given, reads up to `size` bytes"
    if is_url(file_path):
        with urllib.request.urlopen(file_path, timeout=5) as req:
            return req.read(size)

    with open(file_path, 'rb') as fp:
        return fp.read(size)


def locate_file(editor_file: str, file_name: str):
    """
    Locate `file_name` file relative to `editor_file`.
    If `file_name` is absolute, will traverse up to folder structure looking for
    matching file.
    """
    previous_parent = ''
    parent = os.path.dirname(editor_file)
    while parent and os.path.exists(parent) and parent != previous_parent:
        tmp = create_path(parent, file_name)
        if os.path.exists(tmp):
            return tmp

        previous_parent = parent
        parent = os.path.dirname(parent)


def create_path(parent: str, file_name: str):
    """
    Creates absolute path by concatenating `parent` and `file_name`.
    If `parent` points to file, its parent directory is used
    """
    result = ''
    file_name = file_name.lstrip('/')

    if os.path.exists(parent):
        if os.path.isfile(parent):
            parent = os.path.dirname(parent)

        result = os.path.normpath(os.path.join(parent, file_name))

    return result

def attribute_value(attr: AttributeToken):
    "Returns value of given attribute, parsed by Emmet HTML matcher"
    value = attr.value
    if is_quoted(value):
        return value[1:-1]
    return value


def patch_attribute(attr: AttributeToken, value: str, name: str=None):
    "Returns patched version of given HTML attribute, parsed by Emmet HTML matcher"
    if name is None:
        name = attr.name

    before = ''
    after = ''

    if attr.value is not None:
        if is_quoted(attr.value):
            # Quoted value or React-like expression
            before = attr.value[0]
            after = attr.value[-1]
    else:
        # Attribute without value (boolean)
        before = after = '"'

    return '%s=%s%s%s' % (name, before, value, after)


def patch_property(view: sublime.View, prop: CSSProperty, value: str, name=None):
    "Returns patched version of given CSS property, parsed by Emmet CSS matcher"
    if name is None:
        name = view.substr(prop.name)

    before = view.substr(sublime.Region(prop.before, prop.name.begin()))
    between = view.substr(sublime.Region(prop.name.end(), prop.value.begin()))
    after = view.substr(sublime.Region(prop.value.end(), prop.after))

    return ''.join((before, name, between, value, after))


def is_quoted(value: str):
    "Check if given value is either quoted or written as expression"
    return value and ((value[0] in '"\'' and value[0] == value[-1]) or \
        (value[0] == '{' and value[-1] == '}'))


def attribute_region(attr: AttributeToken):
    "Returns region that covers entire attribute"
    end = attr.value_end if attr.value is not None else attr.name_end
    return sublime.Region(attr.name_start, end)


def has_new_line(text: str) -> bool:
    "Check if given text contains newline character"
    return '\n' in text or '\r' in text


def to_region(rng: list) -> sublime.Region:
    "Converts given list range to Sublime region"
    return sublime.Region(rng[0], rng[1])


def escape_snippet(text: str) -> str:
    "Escapes given text for snippet insertion"
    return text.replace('$', '\\$')
