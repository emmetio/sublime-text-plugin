import sublime

def narrow_to_non_space(view, region):
    "Returns copy of region which starts and ends at non-space character"
    begin = region.begin()
    end = region.end()

    while begin < end:
        if not view.substr(begin).isspace():
            break
        begin += 1

    while end > begin:
        if not view.substr(end - 1).isspace():
            break
        end -= 1

    return sublime.Region(begin, end)


def replace_with_snippet(view, edit, region, snippet):
    "Replaces given region view with snippet contents"
    sel = view.sel()
    sel.clear()
    sel.add(sublime.Region(region.begin(), region.begin()))
    view.replace(edit, region, '')
    view.run_command('insert_snippet', { 'contents': snippet })


def get_caret(view):
    "Returns current caret position for single selection"
    return view.sel()[0].begin()


def go_to_pos(view, pos):
    sel = view.sel()
    sel.clear()
    sel.add(sublime.Region(pos, pos))
    view.show(pos)

