import sublime
from . import emmet_sublime as emmet
from . import syntax
from .utils import get_content

models_for_buffer = {}


def run_action(view: sublime.View, previous=False):
    sel = view.sel()[0]
    syntax_name = syntax.from_pos(view, sel.a)
    is_css = syntax.is_css(syntax_name)
    if is_css or syntax.is_html(syntax_name):
        select_item(view, sel, is_css, previous)


def select_item(view: sublime.View, sel: sublime.Region, is_css=False, is_previous=False):
    "Selects next/previous item for CSS source"
    buffer_id = view.buffer_id()
    pos = sel.begin()

    # Check if we are still in calculated model
    model = models_for_buffer.get(buffer_id)
    if model:
        region = find_region(sel, model.ranges, is_previous)
        if region:
            select(view, region)
            return

        # Out of available selection range, move to next tag
        pos = model.start if is_previous else model.end

    # Calculate new model from current editor content
    content = get_content(view)
    model = emmet.select_item(content, pos, is_css, is_previous)
    if model:
        models_for_buffer[buffer_id] = model
        region = find_region(sel, model.ranges, is_previous)
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
        elif candidate is None and (r.contains(sel) or (reverse and r.a <= sel.a) or \
            (not reverse and r.a >= sel.a)):
            # We should store
            candidate = r

    return candidate if not get_next else None


def select(view: sublime.View, region: sublime.Region):
    "Selects given region in view"
    selection = view.sel()
    selection.clear()
    selection.add(region)
    view.show(region.a)


def reset_model(view: sublime.View):
    "Resets stores model for given view"
    buffer_id = view.buffer_id()
    if buffer_id in models_for_buffer:
        del models_for_buffer[buffer_id]
