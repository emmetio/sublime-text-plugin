import sys
import sublime
import sublime_plugin

if int(sublime.version()) >= 3114:

    # Clear module cache to force reloading all modules of this package.
    # See https://github.com/emmetio/sublime-text-plugin/issues/35
    prefix = __package__ + "."  # don't clear the base package
    for module_name in [
        module_name
        for module_name in sys.modules
        if module_name.startswith(prefix) and module_name != __name__
    ]:
        del sys.modules[module_name]
    prefix = None

from .lib import emmet_sublime, abbreviation, balance, syntax, comment, \
    convert_data_url as convert, go_to_edit_point as go_to, go_to_tag_pair as tag_pair, \
    inc_dec_number as inc_dec, select_item, wrap_with_abbreviation as wrap
from .lib.remove_tag import remove_tag
from .lib.split_join_tag import split_join_tag
from .lib.update_image_size import update_image_size
from .lib.utils import get_caret, narrow_to_non_space, replace_with_snippet, get_content
from .lib.telemetry import track_action, check_telemetry
from .lib.config import get_settings


last_wrap_abbreviation = None
"Last abbreviation used for wrapping"

def plugin_unloaded():
    abbreviation.plugin_unloaded()


def plugin_loaded():
    check_telemetry()


def main_view(fn):
    "Method decorator for running actions in code views only"

    def wrapper(self, view):
        if not view.settings().get('is_widget'):
            fn(self, view)

    return wrapper


class EmmetExpandAbbreviation(sublime_plugin.TextCommand):
    def run(self, edit):
        caret = get_caret(self.view)
        trk = abbreviation.get_tracker(self.view)

        if trk and trk.region.contains(caret):
            abbreviation.expand_tracker(self.view, edit, trk)
            track_action('Expand Abbreviation', trk.config.syntax)
        abbreviation.stop_tracking(self.view)


class EmmetEnterAbbreviation(sublime_plugin.TextCommand):
    def run(self, edit):
        trk = abbreviation.get_tracker(self.view)
        abbreviation.stop_tracking(self.view, {'force': True, 'edit': edit})
        if trk and trk.forced:
            # Already have forced abbreviation: act as toggler
            return

        primary_sel = self.view.sel()[0]
        trk = abbreviation.start_tracking(self.view, primary_sel.begin(), primary_sel.end(), {'forced': True})
        if trk and not primary_sel.empty():
            abbreviation.show_preview(self.view, trk)
            sel = self.view.sel()
            sel.clear()
            sel.add(sublime.Region(primary_sel.end(), primary_sel.end()))
            track_action('Enter Abbreviation', trk.config.syntax)


class EmmetClearAbbreviationMarker(sublime_plugin.TextCommand):
    def run(self, edit):
        abbreviation.stop_tracking(self.view, {'force': True, 'edit': edit})
        track_action('Clear Abbreviation')


class EmmetCaptureAbbreviation(sublime_plugin.TextCommand):
    def run(self, edit):
        pos = get_caret(self.view)
        tracker = abbreviation.suggest_abbreviation_tracker(self.view, pos)
        if tracker:
            abbreviation.mark(self.view, tracker)
            abbreviation.show_preview(self.view, tracker)


class EmmetBalance(sublime_plugin.TextCommand):
    def run(self, edit, **kw):
        info = syntax.info(self.view, get_caret(self.view), 'html')
        syntax_name = info['syntax']

        if info['type'] != 'markup' and not syntax.is_css(syntax_name):
            return

        direction = kw.get('direction', 'outward')

        if direction == 'inward':
            regions = balance.balance_inward(self.view, syntax_name)
        else:
            regions = balance.balance_outward(self.view, syntax_name)

        selection = self.view.sel()
        selection.clear()
        selection.add_all(regions)

        track_action('Balance', direction)


# NB: use `Emmet` prefix to distinguish default `toggle_comment` action
class EmmetToggleComment(sublime_plugin.TextCommand):
    def run(self, edit):
        view = self.view
        for s in view.sel():
            pt = s.begin()
            syntax_name = syntax.from_pos(view, pt)
            tokens = comment.css_comment if syntax.is_css(syntax_name) else comment.html_comment

            if view.match_selector(pt, comment.comment_selector):
                # Caret inside comment, strip it
                comment_region = narrow_to_non_space(view, view.extract_scope(pt))
                comment.remove_comments(view, edit, comment_region, tokens)
            elif s.empty():
                # Empty region, find tag
                region = comment.get_range_for_comment(view, pt)
                if region is None:
                    # No tag found, comment line
                    region = narrow_to_non_space(view, view.line(pt))

                # If there are any comments inside region, remove them
                comments = comment.get_comment_regions(view, region, tokens)
                if comments:
                    removed = 0
                    comments.reverse()
                    for c in comments:
                        removed += comment.remove_comments(view, edit, c, tokens)
                    region = sublime.Region(region.begin(), region.end() - removed)

                comment.add_comment(view, edit, region, tokens)
            else:
                # Comment selection
                comment.add_comment(view, edit, s, comment.html_comment)

        pos = get_caret(view)
        track_action('Toggle Comment', syntax.from_pos(view, pos))


class EmmetConvertDataUrl(sublime_plugin.TextCommand):
    def run(self, edit):
        caret = get_caret(self.view)
        syntax_name = syntax.from_pos(self.view, caret)

        if syntax.is_html(syntax_name):
            convert.convert_html(self.view, edit, caret)
        elif syntax.is_css(syntax_name):
            convert.convert_css(self.view, edit, caret)


class ConvertDataUrlReplace(sublime_plugin.TextCommand):
    "Internal command for async text replace"
    def run(self, edit, region, text):
        region = sublime.Region(*region)
        self.view.replace(edit, region, text)


class EmmetEvaluateMath(sublime_plugin.TextCommand):
    def run(self, edit: sublime.Edit):
        caret = get_caret(self.view)
        line = self.view.line(caret)
        expr = emmet_sublime.evaluate_math(self.view.substr(line), caret - line.begin())
        if expr:
            r = sublime.Region(line.begin() + expr['start'], line.begin() + expr['end'])
            self.view.replace(edit, r, str(expr['snippet']))
        track_action('Evaluate Math')


class EmmetGoToEditPoint(sublime_plugin.TextCommand):
    def run(self, edit, previous=False):
        caret = get_caret(self.view)
        delta = -1 if previous else 1
        pt = go_to.find_new_edit_point(self.view, caret + delta, delta)
        if pt is not None:
            go_to.go_to_pos(self.view, pt)

        track_action('Go to Edit Point', 'previous' if previous else 'next')


class EmmetGoToTagPair(sublime_plugin.TextCommand):
    def run(self, edit: sublime.Edit):
        caret = get_caret(self.view)
        if self.view.substr(caret) == '<':
            caret += 1

        syntax_name = syntax.from_pos(self.view, caret)
        if syntax.is_html(syntax_name):
            ctx = emmet_sublime.get_tag_context(self.view, caret, syntax.is_xml(syntax_name))
            if ctx and 'open' in ctx and 'close' in ctx:
                open_tag = ctx['open']
                close_tag = ctx['close']
                pos = close_tag.begin() if open_tag.contains(caret) else open_tag.begin()
                tag_pair.go_to_pos(self.view, pos)

        track_action('Go to Tag Pair')


class EmmetHideTagPreview(sublime_plugin.TextCommand):
    def run(self, edit: sublime.Edit):
        tag_pair.reset_tag_preview(self.view)


class EmmetIncrementNumber(sublime_plugin.TextCommand):
    def run(self, edit, delta=1):
        inc_dec.update(self.view, edit, delta)
        track_action('Increment number', 'delta', delta)


class EmmetRemoveTag(sublime_plugin.TextCommand):
    def run(self, edit):
        view = self.view
        for sel in view.sel():
            tag = emmet_sublime.get_tag_context(view, sel.begin())
            if tag:
                remove_tag(view, edit, tag)

        track_action('Remove Tag')


class EmmetSelectItem(sublime_plugin.TextCommand):
    def run(self, edit, previous=False):
        select_item.run_action(self.view, previous)
        track_action('Select Item', 'previous' if previous else 'next')


class EmmetSplitJoinTag(sublime_plugin.TextCommand):
    def run(self, edit):
        split_join_tag(self.view, edit)
        track_action('Split/Join Tag')


class EmmetUpdateImageSize(sublime_plugin.TextCommand):
    def run(self, edit):
        update_image_size(self.view, edit)
        caret = get_caret(self.view)
        track_action('Update Image Size', syntax.from_pos(self.view, caret))


class EmmetWrapWithAbbreviation(sublime_plugin.TextCommand):
    def run(self, edit, wrap_abbreviation):
        global last_wrap_abbreviation  # pylint: disable=global-statement
        if wrap_abbreviation:
            snippet = emmet_sublime.expand(wrap_abbreviation, self.config)
            replace_with_snippet(self.view, edit, self.region, snippet)
            last_wrap_abbreviation = wrap_abbreviation

            track_action('Wrap With Abbreviation')


    def input(self, *args, **kwargs):
        # pylint: disable=attribute-defined-outside-init
        sel = self.view.sel()[0]
        abbreviation.stop_tracking(self.view)

        self.config = wrap.get_wrap_config(self.view, sel.begin())
        self.region = wrap.get_wrap_region(self.view, sel, self.config)
        lines = wrap.get_content(self.view, self.region, True)
        self.config.user_config['text'] = lines
        preview = len(self.region) <  get_settings('wrap_size_preview', -1)

        return wrap.WrapAbbreviationInputHandler(self.view, self.region, self.config, preview)


class EmmetWrapWithAbbreviationPreview(sublime_plugin.TextCommand):
    "Internal command to preview abbreviation in text"

    def run(self, edit: sublime.Edit, region: tuple, result: str):
        r = sublime.Region(*region)
        replace_with_snippet(self.view, edit, r, result)
        self.view.show_at_center(r.begin())


class AbbreviationMarkerListener(sublime_plugin.EventListener):
    def __init__(self):
        self.pending_completions_request = False

    @main_view
    def on_close(self, editor: sublime.View):
        abbreviation.dispose_editor(editor)

    @main_view
    def on_activated(self, editor: sublime.View):
        abbreviation.handle_selection_change(editor, get_caret(editor))

    @main_view
    def on_selection_modified(self, editor: sublime.View):
        if not abbreviation.is_enabled(editor):
            return

        pos = get_caret(editor)
        trk = abbreviation.handle_selection_change(editor, pos)

        # print('sel modified at %d: %s' % (pos, trk))
        if trk:
            if trk.region.contains(pos):
                abbreviation.show_preview(editor, trk)
            else:
                abbreviation.hide_preview(editor)

    @main_view
    def on_modified(self, editor: sublime.View):
        abbreviation.handle_change(editor, get_caret(editor))
        # print('modified: %s' % trk)

    def on_query_context(self, view: sublime.View, key: str, *args):
        if key == 'emmet_abbreviation':
            # Check if caret is currently inside Emmet abbreviation
            trk = abbreviation.get_tracker(view)
            if trk:
                for s in view.sel():
                    if trk.region.contains(s):
                        return trk.forced or isinstance(trk, abbreviation.AbbreviationTrackerValid)

            return False

        if key == 'emmet_tab_expand':
            return get_settings('tab_expand', False)

        if key == 'has_emmet_abbreviation_mark':
            return bool(abbreviation.get_tracker(view))

        if key == 'has_emmet_forced_abbreviation_mark':
            trk = abbreviation.get_tracker(view)
            return trk.forced if trk else False

        return None

    def on_query_completions(self, editor: sublime.View, prefix: str, locations: list):
        pos = locations[0]
        if self.pending_completions_request:
            self.pending_completions_request = False

            tracker = abbreviation.suggest_abbreviation_tracker(editor, pos)
            if tracker:
                abbreviation.mark(editor, tracker)
                abbreviation.show_preview(editor, tracker)
                snippet = emmet_sublime.expand(tracker.abbreviation, tracker.config)
                return [('%s\tEmmet' % tracker.abbreviation, snippet)]

    def on_text_command(self, view: sublime.View, command_name: str, args: list):
        if command_name == 'auto_complete' and abbreviation.is_enabled(view):
            self.pending_completions_request = True
        elif command_name == 'commit_completion':
            abbreviation.stop_tracking(view)

    def on_post_text_command(self, editor: sublime.View, command_name: str, args: list):
        if command_name == 'auto_complete':
            self.pending_completions_request = False
        elif command_name == 'undo':
            # In case of undo, editor may restore previously marked range.
            # If so, restore marker from it
            trk = abbreviation.get_stored_tracker(editor)
            if trk and isinstance(trk, abbreviation.AbbreviationTrackerValid) and \
                editor.substr(trk.region) == trk.abbreviation:
                abbreviation.restore_tracker(editor, get_caret(editor))


class ToggleCommentListener(sublime_plugin.EventListener):
    def on_text_command(self, view, command_name, args):
        if command_name == 'toggle_comment' and comment.allow_emmet_comments(view):
            return ('emmet_toggle_comment', None)
        return None


class PreviewTagPair(sublime_plugin.EventListener):
    def on_query_context(self, view: sublime.View, key: str, *args):
        if key == 'emmet_tag_preview':
            return tag_pair.has_preview(view)
        return None

    @tag_pair.allow_preview
    def on_selection_modified_async(self, view: sublime.View):
        tag_pair.handle_selection_change(view)


class SelectItemListener(sublime_plugin.EventListener):
    def on_modified_async(self, view: sublime.View):
        select_item.reset_model(view)

    def on_post_text_command(self, view, command_name, args):
        if command_name != 'emmet_select_item':
            select_item.reset_model(view)
