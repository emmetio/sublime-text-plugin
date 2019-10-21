import re
import os.path
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


def get_content(view):
    "Returns contents of given view"
    return view.substr(sublime.Region(0, view.size()))


def go_to_pos(view, pos):
    sel = view.sel()
    sel.clear()
    sel.add(sublime.Region(pos, pos))
    view.show(pos)


def is_url(file_path):
    "Check if given file path is an URL"
    return re.match(r'^\w+?://', file_path)


def locate_file(editor_file: str, file_name: str):
    """
    Locate `file_name` file relative to `editor_file`.
    If `file_name` is absolute, will traverse up to folder structure looking for
    matching file.
    """
    previous_parent = ''
    parent = os.path.dirname(editor_file)
    while parent and os.path.exists(parent) and parent != previous_parent:
        tmp = create_path(parent, file_name)
        if os.path.exists(tmp):
            return tmp

        previous_parent = parent
        parent = os.path.dirname(parent)


def create_path(parent, file_name):
    """
    Creates absolute path by concatenating `parent` and `file_name`.
    If `parent` points to file, its parent directory is used
    """
    result = ''
    file_name = file_name.lstrip('/')

    if os.path.exists(parent):
        if os.path.isfile(parent):
            parent = os.path.dirname(parent)

        result = os.path.normpath(os.path.join(parent, file_name))

    return result
