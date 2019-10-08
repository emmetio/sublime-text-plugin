import sublime
import sublime_plugin
from . import emmet
from . import syntax
from . import utils

models_for_buffer = {}

class SelectNextItem(sublime_plugin.TextCommand):
    def run(self, edit, **kw):
        sel = self.view.sel()[0]
        pos = sel.a
        syntax_name = syntax.from_pos(self.view, pos)
        if syntax.is_html(syntax_name):
            buffer_id = self.view.buffer_id()

            # Check if we are still in calculated model
            if buffer_id in models_for_buffer:
                model = models_for_buffer[buffer_id]
                if pos > model['start'] and pos < model['end']:
                    region = pick_next_region(sel, model['regions'])
                    if region:
                        return select(self.view, region)
                    else:
                        # Out of available selection range, move to next tag
                        pos = model['end']

                # Unable to find next region from current model, request next
                del models_for_buffer[buffer_id]

            # Calculate new model from current editor content
            # TODO we can start parsing from 'end' position of previous model
            # and improve performance a bit
            content = utils.get_content(self.view)
            model = emmet.select_item(content, pos)
            if model:
                models_for_buffer[buffer_id] = model
                region = pick_next_region(sel, model['regions'])
                if region:
                    return select(self.view, region)


class SelectItemListener(sublime_plugin.EventListener):
    def on_modified(self, view):
        buffer_id = view.buffer_id()
        if buffer_id in models_for_buffer:
            del models_for_buffer[buffer_id]


def pick_next_region(sel, regions):
    get_next = False
    for r in regions:
        if get_next:
            return r
        if r == sel:
            # This range is currently selected, request next
            get_next = True
        elif r.contains(sel) or r.a >= sel.a:
            return r


def select(view, region):
    selection = view.sel()
    selection.clear()
    selection.add(region)
    view.show(region.a)
