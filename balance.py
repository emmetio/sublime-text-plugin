import sublime
import sublime_plugin
from . import emmet
from . import syntax
from . import utils


def push_range(items, region):
    last = items and items[-1]
    if not last or last != region and region:
        items.append(region)


def get_regions(view, pt, syntax, direction='outward'):
    "Returns regions for balancing"
    result = []
    content = view.substr(sublime.Region(0, view.size()))
    tags = emmet.balance(content, pt, direction, syntax in emmet.xml_syntaxes)
    for tag in tags:
        open_tag = tag.get('open')
        close_tag = tag.get('close')
        if close_tag:
            # Inner range
            push_range(result, sublime.Region(open_tag[1], close_tag[0]))
            # Outer range
            push_range(result, sublime.Region(open_tag[0], close_tag[1]))
        else:
            push_range(result, sublime.Region(open_tag[0], open_tag[1]))

    result.sort(key=lambda v: v.begin(), reverse=direction == 'outward')
    return result


def balance_inward(view, syntax_name):
    "Returns inward balanced ranges from current view's selection"
    result = []

    for sel in view.sel():
        regions = get_regions(view, sel.begin(), syntax_name, 'inward')

        # Try to find range which equals to selection: we should pick leftmost
        ix = -1
        for i, r in enumerate(regions):
            if r == sel:
                ix = i
                break

        target_region = sel

        if ix < len(regions) - 1:
            target_region = regions[ix + 1]
        elif ix == -1:
            # No match found, pick closest region
            for r in regions:
                if r.contains(sel):
                    target_region = r
                    break

        result.append(target_region)

    return result


def balance_outward(view, syntax_name):
    "Returns outward balanced ranges from current view's selection"
    result = []

    for sel in view.sel():
        regions = get_regions(view, sel.begin(), syntax_name, 'outward')
        target_region = sel
        for r in regions:
            if r.contains(sel) and r.b > sel.b:
                target_region = r
                break

        result.append(target_region)

    return result


class BalanceTag(sublime_plugin.TextCommand):
    def run(self, edit, **kw):
        info = syntax.info(self.view, utils.get_caret(self.view), 'html')
        if info['type'] != 'markup':
            return

        syntax_name = info['syntax']
        direction = kw.get('direction', 'outward')

        if direction == 'inward':
            regions = balance_inward(self.view, syntax_name)
        else:
            regions = balance_outward(self.view, syntax_name)

        selection = self.view.sel()
        selection.clear()
        selection.add_all(regions)
