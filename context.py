import sublime
import sublime_plugin
from .utils import get_caret

self_close = (
    'img', 'meta', 'link', 'br', 'base', 'hr', 'area', 'wbr', 'col', 'embed',
    'input', 'param', 'source', 'track'
)
"A list of self-closing HTML tags"

class TagContext:
    __slots__ = ('name', 'open', 'close')

    def __init__(self, name: str, open_region: sublime.Region, close_region=None):
        self.name = name
        self.open = open_region
        self.close = close_region

    def is_self_close(self):
        return self.close is None

def get_html_context(editor: sublime.View, pos: int) -> TagContext:
    # In ST3, `view.find_by_selector()` will merge adjacent regions.
    # For example, passing `entity.name.tag` selector will return a single
    # region for `<span></span>`. Since we can easily detect tag start, we’ll
    # use selector to get tag name and adjacent closing punctuation to distinct
    # regions and properly build document tree
    is_html = editor.match_selector(pos, 'text.html')
    tmp = sublime.Region(0, 0)
    pool = []
    stack = []
    regions = editor.find_by_selector('entity.name.tag, punctuation.definition.tag.end')
    pending = None

    for r in regions:
        val = editor.substr(r)
        if val in ('>', '/>'):
            # It’s a closing punctuator for open tag
            # NB: we know it’s open tag (with attributes) for sure, otherwise punctuation
            # will be a part of original region
            if pending is not None:
                tmp.a = pending.a + 1
                tmp.b = pending.b
                tag_name = editor.substr(tmp)
                pending.b = r.b

                is_self_close = val == '/>' or (is_html and tag_name in self_close)
                if is_self_close:
                    if region_contains(pending, pos):
                        return TagContext(tag_name, pending)
                else:
                    stack.append(alloc_item(pool, tag_name, pending))
                pending = None
        else:
            # It’s a tag name, get full tag beginning location
            r.a -= 1
            is_close = editor.substr(r.a) == '/'

            if is_close:
                r.a -= 1

            if val[-1] == '>':
                # We have full tag region here (tag without attributes)
                if is_close:
                    tag_name = val[0:-1]
                    open_tag = pop_tag_stack(stack, tag_name, pool)
                    if open_tag and open_tag['region'].begin() < pos < r.end():
                        return TagContext(tag_name, open_tag['region'], r)
                else:
                    is_self_close = val[-2] == '/'

                    if is_self_close:
                        tag_name = val[0:-2]
                    else:
                        tag_name = val[0:-1]
                        is_self_close = is_html and tag_name in self_close

                    if is_self_close:
                        if region_contains(r, pos):
                            return TagContext(tag_name, pending)
                    else:
                        stack.append(alloc_item(pool, tag_name, r))
            else:
                # Incomplete tag, wait for closing punctuation
                pending = r


def alloc_item(pool: list, name: str, region: sublime.Region) -> dict:
    item = pool.pop() if pool else {}
    item['name'] = name
    item['region'] = region
    return item


def release_item(pool: list, item: dict):
    pool.append(item)


def region_contains(region: sublime.Region, pt: int) -> bool:
    return region.begin() < pt < region.end()


def pop_tag_stack(stack: list, tag: str, pool):
    while stack:
        item = stack.pop()
        release_item(pool, item)
        if item['name'] == tag:
            return item


class EmmetGetContext(sublime_plugin.TextCommand):
    def run(self, edit):
        ctx = get_html_context(self.view, get_caret(self.view))
        if ctx:
            print('found ctx: %s, %s, %s' % (ctx.name, self.view.substr(ctx.open), self.view.substr(ctx.close) if ctx.close else '--'))
