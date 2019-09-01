import concurrent.futures
import threading
import json
import os.path
import quickjs

base_path = os.path.abspath(os.path.dirname(__file__))

with open(os.path.join(base_path, 'emmet.js'), encoding='UTF-8') as f:
    src = f.read()

src += "\nvar {expand, extract} = emmet;"


def _compile(code):
    context = quickjs.Context()
    context.eval(src)
    expand = context.get('expand')
    extract = context.get('extract')
    return context, expand, extract


threadpool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
lock = threading.Lock()

future = threadpool.submit(_compile, src)
concurrent.futures.wait([future])
context, js_expand, js_extract = future.result()

def expand(abbr, options=None):
    """
    Expands given abbreviation into code block
    """
    return call_js(js_expand, abbr, options)


def extract(line, pos, options=None):
    """
    Extracts abbreviation from given line of source code
    """
    return call_js(js_extract, line, pos, options)


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
