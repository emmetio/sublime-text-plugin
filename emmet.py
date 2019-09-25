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

xml_syntaxes = ['xml', 'xsl']
html_syntaxes = ['html']

def _get_js_code():
    base_path = os.path.abspath(os.path.dirname(__file__))
    with open(os.path.join(base_path, 'emmet.js'), encoding='UTF-8') as f:
        src = f.read()

    src += "\nvar {expand, extract, validate, match} = emmet;"
    return src


def _compile(code):
    context = quickjs.Context()
    context.eval(code)
    expand = context.get('expand')
    extract = context.get('extract')
    validate = context.get('validate')
    match = context.get('match')
    return context, expand, extract, validate, match


threadpool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
lock = threading.Lock()

future = threadpool.submit(_compile, _get_js_code())
concurrent.futures.wait([future])
context, js_expand, js_extract, js_validate, js_match = future.result()

def expand(abbr, options=None):
    "Expands given abbreviation into code snippet"
    return call_js(js_expand, abbr, options)


def extract(line, pos, options=None):
    "Extracts abbreviation from given line of source code"
    return call_js(js_extract, line, pos, options)


def validate(abbr, options=None):
    """
    Validates given abbreviation: check if it can be properly expanded and detects
    if it's a simple abbreviation (looks like a regular word)
    """
    return call_js(js_validate, abbr, options)


def match(code, pos, options=None):
    """
    Finds matching tag pair for given `pos` in `code`
    """
    return call_js(js_match, code, pos, options)


def get_tag_context(view, pt, xml=False):
    "Returns matched HTML/XML tag for given point in view"
    content = view.substr(sublime.Region(0, view.size()))
    tag = match(content, pt, { 'xml': xml })
    if tag:
        ctx = {
            'name': tag['name'],
            'attributes': {}
        }

        for attr in tag['attributes']:
            name = attr['name']
            value = attr['value']
            # unquote value
            if value and value[0] == '"' or value[0] == "'":
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
        elif syntax_info['syntax'] in xml_syntaxes or syntax_info['syntax'] in html_syntaxes:
            syntax_info['context'] = get_tag_context(view, pt, syntax_info['syntax'] in xml_syntaxes)

    syntax_info['inline'] = syntax.is_inline(view, pt)
    return syntax_info

def abbreviation_from_line(view, pt):
    "Extracts abbreviation from line that matches given point in view"
    line_region = view.line(pt)
    line_start = line_region.begin()
    line = view.substr(line_region)
    opt = get_options(view, pt)

    if opt['type'] == 'stylesheet':
        opt['lookAhead'] = False

    abbr_data = extract(line, pt - line_start, opt)

    if abbr_data:
        start = line_start + abbr_data['start']
        end = line_start + abbr_data['end']
        return start, end, opt


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
