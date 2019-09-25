import re
import html
import sublime

phantom_sets_by_buffer = {}
previews_by_buffer = set()

def plugin_unloaded():
    for wnd in sublime.windows():
        for view in wnd.views():
            hide(view)


def show(view, marker, as_phantom=False):
    "Displays Emmet abbreviation as a preview for given view"
    content = None
    buffer_id = view.buffer_id()

    try:
        content = format_snippet(marker.preview())
    except Exception as e:
        content = '<div class="error">%s</div>' % format_snippet(str(e))

    if content:
        if as_phantom:
            if buffer_id not in phantom_sets_by_buffer:
                phantom_set = sublime.PhantomSet(view, 'emmet')
                phantom_sets_by_buffer[buffer_id] = phantom_set
            else:
                phantom_set = phantom_sets_by_buffer[buffer_id]

            r = sublime.Region(marker.region.end(), marker.region.end())
            phantoms = [sublime.Phantom(r, phantom_content(content), sublime.LAYOUT_INLINE)]
            phantom_set.update(phantoms)
        else:
            previews_by_buffer.add(buffer_id)
            view.show_popup(popup_content(content), 0, marker.region.begin(), 400, 300)


def hide(view):
    "Hides Emmet abbreviation preview for given view"
    buffer_id = view.buffer_id()

    if buffer_id in previews_by_buffer:
        previews_by_buffer.remove(buffer_id)
        view.hide_popup()

    if buffer_id in phantom_sets_by_buffer:
        del phantom_sets_by_buffer[buffer_id]
        view.erase_phantoms('emmet')


def toggle(view, marker, pos, as_phantom=False):
    "Toggle Emmet abbreviation preview display for given marker and location"
    if marker.contains(pos) and (not marker.simple or marker.type == 'stylesheet'):
        show(view, marker, as_phantom)
    else:
        hide(view)

def format_snippet(text, class_name=None):
    class_attr = class_name and (' class="%s"' % class_name) or ''
    lines = [
        '<div%s style="padding-left: %dpx"><code>%s</code></div>' % (class_attr, indent_size(line, 20), html.escape(line, False)) for line in text.splitlines()
    ]

    return '\n'.join(lines)


def popup_content(content):
    return """
    <body>
        <style>
            body { line-height: 1.5rem; }
            .error { color: red }
        </style>
        <div>%s</div>
    </body>
    """ % content


def phantom_content(content):
    return """
    <body>
        <style>
            body {
                background-color: var(--orangish);
                color: #fff;
                border-radius: 3px;
                padding: 1px 3px;
                position: relative;
            }

            .error { color: red }
        </style>
        <div class="main">%s</div>
    </body>
    """ % content


def indent_size(line, width=1):
    m = re.match(r'\t+', line)
    if m:
        return len(m.group(0)) * width
    return 0
