import sublime
import sublime_plugin
from . import emmet
from . import syntax
from . import utils

class GoToTagPair(sublime_plugin.TextCommand):
    def run(self, edit, **kw):
        caret = utils.get_caret(self.view)
        if self.view.substr(caret) == '<':
            caret += 1

        syntax_name = syntax.from_pos(self.view, caret)
        if syntax.is_html(syntax_name):
            ctx = emmet.get_tag_context(self.view, caret, syntax.is_xml(syntax_name))
            if ctx and 'open' in ctx and 'close' in ctx:
                open_tag = ctx['open']
                close_tag = ctx['close']

                if open_tag.contains(caret):
                    pos = close_tag.a
                else:
                    pos = open_tag.a

                sel = self.view.sel()
                sel.clear()
                sel.add(sublime.Region(pos, pos))
                self.view.show(pos)

