import re
import base64
import os
import os.path
import sublime
from . import emmet_sublime as emmet
from . import utils
from ..emmet.html_matcher import AttributeToken
from ..emmet.action_utils import CSSProperty

mime_types = {
    '.gif' : 'image/gif',
    '.png' : 'image/png',
    '.jpg' : 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.svg' : 'image/svg+xml',
    '.webp' : 'image/webp',
}

def convert_html(view: sublime.View, edit: sublime.Edit, pos: int):
    "Convert to/from data:URL for HTML context"
    tag = emmet.tag(utils.get_content(view), pos)

    if tag and tag.name.lower() == 'img' and tag.attributes:
        src_attr = next((a for a in tag.attributes if a.name == 'src'), None)

        # Get region of attribute value
        region = src_attr and attr_value_region(src_attr)

        if region:
            toggle_url(view, edit, region)


def convert_css(view: sublime.View, edit: sublime.Edit, pos: int):
    "Convert to/from data:URL for CSS context"
    section = emmet.css_section(utils.get_content(view), pos, True)

    if not section:
        return

    # Find value token with `url(...)` value under caret
    for p in section.properties:
        # If value matches caret location, find url(...) token for it
        if p.value.contains(pos):
            token = get_url_region(view, p, pos)
            if token:
                toggle_url(view, edit, token)
            break


def toggle_url(view: sublime.View, edit: sublime.Edit, region: sublime.Region):
    "Toggles URL state for given region: either convert it to data:URL or store as file"
    src = view.substr(region)

    if src.startswith('data:'):
        on_done = lambda text: convert_from_data_url(view, region, text)
        view.window().show_input_panel('Enter file name', 'image%s' % get_ext(src), on_done, None, None)
    else:
        convert_to_data_url(view, edit, region)


def convert_to_data_url(view: sublime.View, edit: sublime.Edit, region: sublime.Region):
    max_size = emmet.get_settings('max_data_url', 0)
    src = view.substr(region)
    abs_file = None

    if utils.is_url(src):
        abs_file = src
    elif view.file_name():
        abs_file = utils.locate_file(view.file_name(), src)
        if abs_file and max_size and os.path.getsize(abs_file) > max_size:
            print('Size of %s file is too large. Check "emmet_max_data_url" setting to increase this limit' % abs_file)
            return

    if abs_file:
        data = utils.read_file(abs_file)
        if data and (not max_size or len(data) <= max_size):
            ext = os.path.splitext(abs_file)[1]
            if ext in mime_types:
                new_src = 'data:%s;base64,%s' % (mime_types[ext], base64.urlsafe_b64encode(data).decode('utf8'))
                view.replace(edit, region, new_src)


def convert_from_data_url(view: sublime.View, region: sublime.Region, dest: str):
    src = view.substr(region)
    m = re.match(r'^data\:.+?;base64,(.+)', src)
    if m:
        base_dir = os.path.dirname(view.file_name())
        abs_dest = utils.create_path(base_dir, dest)
        file_url = os.path.relpath(abs_dest, base_dir).replace('\\', '/')

        dest_dir = os.path.dirname(abs_dest)
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)

        with open(abs_dest, 'wb') as fd:
            fd.write(base64.urlsafe_b64decode(m.group(1)))

        view.run_command('convert_data_url_replace', {
            'region': [region.begin(), region.end()],
            'text': file_url
        })


def attr_value_region(attr: AttributeToken) -> sublime.Region:
    "Returns clean (unquoted) value region of given attribute"
    if attr.value is not None:
        start = attr.value_start
        end = attr.value_end
        if utils.is_quoted(attr.value):
            start += 1
            end -= 1
        return sublime.Region(start, end)
    return None


def get_url_region(view: sublime.View, css_prop: CSSProperty, pos: int) -> sublime.Region:
    "Returns region of matched `url()` token from given value"
    for v in css_prop.value_tokens:
        m = re.match(r'url\([\'"]?(.+?)[\'"]?\)', view.substr(v)) if v.contains(pos) else None
        if m:
            return sublime.Region(v.begin() + m.start(1), v.begin() + m.end(1))
    return None


def get_ext(data_url: str):
    "Returns suggested extension from given data:URL string"
    m = re.match(r'data:(.+?);', data_url)
    if m:
        for key, value in mime_types.items():
            if value == m.group(1):
                return key
    return '.jpg'
