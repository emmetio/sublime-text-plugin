import re
import sublime
import sublime_plugin
from .emmet import extract, expand
from .emmet.syntax import get_syntax_type, get_syntax

abbr_region_id = 'emmet-abbreviation'
abbr_ui_flags = sublime.DRAW_SOLID_UNDERLINE | sublime.DRAW_NO_FILL | sublime.DRAW_NO_OUTLINE
active_preview = False
active_preview_id = None

def plugin_unloaded():
    for wnd in sublime.windows():
        for view in wnd.views():
            clear_abbreviation(view)
            if view.id() == active_preview_id:
                hide_preview(view)

def is_abbreviation_context(view, pt):
    """
    Check if given location in view is allowed for abbreviation marking
    """
    return view.match_selector(pt, "text.html - (source - source text.html, meta)")

def abbr_from_line(view, pt):
    """
    Extracts abbreviation from line that matches given point in view
    """
    line_region = view.line(pt)
    line_start = line_region.begin()
    line = view.substr(line_region)

    syntax = get_syntax(view, pt)
    abbr_data = extract(line, pt - line_start, {
        'syntax': syntax,
        'type': get_syntax_type(syntax)
    })

    if abbr_data:
        abbr = abbr_data['abbreviation']
        start = line_start + abbr_data['start']
        end = line_start + abbr_data['end']

        return (abbr, start, end)

def mark_abbreviation(view, pt):
    """
    Extracts abbreviation from line at given point and, if found, marks it in view
    """
    abbr_data = abbr_from_line(view, pt)
    if abbr_data:
        abbr, start, end = abbr_data
        view.add_regions(abbr_region_id, [sublime.Region(start, end)], 'string.emmet', '', abbr_ui_flags)
        return True

    return False

def clear_abbreviation(view):
    view.erase_regions(abbr_region_id)

def show_preview(view, abbr_region):
    abbr = view.substr(abbr_region)
    globals()['active_preview'] = True
    globals()['active_preview_id'] = view.id()
    view.show_popup(get_preview(view, abbr),
        sublime.COOPERATE_WITH_AUTO_COMPLETE, abbr_region.begin(), 400, 300)

def hide_preview(view):
    if active_preview and active_preview_id == view.id():
        view.hide_popup()

    globals()['active_preview'] = False
    globals()['active_preview_id'] = None

def get_preview(view, abbr, syntax='html'):
    try:
        snippet = expand(abbr, {
            'syntax': syntax,
            'type': get_syntax_type(syntax),
            'preview': True
        })

        lines = [
            '<div style="padding-left: %dpx"><code>%s</code></div>' % (indent_size(line) * 20, escape_html(line)) for line in snippet.splitlines()
        ]

        return popup_content('\n'.join(lines))
    except Exception as e:
        return popup_content('<div class="error">%s</div>' % e)

def indent_size(line):
    m = re.match(r'\t+', line)
    if m:
        return len(m.group(0))
    return 0

def popup_content(content):
    return """
    <body>
        <style>
            body { font-size: 0.85rem; }
            pre { display: block }
            h1 { font-size: 1rem; margin-top: 0; margin-bottom: 0.3rem; }
            .main { line-height: 1.5rem; }
            .error { color: red }
        </style>
        <h1>Emmet abbreviation:</h1>
        <div class="main">%s</div>
    </body>
    """ % content

def escape_html(text):
    escaped = { '<': '&lt;', '&': '&amp;', '>': '&gt;' }
    return re.sub(r'[<>&]', lambda m: escaped[m.group(0)], text)

class ExpandAbbreviation(sublime_plugin.TextCommand):
    def run(self, edit, **kw):
        regions = self.view.get_regions(abbr_region_id)
        abbr_region = regions and regions[0]

        clear_abbreviation(self.view)

        for sel in reversed(list(self.view.sel())):
            caret = sel.begin()
            abbr_data = None

            if abbr_region and abbr_region.contains(sel.begin()):
                # Caret point to marked abbreviation
                abbr_data = (self.view.substr(abbr_region), abbr_region.begin(), abbr_region.end())
            else:
                # Should extract abbreviation from given line
                abbr_data = abbr_from_line(self.view, caret)

            if abbr_data:
                try:
                    abbr, start, end = abbr_data
                    syntax = get_syntax(self.view, caret)
                    snippet = expand(abbr, {
                        'syntax': syntax,
                        'type': get_syntax_type(syntax)
                    })
                    region = sublime.Region(start, end)
                    self.view.replace(edit, region, '')
                    self.view.run_command('insert_snippet', {'contents': snippet})
                except:
                    pass

class MarkAbbreviation(sublime_plugin.TextCommand):
    def run(self, edit, **kw):
        caret = self.view.sel()[0].begin()
        clear_abbreviation(self.view)
        mark_abbreviation(self.view, caret)

class AbbreviationMarker(sublime_plugin.EventListener):
    def on_modified(self, view: sublime.View):
        mark = [s for s in view.sel()]
        regions = view.get_regions(abbr_region_id)

        if len(mark) != 1 or not mark[0].empty():
            # Multiple selections are not supported yet
            clear_abbreviation(view)
            return

        caret = mark[0].begin()
        if regions and not regions[0].empty() and regions[0].contains(caret):
            # Modification made inside caret: do nothing, it will be automatically
            # expanded
            return

        # Try to find abbreviation from current caret position, if available
        clear_abbreviation(view)

        if is_abbreviation_context(view, caret):
            mark_abbreviation(view, caret)

    def on_selection_modified(self, view: sublime.View):
        mark = [s for s in view.sel()]
        regions = view.get_regions(abbr_region_id)

        if len(mark) == 1 and regions and regions[0].contains(mark[0]):
            # Caret is inside marked abbreviation, display preview
            show_preview(view, regions[0])
        else:
            hide_preview(view)

    def on_query_context(self, view, key, op, operand, match_all):
        if key == 'emmet_tab_expand':
            # Trying to expand Emmet abbreviation with tab:
            # check if there’s marked abbreviation under caret
            regions = view.get_regions(abbr_region_id)
            abbr_region = regions and regions[0]
            if abbr_region:
                for s in view.sel():
                    if abbr_region.contains(s):
                        return True

            return False

        return None
