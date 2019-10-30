import sublime
import sublime_plugin
from . import emmet
from . import utils

class EmmetEvaluateMath(sublime_plugin.TextCommand):
    def run(self, edit, **kw):
        caret = utils.get_caret(self.view)
        line = self.view.line(caret)
        expr = emmet.evaluate_math(self.view.substr(line), caret - line.begin())
        if expr:
            r = sublime.Region(line.begin() + expr['start'], line.begin() + expr['end'])
            self.view.replace(edit, r, str(expr['result']))
