import urllib
import sublime
from .config import get_settings

__doc__ = "Telemetry module: sends anonymous Emmet usage stats to improve user experience"

TRACK_ID = 'UA-171521327-1'
HOST = 'https://www.google-analytics.com/batch'
MAX_BATCH = 20


scheduled = False
queue = []
"Queue for pending tracking records"


def track_action(action: str, label: str = None, value: str = None):
    payload = {
        't': 'event',
        'ec': 'Actions',
        'ea': action
    }

    if label is not None:
        payload['el'] = label

    if value is not None:
        payload['ev'] = value

    push_queue(payload)


def push_queue(item: dict):
    queue.append(item)
    schedule_send()


def schedule_send():
    global scheduled
    if not scheduled:
        scheduled = True
        sublime.set_timeout_async(_flush_queue, 30000)


def get_user_agent():
    platforms = {
        'osx': 'Macintosh',
        'linux': 'X11; Linux',
        'windows': 'Windows NT 10.0; Win64; x64'
    }

    try:
        version = sublime.load_resource('/'.join(['Packages', __package__, 'VERSION']))
    except:
        version = '1.0.0'

    return 'Mozilla/5.0 (%s) EmmetTracker/%s' % (platforms.get(sublime.platform()), version.strip())


def _flush_queue():
    global scheduled, queue
    scheduled = False
    _queue = queue[:MAX_BATCH]
    queue = queue[MAX_BATCH:]
    entries = []

    for q in _queue:
        params = {'v': 1, 'tid': TRACK_ID, 'cid': get_settings('uid', '000')}
        params.update(q)
        entries.append(urllib.parse.urlencode(params))

    data = '\n'.join(entries).encode('ascii')
    req = urllib.request.Request(
        HOST,
        data,
        method='POST',
        headers={
        'User-Agent': get_user_agent(),
        'Content-Length': len(data)
    })
    # print('send req %s to %s as %s' % (req, HOST, ua))
    # print('payload: %s' % data)

    try:
        with urllib.request.urlopen(req):
            # print('status: %s' % res.status)
            pass
    except:
        pass

    if queue:
        # print('schedule next request')
        schedule_send()
