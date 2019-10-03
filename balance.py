import sublime
from . import emmet

def push_range(items, region):
    last = items[-1]
    if not last or last != region:
        items.append(region)

def get_ranges(view, pt, syntax, direction='outward'):
    "Returns regions for balancing"
    result = []
    content = view.substr(sublime.Region(0, view.size()))
    tags = emmet.balance(content, pt, direction, syntax in emmet.xml_syntaxes)
    for tag in tags:
        region = None
        if tag.has('close'):
            region = sublime.Region(tag['open'][0], tag['close'][1])
        else:
            region = sublime.Region(tag['open'][0], tag['open'][1])

        push_range(result, region)

        # Create range for tag content
