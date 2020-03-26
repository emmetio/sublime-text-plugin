import sublime
from . import utils

cache = {}

class RegionTracker:
    __slots__ = ('last_pos', 'last_length', 'region', 'forced', 'config',
                 'abbreviation', 'forced_indicator')

    def __init__(self, start: int, pos: int, length: int, forced=False):
        self.last_pos = pos
        self.last_length = length
        self.forced = forced
        self.region = sublime.Region(start, pos)
        self.config = None
        self.abbreviation = None
        self.forced_indicator = None


def handle_change(view: sublime.View):
    tracker = get_tracker(view)
    if not tracker:
        return

    last_pos = tracker.last_pos
    region = tracker.region

    if last_pos < region.a or last_pos > region.b:
        # Updated content outside abbreviation: reset tracker
        stop_tracking(view)
        return

    length = view.size()
    pos = utils.get_caret(view)
    delta = length - tracker.last_length

    tracker.last_length = length
    tracker.last_pos = pos

    print('tracker >> handle delta %d, last pos: %d, pos: %d' % (delta, last_pos, pos))

    if delta < 0:
        # Removed some content
        if last_pos == region.a:
            # Updated content at the abbreviation edge
            region.a += delta
            region.b += delta
        elif region.a < last_pos <= region.b:
            region.b += delta
    elif delta > 0:
        # Inserted content
        if region.a <= last_pos <= region.b:
            # Inserted content in abbreviation
            region.b += delta

    # Ensure range is in valid state
    if region.b < region.a or (region.a == region.b and not tracker.forced):
        stop_tracking(view)
    else:
        print('new tracker region is %s' % tracker.region)
        return tracker


def handle_selection_change(view: sublime.View, caret=None):
    tracker = get_tracker(view)
    if tracker:
        if caret is None:
            caret = utils.get_caret(view)
        tracker.last_pos = caret


def get_tracker(view: sublime.View) -> RegionTracker:
    "Returns current abbreviation tracker for given editor, if available"
    return cache.get(view.id())


def start_tracking(view: sublime.View, start: int, pos: int, forced=False) -> RegionTracker:
    """
    Starts abbreviation tracking for given editor
    :param start Location of abbreviation start
    :param pos Current caret position, must be greater that `start`
    """
    tracker = RegionTracker(start, pos, view.size(), forced)
    cache[view.id()] = tracker
    return tracker

def stop_tracking(view: sublime.View):
    key = view.id()
    if key in cache:
        del cache[key]
