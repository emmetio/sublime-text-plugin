# pylint: disable=import-error
import sublime
import sublime_plugin
# pylint: enable=import-error

import re
import sys
import os.path

sys.path += [os.path.abspath(os.path.dirname(__file__))]

from emmet import expand, extract

re_string_scope = re.compile(r'\bstring\b')
# rs_jsx_scope = re.compile(r'\bsource\.jsx?\b')
re_source_scope = re.compile(r'\bsource\.([\w\-]+)')

markup_syntaxes = ['html', 'xml', 'xsl', 'jsx', 'haml', 'jade', 'pug', 'slim']
stylesheet_syntaxes = ['css', 'scss', 'sass', 'less', 'sss', 'stylus', 'postcss']

def is_know_syntax(syntax):
    return syntax in markup_syntaxes or syntax in stylesheet_syntaxes

def get_syntax_type(syntax):
    """
    Returns type of given syntax: either 'markup' or 'stylesheet'
    """
    return syntax in stylesheet_syntaxes and 'stylesheet' or 'markup'

def get_syntax(view, pt):
    """
    Returns context syntax for given point
    """

    scope = view.scope_name(pt)

    if not re_string_scope.search(scope):
        m = re_source_scope.search(scope)
        if m and is_know_syntax(m.group(1)):
            return m.group(1)

    # Unknown syntax, fallback to HTML
    return 'html'

def is_autocomplete_context(view, pt):
    """
    Check if given location in view is allowed for autocomplete context
    """
    return view.match_selector(pt, "text.html - (source - source text.html, meta)")

def expand_from_line(view: sublime.View, pt: int):
    """
    Tries to extract abbreviation from line at given point.
    If succeeded, returns expanded abbreviation and abbreviation
    location in given view
    """
    syntax = get_syntax(view, pt)
    opt = {
        'syntax': syntax,
        'type': get_syntax_type(syntax)
    }

    # Extract abbreviation from line that matches given point
    line_region = view.line(pt)
    line_start = line_region.begin()
    line = view.substr(line_region)

    abbr_data = extract(line, pt - line_start, opt)
    if abbr_data:
        abbr = abbr_data['abbreviation']

        # Replace abbreviation with snippet
        snippet = expand(abbr, opt)
        if snippet is not None:
            start = line_start + abbr_data['start']
            end = line_start + abbr_data['end']
            return snippet, start, end

def escape_html(text: str):
    escaped = { '<': '&lt;', '&': '&amp;', '>': '&gt;' }
    return re.sub(r'[<>&]', lambda m: escaped[m.group(0)], text)
    # return text.replace(r'[<>&]', lambda m: escaped[m.group(0)])

def indent_size(line: str):
    m = re.match(r'\t+', line)
    if m:
        return len(m.group(0))
    return 0

def popup_content(snippet: str):
    lines = [
        '<div style="padding-left: %dpx"><code>%s</code></div>' % (indent_size(line) * 20, escape_html(line)) for line in snippet.splitlines()
    ]
    return """
    <body>
        <style>
            body { font-size: 0.85rem; }
            pre { display: block }
            h1 { font-size: 1rem; margin-top: 0; margin-bottom: 0.3rem; }
            .main { line-height: 1.5rem; }
        </style>
        <h1>Emmet abbreviation:</h1>
        <div class="main">%s</div>
    </body>
    """ % '\n'.join(lines)


class ExpandAbbreviation(sublime_plugin.TextCommand):
    def run(self, edit, **kw):
        selections = list(self.view.sel())
        for sel in reversed(selections):
            expanded = expand_from_line(self.view, sel.begin())
            if expanded:
                # Replace abbreviation with expanded snippet
                snippet, start, end = expanded
                region = sublime.Region(start, end)
                self.view.replace(edit, region, '')
                self.view.run_command('insert_snippet', {'contents': snippet})

class EmmetCompletions(sublime_plugin.EventListener):
    def on_modified(self, view: sublime.View):
        caret = view.sel()[0].begin()
        if is_autocomplete_context(view, caret):
            expanded = expand_from_line(view, caret)
            if expanded:
                view.show_popup(popup_content(expanded[0]),
                                sublime.COOPERATE_WITH_AUTO_COMPLETE, expanded[1], 400, 300)


    def on_query_completions(self, view, prefix, locations):
        expanded = expand_from_line(view, locations[0])
        if expanded:
            snippet, start, end = expanded
            abbr = view.substr(sublime.Region(start, end))
            return [
                ['%s\tEmmet' % abbr, snippet]
            ]
        return None
