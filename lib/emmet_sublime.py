import re
import sublime
from ..emmet import expand as expand_abbreviation, extract, Config
from ..emmet.html_matcher import match, balanced_inward, balanced_outward
from ..emmet.css_matcher import balanced_inward as css_balanced_inward, \
    balanced_outward as css_balanced_outward
from ..emmet.action_utils import select_item_css, select_item_html, \
    get_css_section, SelectItemModel, CSSSection
from ..emmet.math_expression import evaluate, extract as extract_math
from . import syntax
from .config import get_settings, get_config
from .utils import to_region

JSX_PREFIX = '<'


def escape_text(text: str, **kwargs):
    "Escapes all `$` in plain text for snippet output"
    return re.sub(r'\$', '\\$', text)


def expand(abbr: str, config: dict):
    return expand_abbreviation(abbr, config, get_settings('config'))


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
    ctx = None
    content = view.substr(sublime.Region(0, view.size()))

    if xml is None:
        # Autodetect XML dialect
        syntax_name = syntax.from_pos(view, pt)
        xml = syntax.is_xml(syntax_name)

    matched_tag = match(content, pt, {'xml': xml})
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


def extract_abbreviation(view: sublime.View, loc: int, config: Config = None):
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
    abbr_pos = pt - begin

    if config is None:
        config = get_config(view, pt)

    abbr_data = extract(text, abbr_pos, {
        'type': config.type,
        # No look-ahead for stylesheets: they do not support brackets syntax
        # and enabled look-ahead produces false matches
        'lookAhead': config.type != 'stylesheet',
        'prefix': JSX_PREFIX if syntax.is_jsx(config.syntax) else None
    })

    if not abbr_data and syntax.is_jsx(config.syntax):
        # Try JSX without prefix
        abbr_data = extract(text, abbr_pos, {
            'type': config.type,
            'lookAhead': config.type != 'stylesheet',
        })

    if abbr_data:
        abbr_data.start += begin
        abbr_data.end += begin
        abbr_data.location += begin
        return abbr_data

    return None
