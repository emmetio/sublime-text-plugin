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

known_tags = [
	'a', 'abbr', 'acronym', 'address', 'applet', 'area', 'article', 'aside', 'audio',
	'b', 'base', 'basefont', 'bdi', 'bdo', 'bgsound', 'big', 'blink', 'blockquote', 'body', 'br', 'button',
	'canvas', 'caption', 'center', 'cite', 'code', 'col', 'colgroup', 'command', 'content',
	'data', 'datalist', 'dd', 'del', 'details', 'dfn', 'dialog', 'dir', 'div', 'dl', 'dt',
	'element', 'em', 'embed',
	'fieldset', 'figcaption', 'figure', 'font', 'footer', 'form', 'frame', 'frameset',
	'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'head', 'header', 'hgroup', 'hr', 'html',
	'i', 'iframe', 'image', 'img', 'input', 'ins', 'isindex',
	'kbd', 'keygen',
	'label', 'legend', 'li', 'link', 'listing',
	'main', 'main', 'map', 'mark', 'marquee', 'menu', 'menuitem', 'meta', 'meter', 'multicol',
	'nav', 'nextid', 'nobr', 'noembed', 'noframes', 'noscript',
	'object', 'ol', 'optgroup', 'option', 'output',
	'p', 'param', 'picture', 'plaintext', 'pre', 'progress',
	'q',
	'rb', 'rp', 'rt', 'rtc', 'ruby',
	's', 'samp', 'script', 'section', 'select', 'shadow', 'slot', 'small', 'source', 'spacer', 'span', 'strike', 'strong', 'style', 'sub', 'summary', 'sup',
	'table', 'tbody', 'td', 'template', 'textarea', 'tfoot', 'th', 'thead', 'time', 'title', 'tr', 'track', 'tt', 'u', 'ul', 'var', 'video', 'wbr', 'xmp'
]

pairs_end = {}
for k, v in pairs.items():
    pairs_end[v] = k


NON_SPACE_LEFT = 1
NON_SPACE_RIGHT = 2

def narrow_to_non_space(view: sublime.View, region: sublime.Region, direction = NON_SPACE_LEFT | NON_SPACE_RIGHT) -> sublime.Region:
    "Returns copy of region which starts and ends at non-space character"
    begin = region.begin()
    end = region.end()

    if direction & NON_SPACE_LEFT:
        while begin < end:
            if not view.substr(begin).isspace():
                break
            begin += 1

    if (direction & NON_SPACE_RIGHT):
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
        'contents': preprocess_snippet(snippet)
    })

def multicursor_replace_with_snippet(view: sublime.View, edit: sublime.Edit, payload: list):
    "Replaces multiple regions with snippets, maintaining final caret positions"
    sels = []
    doc_size = view.size()
    for region, snippet in reversed(list(payload)):
        replace_with_snippet(view, edit, region, snippet)

        # Update locations of existing regions
        next_size = view.size()
        delta = next_size - doc_size
        for r in sels:
            r.a += delta
            r.b += delta

        doc_size = next_size
        sels += list(view.sel())

    s = view.sel()
    s.clear()
    s.add_all(sels)



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


def preprocess_snippet(text: str) -> str:
    "Preprocess given text before inserting into document: escapes $ charaters where required"
    result = ''
    i = 0
    l = len(text)

    while i < l:
        ch = text[i]
        next_ch = text[i + 1] if i + 1 < l else ''
        i += 1
        if ch == '\\':
            # Escape sequence
            result += ch + next_ch
            i += 1
        elif ch == '$' and next_ch != '{':
            # Non-field $ character
            result += '\\' + ch
        else:
            result += ch

    return result


