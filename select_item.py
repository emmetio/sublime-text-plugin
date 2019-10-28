import sublime
import sublime_plugin
from . import emmet
from . import syntax
from . import utils

models_for_buffer = {}


class EmmetSelectItem(sublime_plugin.TextCommand):
    def run(self, edit, previous=False):
        sel = self.view.sel()[0]
        syntax_name = syntax.from_pos(self.view, sel.a)
        if syntax.is_css(syntax_name):
            select_item_css(self.view, sel, previous)
        elif syntax.is_html(syntax_name):
            select_item(self.view, sel, previous)


class SelectItemListener(sublime_plugin.EventListener):
    def on_modified(self, view: sublime.View):
        buffer_id = view.buffer_id()
        if buffer_id in models_for_buffer:
            del models_for_buffer[buffer_id]


def select_item(view: sublime.View, sel: sublime.Region, is_previous=False):
    buffer_id = view.buffer_id()
    pos = sel.begin()
    key = 'start' if is_previous else 'end'

    # Check if we are still in calculated model
    if buffer_id in models_for_buffer:
        model = models_for_buffer[buffer_id]
        if model['start'] < pos < model['end']:
            region = find_region(sel, model['regions'], is_previous)
            if region:
                return select(view, region)

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


def select_item_css(view: sublime.View, sel: sublime.Region, is_previous=False):
    "Selects next/previous item for CSS source"
    buffer_id = view.buffer_id()
    pos = sel.begin()

    # Check if we are still in calculated model
    if buffer_id in models_for_buffer:
        model = models_for_buffer[buffer_id]
        region = find_region(sel, model, is_previous)
        if region:
            select(view, region)
            return

        # Out of available selection range, move to next tag
        pos = model[0].begin() if is_previous else model[-1].end()


    # Calculate new model from current editor content
    content = utils.get_content(view)
    model = emmet.select_item_css(content, pos, is_previous)
    if model:
        models_for_buffer[buffer_id] = model
        region = find_region(sel, model, is_previous)
        if region:
            select(view, region)
            return


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
        elif candidate is None and (r.contains(sel) or (reverse and r.a <= sel.a) or (not reverse and r.a >= sel.a)):
            # We should store
            candidate = r

    return candidate if not get_next else None


def select(view: sublime.View, region: sublime.Region):
    "Selects given region in view"
    selection = view.sel()
    selection.clear()
    selection.add(region)
    view.show(region.a)
