import quickjs
import json

with open('./emmet.js') as f:
	src = f.read()

src += "\nvar {expand, extract} = emmet;"

context = quickjs.Context()
context.eval(src)

def convert_arg(arg):
    if isinstance(arg, (type(None), str, bool, float, int)):
        return arg
    else:
        # More complex objects are passed through JSON.
        return context.eval("(" + json.dumps(arg) + ")")

def expand(abbr, options={}):
    """
    Expands given abbreviation into code block
    """
    js_expand = context.get('expand')
    return js_expand(abbr, convert_arg(options))

def extract(line, pos=None, options={}):
    js_extract = context.get('extract')
    if pos is None:
        pos = len(line)
    res = js_extract(line, pos, convert_arg(options)).json()
    if res:
        return json.loads(res)

    return None

print(expand('p10'))
print(expand('p10', { 'type': 'stylesheet' }))
print(extract('hello foo>bar')['abbreviation'])
