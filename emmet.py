import re
import sublime
from .py_emmet import expand as expand_abbreviation, extract, Config, \
    stylesheet_abbreviation, markup_abbreviation, ScannerException
from .py_emmet.html_matcher import match, balanced_inward, balanced_outward
from .py_emmet.css_matcher import match as css_match, \
    balanced_inward as css_balanced_inward \
    balanced_outward as css_balanced_outward
from . import syntax

re_simple = re.compile(r'^([\w!-]+)\.?$')
known_tags = (
    'a', 'abbr', 'address', 'area', 'article', 'aside', 'audio',
    'b', 'base', 'bdi', 'bdo', 'blockquote', 'body', 'br', 'button',
    'canvas', 'caption', 'cite', 'code', 'col', 'colgroup', 'content',
    'data', 'datalist', 'dd', 'del', 'details', 'dfn', 'dialog', 'div', 'dl', 'dt',
    'em', 'embed',
    'fieldset', 'figcaption', 'figure', 'footer', 'form',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'head', 'header', 'hr', 'html',
    'i', 'iframe', 'img', 'input', 'ins',
    'kbd', 'keygen',
    'label', 'legend', 'li', 'link',
    'main', 'map', 'mark', 'menu', 'menuitem', 'meta', 'meter',
    'nav', 'noscript',
    'object', 'ol', 'optgroup', 'option', 'output',
    'p', 'param', 'picture', 'pre', 'progress',
    'q',
    'rp', 'rt', 'rtc', 'ruby',
    's', 'samp', 'script', 'section', 'select', 'shadow', 'slot', 'small', 'source', 'span', 'strong', 'style', 'sub', 'summary', 'sup',
    'table', 'tbody', 'td', 'template', 'textarea', 'tfoot', 'th', 'thead', 'time', 'title', 'tr', 'track',
    'u', 'ul', 'var', 'video', 'wbr'
)


def field(index: int, placeholder: str, **kwargs):
    "Produces tabstops for editor"
    if placeholder:
        return '${%d:%s}' % (index, placeholder)
    return '${%d}' % index


def field_preview(index: int, placeholder: str, **kwargs):
    return placeholder


def escape_text(text: str, **kwargs):
    "Escapes all `$` in plain text for snippet output"
    return re.sub(r'\$', '\\$', text)


def expand(abbr, config: dict=None):
    "Expands given abbreviation into code snippet"
    is_preview = config and config.get('preview')
    opt = {}
    output_opt = {
        'output.field': field_preview if is_preview else field,
        'output.text': escape_text,
        'output.format': not config or not config.get('inline'),
    }

    if config:
        opt.update(options)
        if 'options' in config:
            output_opt.update(config.get('options'))
    opt['options'] = output_opt

    return expand_abbreviation(abbr, opt)


def validate(abbr, config=None):
    """
    Validates given abbreviation: check if it can be properly expanded and detects
    if it's a simple abbreviation (looks like a regular word)
    """
    resolved = Config(config)

    try:
        if resolved.type == 'stylesheet':
            stylesheet_abbreviation(abbr, resolved)
        else:
            markup_abbreviation(abbr, resolved)

        m = re_simple.match(abbr)
        return {
            'valid': True,
            'simple': abbr == '.' or bool(m),
            'matched': m.group(1) in known_tags or m.group(1) in config.snippets if m else False
        }

    except ScannerException as err:
        return {
            'valid': False,
            'error': err.message,
            'pos': err.pos,
            'snippet': '%s^' % ('-' % err.pos,) if err.pos is not None else ''
        }

    return {
        'valid': False,
        'error': '',
        'pos': -1,
        'snippet': ''
    }


def balance(code: str, pos: int, direction: str, xml=False):
    "Returns list of tags for balancing for given code"
    if direction == 'inward':
        return balanced_inward(code, pos, options)
    return balanced_outward(code, pos, options)


def balance_css(code: str, pos: int, direction: str):
    "Returns list of selector/property ranges for balancing for given code"
    if direction == 'inward':
        return css_balanced_inward(code, pos)
    return css_balanced_outward(code, pos)


def select_item(code, pos, is_css=False, is_previous=False):
    "Returns model for selecting next/previous item"
    fn = 'selectItemCSS' if is_css else 'selectItemHTML'
    model = call_js(fn, code, pos, is_previous)
    if model:
        model['ranges'] = [to_region(r) for r in model['ranges']]
        return model


def tag(code, pos, options=None):
    "Find tag that matches given `pos` in `code`"
    return call_js('getOpenTag', code, pos, options)


def css_section(code, pos, properties=False):
    "Find enclosing CSS section and returns its ranges with (optionally) parsed properties"
    section = call_js('getCSSSection', code, pos, properties)
    if section and section.get('properties'):
        # Convert property ranges to Sublime Regions
        for p in section.get('properties', []):
            p['name'] = to_region(p['name'])
            p['value'] = to_region(p['value'])
            p['valueTokens'] = [to_region(v) for v in p['valueTokens']]

    return section

def evaluate_math(line, pos, options=None):
    "Finds and evaluates math expression at given position in line"
    return call_js('math', line, pos, options)


def get_tag_context(view, pt, xml=None):
    "Returns matched HTML/XML tag for given point in view"
    content = view.substr(sublime.Region(0, view.size()))
    if xml is None:
        # Autodetect XML dialect
        syntax_name = syntax.from_pos(view, pt)
        xml = syntax.is_xml(syntax_name)

    tag = match(content, pt, { 'xml': xml })
    if tag:
        open_tag = tag.get('open')
        close_tag = tag.get('close')
        ctx = {
            'name': tag.get('name'),
            'attributes': {},
            'open': to_region(open_tag),
        }

        if close_tag:
            ctx['close'] = to_region(close_tag)

        for attr in tag['attributes']:
            name = attr['name']
            value = attr.get('value')
            # unquote value
            if value and (value[0] == '"' or value[0] == "'"):
                value = value.strip(value[0])
            ctx['attributes'][name] = value

        return ctx


def get_css_context(view: sublime.View, pt: int):
    "Returns context CSS property name, if any"
    if view.match_selector(pt, 'meta.property-value'):
        # Walk back until we find property name
        scope_range = view.extract_scope(pt)
        ctx_pos = scope_range.begin() - 1
        while ctx_pos >= 0 and not view.match_selector(ctx_pos, 'section.property-list') \
            and not view.match_selector(ctx_pos, 'meta.selector'):
            scope_range = view.extract_scope(ctx_pos)
            if view.match_selector(ctx_pos, 'meta.property-name'):
                return { 'name': view.substr(scope_range) }
            ctx_pos = scope_range.begin() - 1


def get_options(view, pt, with_context=False):
    "Returns Emmet options for given character location in view"
    syntax_info = syntax.info(view, pt, 'html')

    # Get element context
    if with_context:
        if syntax_info['type'] == 'stylesheet':
            syntax_info['context'] = get_css_context(view, pt)
        elif syntax.is_html(syntax_info['syntax']):
            syntax_info['context'] = get_tag_context(view, pt, syntax.is_xml(syntax_info['syntax']))

    syntax_info['inline'] = syntax.is_inline(view, pt)
    return syntax_info

def extract_abbreviation(view, loc):
    """
    Extracts abbreviation from given location in view. Locations could be either
    `int` (a character location in view) or `list`/`tuple`/`sublime.Region`.
    """
    pt = -1
    region = None

    if isinstance(loc, (list, tuple)):
        loc = to_region(loc)

    if isinstance(loc, int):
        # Character location is passed, extract from line
        pt = loc
        region = view.line(pt)
    elif isinstance(loc, sublime.Region):
        # Extract from given range
        pt = loc.end()
        region = loc
    else:
        return None

    text = view.substr(region)
    begin = region.begin()
    opt = get_options(view, pt)

    if opt['type'] == 'stylesheet':
        # No look-ahead for stylesheets: they do not support brackets syntax
        # and enabled look-ahead produces false matches
        opt['lookAhead'] = False

    if opt['syntax'] == 'jsx':
        opt['prefix'] = view.settings().get('emmet_jsx_prefix', None)

    abbr_data = extract(text, pt - begin, opt)

    if abbr_data:
        abbr_data['start'] += begin
        abbr_data['end'] += begin
        abbr_data['location'] += begin
        return abbr_data, opt


def to_region(rng):
    return sublime.Region(rng[0], rng[1])
