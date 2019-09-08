import concurrent.futures
import threading
import json
import os.path
import re
import quickjs

re_string_scope = re.compile(r'\bstring\b')
re_source_scope = re.compile(r'\bsource\.([\w\-]+)')

markup_syntaxes = ['html', 'xml', 'xsl', 'jsx', 'haml', 'jade', 'pug', 'slim']
stylesheet_syntaxes = ['css', 'scss', 'sass', 'less', 'sss', 'stylus', 'postcss']


def _get_js_code():
    base_path = os.path.abspath(os.path.dirname(__file__))
    with open(os.path.join(base_path, 'emmet.js'), encoding='UTF-8') as f:
        src = f.read()

    src += "\nvar {expand, extract, validate} = emmet;"
    return src


def _compile(code):
    context = quickjs.Context()
    context.eval(code)
    expand = context.get('expand')
    extract = context.get('extract')
    validate = context.get('validate')
    return context, expand, extract, validate


threadpool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
lock = threading.Lock()

future = threadpool.submit(_compile, _get_js_code())
concurrent.futures.wait([future])
context, js_expand, js_extract, js_validate = future.result()

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


def is_know_syntax(syntax):
    "Check if given syntax name is supported by Emmet"
    return syntax in markup_syntaxes or syntax in stylesheet_syntaxes


def get_syntax_type(syntax):
    "Returns type of given syntax: either 'markup' or 'stylesheet'"
    return syntax in stylesheet_syntaxes and 'stylesheet' or 'markup'


def get_syntax(view, pt):
    "Returns context syntax for given point"
    scope = view.scope_name(pt)

    if not re_string_scope.search(scope):
        m = re_source_scope.search(scope)
        if m and is_know_syntax(m.group(1)):
            return m.group(1)

    # Unknown syntax, fallback to HTML
    return 'html'


def get_options(view, pt):
    "Returns Emmet options for given character location in view"
    syntax = get_syntax(view, pt)
    return {
        'syntax': syntax,
        'type': get_syntax_type(syntax)
    }


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
