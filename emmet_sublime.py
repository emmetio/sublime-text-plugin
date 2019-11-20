import re
import sublime
from .emmet import expand as expand_abbreviation, extract, Config, \
    stylesheet_abbreviation, markup_abbreviation, ScannerException
from .emmet.token_scanner import TokenScannerException
from .emmet.html_matcher import match, balanced_inward, balanced_outward
from .emmet.css_matcher import match as match_css, \
    balanced_inward as css_balanced_inward, \
    balanced_outward as css_balanced_outward
from .emmet.action_utils import select_item_css, select_item_html, \
    get_open_tag as tag, get_css_section, SelectItemModel, CSSSection
from .emmet.math_expression import evaluate, extract as extract_math
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
    "Produces tabstops for abbreviation preview"
    return placeholder


def escape_text(text: str, **kwargs):
    "Escapes all `$` in plain text for snippet output"
    return re.sub(r'\$', '\\$', text)


def expand(abbr: str, config: dict=None):
    "Expands given abbreviation into code snippet"
    is_preview = config and config.get('preview', False)
    opt = {}
    output_opt = {
        'output.field': field_preview if is_preview else field,
        'output.text': escape_text,
        'output.format': not config or not config.get('inline'),
    }

    if config:
        opt.update(config)
        if 'options' in config:
            output_opt.update(config.get('options'))
    opt['options'] = output_opt

    view = sublime.active_window().active_view()
    if view:
        global_config = view.settings().get('emmet_config')

    return expand_abbreviation(abbr, opt, global_config)


def validate(abbr: str, config: dict=None):
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
            'abbr': abbr,
            'valid': True,
            'simple': abbr == '.' or bool(m),
            'matched': m.group(1) in known_tags or m.group(1) in resolved.snippets if m else False
        }

    except (ScannerException, TokenScannerException) as err:
        return {
            'abbr': abbr,
            'valid': False,
            'error': err.message,
            'pos': err.pos,
            'snippet': '%s^' % ('-' * err.pos,) if err.pos is not None else ''
        }

    return {
        'abbr': abbr,
        'valid': False,
        'error': '',
        'pos': -1,
        'snippet': ''
    }


def balance(code: str, pos: int, direction: str, xml=False) -> list:
    "Returns list of tags for balancing for given code"
    options = { 'xml': xml }
    if direction == 'inward':
        return balanced_inward(code, pos, options)
    return balanced_outward(code, pos, options)


def balance_css(code: str, pos: int, direction: str) -> list:
    "Returns list of selector/property ranges for balancing for given code"
    if direction == 'inward':
        return css_balanced_inward(code, pos)
    return css_balanced_outward(code, pos)


def select_item(code: str, pos: int, is_css=False, is_previous=False) -> SelectItemModel:
    "Returns model for selecting next/previous item"
    if is_css:
        model = select_item_css(code, pos, is_previous)
    else:
        model = select_item_html(code, pos, is_previous)
    if model:
        model.ranges = [to_region(r) for r in model.ranges]
    return model


def css_section(code: str, pos: int, properties=False) -> CSSSection:
    "Find enclosing CSS section and returns its ranges with (optionally) parsed properties"
    section = get_css_section(code, pos, properties)
    if section and section.properties:
        # Convert property ranges to Sublime Regions
        for p in section.properties:
            p.name = to_region(p.name)
            p.value = to_region(p.value)
            p.value_tokens = [to_region(v) for v in p.value_tokens]

    return section

def evaluate_math(code: str, pos: int, options=None):
    "Finds and evaluates math expression at given position in line"
    expr = extract_math(code, pos, options)
    if expr:
        try:
            start, end = expr
            result = evaluate(code[start:end])
            return {
                'start': start,
                'end': end,
                'result': result,
                'snippet': ('%.4f' % result).rstrip('0').rstrip('.')
            }
        except:
            pass


def get_tag_context(view: sublime.View, pt: int, xml=None) -> dict:
    "Returns matched HTML/XML tag for given point in view"
    content = view.substr(sublime.Region(0, view.size()))
    if xml is None:
        # Autodetect XML dialect
        syntax_name = syntax.from_pos(view, pt)
        xml = syntax.is_xml(syntax_name)

    matched_tag = match(content, pt, { 'xml': xml })
    if matched_tag:
        open_tag = matched_tag.open
        close_tag = matched_tag.close
        ctx = {
            'name': matched_tag.name,
            'attributes': {},
            'open': to_region(open_tag),
        }

        if close_tag:
            ctx['close'] = to_region(close_tag)

        for attr in matched_tag.attributes:
            name = attr.name
            value = attr.value
            # unquote value
            if value and (value[0] == '"' or value[0] == "'"):
                value = value.strip(value[0])
            ctx['attributes'][name] = value

        return ctx

    return None


def get_css_context(view: sublime.View, pt: int) -> dict:
    "Returns context CSS property name, if any"
    if view.match_selector(pt, 'meta.property-value'):
        # Walk back until we find property name
        scope_range = view.extract_scope(pt)
        ctx_pos = scope_range.begin() - 1
        while ctx_pos >= 0 and not view.match_selector(ctx_pos, 'section.property-list') \
            and not view.match_selector(ctx_pos, 'meta.selector'):
            scope_range = view.extract_scope(ctx_pos)
            if view.match_selector(ctx_pos, 'meta.property-name'):
                return {
                    'name': view.substr(scope_range)
                }
            ctx_pos = scope_range.begin() - 1
    return None


def get_options(view: sublime.View, pt: int, with_context=False) -> dict:
    "Returns Emmet options for given character location in view"
    config = syntax.info(view, pt, 'html')

    # Get element context
    if with_context:
        if config['type'] == 'stylesheet':
            config['context'] = get_css_context(view, pt)
        elif syntax.is_html(config['syntax']):
            config['context'] = get_tag_context(view, pt, syntax.is_xml(config['syntax']))

    config['inline'] = syntax.is_inline(view, pt)
    return config

def extract_abbreviation(view: sublime.View, loc: int, opt: dict=None):
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

    if opt is None:
        opt = get_options(view, pt)

    if opt['type'] == 'stylesheet':
        # No look-ahead for stylesheets: they do not support brackets syntax
        # and enabled look-ahead produces false matches
        opt['lookAhead'] = False

    if opt['syntax'] == 'jsx':
        opt['prefix'] = view.settings().get('emmet_jsx_prefix', None)

    abbr_data = extract(text, pt - begin, opt)

    if abbr_data:
        abbr_data.start += begin
        abbr_data.end += begin
        abbr_data.location += begin
        return abbr_data, opt

    return None


def to_region(rng: list) -> sublime.Region:
    "Converts given list range to Sublime region"
    return sublime.Region(rng[0], rng[1])
