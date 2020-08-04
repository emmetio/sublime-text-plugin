import re
import html
import sublime
import sublime_plugin
from time import time
from . import emmet_sublime as emmet
from . import syntax
from .utils import get_caret, go_to_pos
from .telemetry import track_action
from .config import get_user_css

previews_by_buffer = {}
phantoms_by_buffer = {}
phantom_key = 'emmet_tag_preview'
max_preview_len = 100
tracking = {
    'last_event': 0,
    # Delay between tracking events, in seconds
    'delay': 5 * 60
}

def show_tag_preview(view: sublime.View, pt: int, text: str, dest: int):
    "Displays given tag preview at `pt` location"
    buffer_id = view.buffer_id()
    if buffer_id not in phantoms_by_buffer:
        phantom_set = sublime.PhantomSet(view, phantom_key)
        phantoms_by_buffer[buffer_id] = phantom_set
    else:
        phantom_set = phantoms_by_buffer[buffer_id]

    r = sublime.Region(pt, pt)
    nav = lambda href: go_to_pos(view, int(href))
    phantoms = [sublime.Phantom(r, phantom_content(text, dest), sublime.LAYOUT_INLINE, on_navigate=nav)]
    phantom_set.update(phantoms)


def hide_tag_preview(view: sublime.View):
    "Hides tag preview in given view"
    buffer_id = view.buffer_id()

    if buffer_id in phantoms_by_buffer:
        del phantoms_by_buffer[buffer_id]
        view.erase_phantoms(phantom_key)


def phantom_content(content: str, dest: int):
    "Returns contents for phantom preview"
    return """
    <body id="emmet-preview-phantom">
        <style>
            body {
                background-color: #1D9B45;
                color: #fff;
                border-radius: 3px;
                padding: 0px 3px;
                opacity: 0.2;
                font-size: 1rem;
            }
            a {
                text-decoration: none;
                color: #fff;
            }
            %s
        </style>
        <div class="tag-preview"><a href="%d">%s</a></div>
    </body>
    """ % (get_user_css(), dest, html.escape(content, False))


class EmmetGoToTagPair(sublime_plugin.TextCommand):
    def run(self, edit: sublime.Edit):
        caret = get_caret(self.view)
        if self.view.substr(caret) == '<':
            caret += 1

        syntax_name = syntax.from_pos(self.view, caret)
        if syntax.is_html(syntax_name):
            ctx = emmet.get_tag_context(self.view, caret, syntax.is_xml(syntax_name))
            if ctx and 'open' in ctx and 'close' in ctx:
                open_tag = ctx['open']
                close_tag = ctx['close']
                pos = close_tag.begin() if open_tag.contains(caret) else open_tag.begin()
                go_to_pos(self.view, pos)

        track_action('Go to Tag Pair')


class EmmetHideTagPreview(sublime_plugin.TextCommand):
    def run(self, edit: sublime.Edit):
        buffer_id = self.view.buffer_id()
        if buffer_id in previews_by_buffer:
            pt, visible = previews_by_buffer[buffer_id]
            if visible:
                previews_by_buffer[buffer_id] = (pt, False)


def allow_preview(fn):
    "Method decorator for running action callbacks for in allowed tag preview context"
    def wrapper(self, view):
        if not view.settings().get('is_widget') and emmet.get_settings('tag_preview'):
            size = emmet.get_settings('tag_preview_size_limit', 0)
            if not size or view.size() <= size:
                fn(self, view)
    return wrapper


class PreviewTagPair(sublime_plugin.EventListener):
    def on_query_context(self, view: sublime.View, key: str, *args):
        if key == 'emmet_tag_preview':
            buffer_id = view.buffer_id()
            if buffer_id in previews_by_buffer:
                return previews_by_buffer[buffer_id][1]
        return None

    @allow_preview
    def on_selection_modified_async(self, view: sublime.View):
        caret = get_caret(view)
        syntax_name = syntax.from_pos(view, caret)
        buffer_id = view.buffer_id()

        if syntax.is_html(syntax_name):
            ctx = emmet.get_tag_context(view, caret, syntax.is_xml(syntax_name))
            if ctx and 'close' in ctx and \
                ctx['attributes'] and \
                ctx['close'].contains(caret) and \
                not view.visible_region().contains(ctx['open']):
                pos = ctx['close'].b

                # Do not display preview if user forcibly hides it with Esc key
                # for current location
                if buffer_id in previews_by_buffer:
                    pt = previews_by_buffer[buffer_id][0]
                    if pt == pos:
                        return

                preview = create_tag_preview(ctx)
                if len(preview) > max_preview_len:
                    preview = '%s...' % preview[0:max_preview_len]
                show_tag_preview(view, pos, preview, ctx['open'].a)
                previews_by_buffer[buffer_id] = (pos, True)
                track_preview()
                return

        hide_tag_preview(view)
        if buffer_id in previews_by_buffer:
            del previews_by_buffer[buffer_id]


def track_preview():
    last_event = tracking['last_event']
    now = time()
    if now > last_event + tracking['delay']:
        track_action('Display Tag Preview')
        tracking['last_event'] = now


def create_tag_preview(ctx: dict):
    class_name = ''
    id_name = ''
    attrs = []
    for k in ctx['attributes'].keys():
        value = ctx['attributes'][k]
        if k == 'class':
            value = re.sub(r'\s+', '.', value.strip())
            if value:
                class_name += '.%s' % value
        elif k == 'id':
            id_name += '#%s' % value.strip()
        else:
            attrs.append('%s="%s"' % (k, value))

    attr_str = ('[%s]' % ' '.join(attrs)) if attrs else ''
    return '%s%s%s%s' % (ctx['name'], id_name, class_name, attr_str)
