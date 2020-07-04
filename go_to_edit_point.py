import sublime_plugin
from .utils import get_caret, go_to_pos
from .telemetry import track_action


def find_new_edit_point(view, pos, inc):
    doc_size = view.size()
    cur_pos = pos

    while cur_pos < doc_size and cur_pos >= 0:
        cur_pos += inc
        cur_char = view.substr(cur_pos)
        next_char = cur_pos < doc_size - 1 and view.substr(cur_pos + 1) or ''
        prev_char = cur_pos > 0 and view.substr(cur_pos - 1) or ''

        if cur_char in '"\'' and next_char == cur_char and prev_char == '=':
            # Empty attribute value
            return cur_pos + 1

        if cur_char == '<' and prev_char == '>':
            # Between tags
            return cur_pos

        if cur_char in '\n\r':
            line_region = view.line(cur_pos)
            line = view.substr(line_region)
            if not line or line.isspace():
                # Empty line
                return line_region.b

class EmmetGoToEditPoint(sublime_plugin.TextCommand):
    def run(self, edit, previous=False):
        caret = get_caret(self.view)
        delta = -1 if previous else 1
        pt = find_new_edit_point(self.view, caret + delta, delta)
        if pt is not None:
            go_to_pos(self.view, pt)

        track_action('Go to Edit Point', 'previous' if previous else 'next')
