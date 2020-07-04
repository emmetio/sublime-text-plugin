import sublime
import sublime_plugin
from .telemetry import track_action

class EmmetIncrementNumber(sublime_plugin.TextCommand):
    def run(self, edit, delta=1):
        next_selections = []
        selections = self.view.sel()
        for sel in selections:
            if sel.empty():
                # No selection, extract number
                line = self.view.line(sel.begin())
                offset = line.begin()
                num_region = extract_number(self.view.substr(line), sel.begin() - offset)
                if num_region:
                    sel = sublime.Region(num_region[0] + offset, num_region[1] + offset)

            if not sel.empty():
                # Try to update value in given region
                value = update_number(self.view.substr(sel), delta)
                if value is not None:
                    self.view.replace(edit, sel, value)
                    sel = sublime.Region(sel.begin(), sel.begin() + len(value))

            next_selections.append(sel)

        selections.clear()
        selections.add_all(next_selections)

        track_action('Increment number', 'delta', delta)


def extract_number(text: str, pos: int):
    "Extracts number from text at given location"
    has_dot = False
    end = pos
    start = pos

    # Read ahead for possible numbers
    while end < len(text):
        ch = text[end]
        if ch == '.':
            if has_dot:
                break
            has_dot = True
        elif not ch.isdigit():
            break
        end += 1

    # Read backward for possible numerics
    while start >= 0:
        ch = text[start - 1]
        if ch == '.':
            if has_dot:
                break
            has_dot = True
        elif not ch.isdigit():
            break
        start -= 1

    # Negative number?
    if start > 0 and text[start - 1] == '-':
        start -= 1

    if start != end:
        return (start, end)

def update_number(num: str, delta: float, precision=3):
    "Increments given number with `delta` and returns formatted result"
    try:
        fmt = '%.' + str(precision) + 'f'
        value = float(num) + delta
        neg = value < 0
        result = fmt % abs(value)

        # Trim trailing zeroes and optionally decimal number
        result = result.rstrip('0').rstrip('.')

        # Trim leading zero if input value doesn't have it
        if (num[0] == '.' or num[0:2] == '-.') and result[0] == '0':
            result = result[1:]

        return '-{0}'.format(result) if neg else result
    except:
        return None
