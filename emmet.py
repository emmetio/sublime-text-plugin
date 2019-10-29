import sublime
import concurrent.futures
import threading
import json
import os.path
import re
from . import syntax

if sublime.platform() == 'osx':
    from .osx import _quickjs as quickjs
elif sublime.platform() == 'window':
    from .win_x64 import _quickjs as quickjs
else:
    raise RuntimeError('Platform %s (%s) is not currently supported' % (sublime.platform(), sublime.arch()))


def _get_js_code():
    base_path = os.path.abspath(os.path.dirname(__file__))
    with open(os.path.join(base_path, 'emmet.js'), encoding='UTF-8') as f:
        src = f.read()

    src += "\nvar {expand, extract, validate, matchHTML, matchCSS, balance, balanceCSS, math, selectItemHTML, selectItemCSS, getOpenTag} = emmet;"
    return src


def _compile(code):
    context = quickjs.Context()
    context.eval(code)
    return context


threadpool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
lock = threading.Lock()

future = threadpool.submit(_compile, _get_js_code())
concurrent.futures.wait([future])
context = future.result()

def expand(abbr, options=None):
    "Expands given abbreviation into code snippet"
    return call_js('expand', abbr, options)


def extract(line, pos, options=None):
    "Extracts abbreviation from given line of source code"
    return call_js('extract', line, pos, options)


def validate(abbr, options=None):
    """
    Validates given abbreviation: check if it can be properly expanded and detects
    if it's a simple abbreviation (looks like a regular word)
    """
    return call_js('validate', abbr, options)


def match(code, pos, options=None):
    "Finds matching tag pair for given `pos` in `code`"
    return call_js('matchHTML', code, pos, options)


def match_css(code, pos, options=None):
    "Finds matching selector or property for given `pos` in `code`"
    return call_js('matchCSS', code, pos, options)


def balance(code, pos, direction, xml=False):
    "Returns list of tags for balancing for given code"
    return call_js('balance', code, pos, direction, { 'xml': xml })


def balance_css(code, pos, direction):
    "Returns list of selector/property ranges for balancing for given code"
    return call_js('balanceCSS', code, pos, direction)


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

######################################
## QuickJS Runtime
## https://github.com/PetterS/quickjs
######################################


def call_js(fn, *args):
    with lock:
        future = threadpool.submit(_call_js, fn, *args)
        concurrent.futures.wait([future])
        return future.result()


def _call_js(fn, *args, run_gc=True):
    try:
        if isinstance(fn, str):
            fn = context.get(fn)
        result = fn(*[convert_arg(a) for a in args])
        if isinstance(result, quickjs.Object):
            result = json.loads(result.json())
        return result
    finally:
        if run_gc:
            context.gc()


def convert_arg(arg):
    if isinstance(arg, (type(None), str, bool, float, int)):
        return arg
    else:
        # More complex objects are passed through JSON.
        return context.eval("(" + json.dumps(arg) + ")")
