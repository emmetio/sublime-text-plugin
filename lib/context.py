import sublime
from .utils import  get_content, attribute_value
from .config import get_config
from . import syntax
from ..emmet.config import Config
from ..emmet.html_matcher import attributes
from ..emmet.css_matcher import scan as scan_css, TokenType
from ..emmet.stylesheet import CSSAbbreviationScope

self_close = (
    'img', 'meta', 'link', 'br', 'base', 'hr', 'area', 'wbr', 'col', 'embed',
    'input', 'param', 'source', 'track'
)
"A list of self-closing HTML tags"

def get_activation_context(editor: sublime.View, pos: int) -> Config:
    """
    Detects and returns valid abbreviation activation context for given location
    in editor which can be used for abbreviation expanding.
    For example, in given HTML code:
    `<div title="Sample" style="">Hello world</div>`
    it’s not allowed to expand abbreviations inside `<div ...>` or `</div>`,
    yet it’s allowed inside `style` attribute and between tags.

    This method ensures that given `pos` is inside location allowed for expanding
    abbreviations and returns context data about it.

    Default implementation works for any editor since it uses own parsers for HTML
    and CSS but might be slow: if your editor supports low-level access to document
    parse tree or tokens, authors should override this method and provide alternative
    based on editor native features.
    """
    if editor.match_selector(pos, 'meta.attribute-with-value.style string'):
        # Inline CSS
        # TODO detect property value context
        return create_activation_context(editor, pos, {'name': CSSAbbreviationScope.Property}, True)

    syntax_name = syntax.from_pos(editor, pos)
    if syntax.is_css(syntax_name):
        ctx = get_css_context(editor, pos)
        if ctx:
            result = create_activation_context(editor, pos, ctx)
            if editor.match_selector(pos, 'meta.at-rule.media meta.group | meta.at-rule.supports meta.group'):
                result.options['stylesheet.after'] = ''
            return result

        return None

    if syntax.is_html(syntax_name):
        ctx = get_html_context(editor, pos)
        if syntax.is_jsx(syntax_name) and ctx is None:
            # No luck with context for JSX: but we can still use it
            return create_activation_context(editor, pos)

        return create_activation_context(editor, pos, ctx) if ctx is not None else None

    return create_activation_context(editor, pos)


def create_activation_context(editor: sublime.View, pos: int, context: dict = None, inline=False) -> Config:
    "Creates abbreviation activation context payload for given location in editor."
    config = get_config(editor, pos)
    config.context = context
    return config


def get_html_context(editor: sublime.View, pos: int) -> dict:
    """
    Get Emmet abbreviation context for given location in HTML editor
    Returns `None` if context is not valid
    """
    if editor.match_selector(pos, '(meta.tag | comment) - punctuation.definition.tag.begin'):
        # Do not allow abbreviations inside tags or comments
        return None

    # In ST3, `view.find_by_selector()` will merge adjacent regions.
    # For example, passing `entity.name.tag` selector will return a single
    # range for `<span></span>`. Since we can easily detect tag start, we’ll
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
                        return create_tag_context(editor, tag_name, pending)
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
                        return create_tag_context(editor, tag_name, open_tag['region'])
                else:
                    is_self_close = val[-2] == '/'

                    if is_self_close:
                        tag_name = val[0:-2]
                    else:
                        tag_name = val[0:-1]
                        is_self_close = is_html and tag_name in self_close

                    if is_self_close:
                        if region_contains(r, pos):
                            return create_tag_context(editor, tag_name, pending)
                    else:
                        stack.append(alloc_item(pool, tag_name, r))
            else:
                # Incomplete tag, wait for closing punctuation
                pending = r

    # Return empty dict, which means there’s no context but abbreviation is allowed
    return {}


def fast_get_css_context(editor: sublime.View, pos: int):
    "Get CSS context using native ST API, but might be less accurate than get_css_context()"
    # Check for edge case: typing abbreviation inside media expression,
    # e.g. `@media (|) { ... }`
    r = None
    text = ''
    sel_at_rule = 'meta.at-rule.media | meta.at-rule.supports'
    if editor.match_selector(pos, sel_at_rule):
        r = editor.expand_to_scope(pos, 'meta.group')
        if not r:
            start = pos
            while start > 0 and editor.match_selector(start, 'punctuation.definition.group'):
                start -= 1

            r = editor.extract_scope(start)

        prefix = '@media '
        text = '%s%s {}' % (prefix, editor.substr(r))
        return get_css_context_from_text(text, pos - r.a + len(prefix))
    else:
        r = get_matching_section(editor, pos)
        if r:
            text = editor.substr(r)

    if r:
        ctx = get_css_context_from_text(text, pos - r.a)
        return ctx

    # TODO check for side-effects, may introduce unwanted inline completions
    # a better solution is to use native ST snippets here
    # if editor.match_selector(pos, 'source - (meta | comment)'):
    #     # A global (root) scope
    #     return { 'name': CSSAbbreviationScope.Global }


def get_matching_section(view: sublime.View, pos: int):
    for r in get_section_regions(view):
        if r.contains(pos):
            return r


def get_section_regions(view: sublime.View):
    result = []
    regions = view.find_by_selector('meta.selector, meta.property-list')
    max_size = view.size()

    for r in regions:
        start = r.begin()
        end = r.end()

        # a region may start with whitespace
        while start < end and view.substr(start).isspace():
            start += 1

        # Find terminating
        while end > max_size and view.substr(end) != '}':
            end += 1

        result.append(sublime.Region(start, end))

    return result


def search_css_context(content: str, pos: int):
    "Searches for Emmet CSS context in content at given location"
    state = {
        'current': None,
        'pool': [],
        'stack': []
    }

    def scan_callback(token_type: str, start: int, end: int, delimiter: int):
        if start >= pos:
            # Token behind specified location, stop parsing
            return False

        if start < pos <= end:
            # Direct hit on token
            state['current'] = {
                'type': token_type,
                'region': sublime.Region(start, end)
            }
            return False

        if token_type in (TokenType.Selector, TokenType.PropertyName):
            state['stack'].append(alloc_css_item(state['pool'], token_type, start, end))
        elif token_type in (TokenType.PropertyValue, TokenType.BlockEnd) and state['stack']:
            release_css_item(state['pool'], state['stack'].pop())

    scan_css(content, scan_callback)

    return state


def text_substr(text: str, r: sublime.Region) -> str:
    return text[r.begin():r.end()]


def get_css_context_from_text(text: str, pos: int):
    state = search_css_context(text, pos)

    # CSS abbreviations can be activated only when a character is entered, e.g.
    # it should be either property name or value.
    # In come cases, a first character of selector should also be considered
    # as activation context
    cur = state['current']
    stack = state['stack']
    if not cur:
        return None

    # Check for edge case: typing abbreviation inside media expression,
    # e.g. `@media (|) { ... }`
    if cur['type'] == TokenType.Selector:
        value = text_substr(text, cur['region'])
        if value.startswith('@media') and in_media_expression(value, pos - cur['region'].begin()):
            return {'name': CSSAbbreviationScope.Property}

    if cur['type'] in (TokenType.PropertyName, TokenType.PropertyValue) or \
        is_typing_before_selector(text, pos, cur):

        parent = stack[-1] if stack else None
        scope = CSSAbbreviationScope.Global

        if cur:
            if cur['type'] == TokenType.PropertyValue:
                prefix = text[pos - 1]
                value = text_substr(text, cur['region'])
                allowed_prefixes = '!#'
                if prefix not in allowed_prefixes and value[0] not in allowed_prefixes:
                    # For value scope, allow color abbreviations only and important
                    # modifiers. For all other cases, delegate to native completions
                    return None
                if parent:
                    value = text_substr(text, parent['region'])
            elif cur['type'] in (TokenType.Selector, TokenType.PropertyName) and not parent:
                scope = CSSAbbreviationScope.Section

        return {'name': scope}

def get_css_context(editor: sublime.View, pos: int):
    if syntax.doc_syntax(editor) == 'css':
        return fast_get_css_context(editor, pos)

    return get_css_context_from_text(get_content(editor), pos)


def is_typing_before_selector(text: str, pos: int, ctx: dict) -> bool:
    """
    Handle edge case: start typing abbreviation before selector. In this case,
    entered character becomes part of selector
    Activate only if it’s a nested section and it’s a first character of selector
    """
    if ctx and ctx['type'] == TokenType.Selector and ctx['region'].begin() == pos - 1:
        # Typing abbreviation before selector is tricky one:
        # ensure it’s on its own line
        line = text_substr(text, ctx['region']).splitlines()[0]
        return len(line.strip()) == 1

    return False


def alloc_item(pool: list, name: str, region: sublime.Region) -> dict:
    item = pool.pop() if pool else {}
    item['name'] = name
    item['region'] = region
    return item


def release_item(pool: list, item: dict):
    pool.append(item)


def pop_tag_stack(stack: list, tag: str, pool):
    while stack:
        item = stack.pop()
        release_item(pool, item)
        if item['name'] == tag:
            return item


def alloc_css_item(pool: list, token_type: str, start: int, end: int):
    if pool:
        item = pool.pop()
        item['type'] = token_type
        item['region'].a = start
        item['region'].b = end
    else:
        item = {
            'type': token_type,
            'region': sublime.Region(start, end)
        }

    return item

def release_css_item(pool: list, item: dict):
    if item is not None:
        pool.append(item)


def parse_html_attributes(editor: sublime.View, name: str, open_tag: sublime.Region) -> dict:
    "Parses attributes of given open tag"
    attrs = {}
    for attr in attributes(editor.substr(open_tag), name):
        attrs[attr.name] = attribute_value(attr)

    return attrs


def create_tag_context(editor: sublime.View, name: str, open_tag: sublime.Region) -> dict:
    "Factory method for creating tag context"
    return {
        'name': name,
        'attributes': parse_html_attributes(editor, name, open_tag)
    }


def region_contains(region: sublime.Region, pt: int) -> bool:
    return region.begin() < pt < region.end()


def in_media_expression(value: str, pos: int) -> bool:
    "Check if given `pos` is inside expresion of @media rule"
    stack = 0
    i = 0
    while i < len(value):
        if i == pos:
            return stack > 0

        if value[i] == '(':
            stack += 1
        elif value[i] == ')':
            stack -= 1

        i += 1

    return False
