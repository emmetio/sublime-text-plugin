import sublime
import sublime_plugin
from emmet import expand, extract

def get_syntax(view, pt=None):
    """
    Returns either document syntax for given view or context syntax for given point
    """


class ExpandAbbreviation(sublime_plugin.TextCommand):
    def run(self, edit, **kw):
