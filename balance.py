import sublime
import sublime_plugin
from . import emmet
from . import syntax
from . import utils


def push_range(items, region):
    last = items and items[-1]
    if not last or last != region and region:
        items.append(region)


def get_regions(view: sublime.View, pt: int, syntax_name: str, direction='outward'):
    "Returns regions for balancing"
    content = utils.get_content(view)

    if syntax.is_css(syntax_name):
        regions = emmet.balance_css(content, pt, direction)
        return [emmet.to_region(r) for r in regions]

    result = []
    tags = emmet.balance(content, pt, direction, syntax.is_xml(syntax_name))

    for tag in tags:
        if tag.close:
            # Inner range
            push_range(result, sublime.Region(tag.open[1], tag.close[0]))
            # Outer range
            push_range(result, sublime.Region(tag.open[0], tag.close[1]))
        else:
            push_range(result, sublime.Region(tag.open[0], tag.open[1]))

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
            if r.contains(sel) and r.end() > sel.end():
                target_region = r
                break

        result.append(target_region)

    return result


class EmmetBalance(sublime_plugin.TextCommand):
    def run(self, edit, **kw):
        info = syntax.info(self.view, utils.get_caret(self.view), 'html')
        syntax_name = info['syntax']

        if info['type'] != 'markup' and not syntax.is_css(syntax_name):
            return

        direction = kw.get('direction', 'outward')

        if direction == 'inward':
            regions = balance_inward(self.view, syntax_name)
        else:
            regions = balance_outward(self.view, syntax_name)

        selection = self.view.sel()
        selection.clear()
        selection.add_all(regions)
