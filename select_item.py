import sublime
import sublime_plugin
from . import emmet
from . import syntax
from . import utils

models_for_buffer = {}

class SelectNextItem(sublime_plugin.TextCommand):
    def run(self, edit, **kw):
        sel = self.view.sel()[0]
        syntax_name = syntax.from_pos(self.view, sel.a)
        if syntax.is_html(syntax_name):
            select_item(self.view, sel, False)


class SelectPreviousItem(sublime_plugin.TextCommand):
    def run(self, edit, **kw):
        sel = self.view.sel()[0]
        syntax_name = syntax.from_pos(self.view, sel.a)
        if syntax.is_html(syntax_name):
            select_item(self.view, sel, True)


class SelectItemListener(sublime_plugin.EventListener):
    def on_modified(self, view):
        buffer_id = view.buffer_id()
        if buffer_id in models_for_buffer:
            del models_for_buffer[buffer_id]


def select_item(view, sel, is_previous=False):
    buffer_id = view.buffer_id()
    pos = sel.a
    key = is_previous and 'start' or 'end'

    # Check if we are still in calculated model
    if buffer_id in models_for_buffer:
        model = models_for_buffer[buffer_id]
        if pos > model['start'] and pos < model['end']:
            region = find_region(sel, model['regions'], is_previous)
            if region:
                return select(view, region)
            else:
                # Out of available selection range, move to next tag
                pos = model[key]

    # Calculate new model from current editor content
    # TODO we can start parsing from 'end' position of previous model
    # and improve performance a bit
    content = utils.get_content(view)
    model = emmet.select_item(content, pos, is_previous)
    if model:
        models_for_buffer[buffer_id] = model
        region = find_region(sel, model['regions'], is_previous)
        if region:
            return select(view, region)


def find_region(sel, regions, reverse=False):
    if reverse:
        regions = regions[:]
        regions.reverse()

    get_next = False
    candidate = None

    for r in regions:
        if get_next:
            return r
        if r == sel:
            # This range is currently selected, request next
            get_next = True
        elif candidate is None and (r.contains(sel) or (reverse and r.a <= sel.a ) or (not reverse and r.a >= sel.a)):
            # We should store
            candidate = r

    return not get_next and candidate or None


def select(view, region):
    selection = view.sel()
    selection.clear()
    selection.add(region)
    view.show(region.a)
