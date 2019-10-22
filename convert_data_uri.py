import os.path
import sublime
import sublime_plugin
import base64
from . import emmet
from . import utils

mime_types = {
    '.gif' : 'image/gif',
    '.png' : 'image/png',
    '.jpg' : 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.svg' : 'image/svg+xml',
    '.webp' : 'image/webp',
}

class ConvertDataUrl(sublime_plugin.TextCommand):
    def run(self, edit):
        caret = utils.get_caret(self.view)
        tag = emmet.tag(utils.get_content(self.view), caret)

        if tag and tag['name'].lower() == 'img' and 'attributes' in tag:
            src_attr = next((a for a in tag['attributes'] if a['name'] == 'src'), None)
            src = src_attr and utils.attribute_value(src_attr)
            if not src:
                return

            if src.startswith('data:'):
                print('Should convert from data URL')
            else:
                convert_to_data_url(self.view, edit, src_attr, src)


def convert_to_data_url(view: sublime.View, edit: sublime.Edit, attr: dict, src: str):
    max_size = view.settings().get('emmet_max_data_url', 0)

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
            base, ext = os.path.splitext(abs_file)
            if ext in mime_types:
                new_src = 'data:%s;base64,%s' % (mime_types[ext], base64.urlsafe_b64encode(data).decode('utf8'))
                r = utils.attribute_region(attr)
                view.replace(edit, r, utils.patch_attribute(attr, new_src))
