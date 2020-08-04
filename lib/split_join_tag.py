import sublime
from . import emmet_sublime as emmet
from . import syntax

def split_join_tag(view: sublime.View, edit: sublime.Edit):
    for sel in view.sel():
        pt = sel.begin()
        syntax_name = syntax.from_pos(view, pt)
        xml = syntax.is_xml(syntax_name)
        tag = emmet.get_tag_context(view, pt, xml)

        if tag:
            open_tag = tag.get('open')
            close_tag = tag.get('close')

            if close_tag:
                # Join tag: remove tag contents, if any, and add closing slash
                view.erase(edit, sublime.Region(open_tag.end(), close_tag.end()))
                closing = '/' if view.substr(open_tag.end() - 2).isspace() else ' /'
                view.insert(edit, open_tag.end() - 1, closing)
            else:
                # Split tag: add closing part and remove closing slash
                view.insert(edit, open_tag.end(), '</%s>' % tag['name'])
                if view.substr(open_tag.end() - 2) == '/':
                    start = open_tag.end() - 2
                    end = open_tag.end() - 1
                    if view.substr(start - 1).isspace():
                        start -= 1
                    view.erase(edit, sublime.Region(start, end))

