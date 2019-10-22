import re
import io
import struct
import os.path
import sublime
import sublime_plugin
from . import emmet
from . import utils

class UpdateImageSize(sublime_plugin.TextCommand):
    def run(self, edit):
        caret = utils.get_caret(self.view)
        tag = emmet.tag(utils.get_content(self.view), caret)
        if tag and tag['name'].lower() == 'img' and 'attributes' in tag:
            attrs = dict([(a['name'].lower(), a) for a in tag['attributes']])

            if 'src' in attrs and attrs['src'].get('value'):
                src = utils.attribute_value(attrs['src'])
                if utils.is_url(src):
                    abs_file = src
                elif self.view.file_name():
                    abs_file = utils.locate_file(self.view.file_name(), src)

                if abs_file:
                    size = read_image_size(abs_file)
                    if size:
                        dpi = get_dpi(src)
                        width = round(size[0] / dpi)
                        height = round(size[1] / dpi)

                        update_html_size(attrs, self.view, edit, width, height)
                    else:
                        print('Unable to determine size of "%s": file is either unsupported or invalid')
                else:
                    print('Unable to locate file for "%s" url' % src)

def get_dpi(file_path):
    "Detects file DPI from given file path"
    name, ext = os.path.splitext(file_path)

    # If file name contains DPI suffix like `@2x`, use it to scale down image size
    m = re.search(r'@(\d+(?:\.\d+))x$', name)
    return m and float(m.group(1)) or 1


def read_image_size(file_path):
    "Reads image size of given file, if possible"
    file_name = os.path.basename(file_path)
    name, ext = os.path.splitext(file_name)
    chunk = ext.lower() in ('.svg', '.jpg', '.jpeg') and 2048 or 100
    data = utils.read_file(file_path, chunk)
    return get_size(data)


def update_html_size(attrs: dict, view: sublime.View, edit: sublime.Edit, width: int, height: int):
    "Updates image size of HTML tag"
    width = str(width)
    height = str(height)
    width_attr = attrs.get('width')
    height_attr = attrs.get('height')

    if width_attr and height_attr:
        # We have both attributes, patch them
        wr = utils.attribute_region(width_attr)
        hr = utils.attribute_region(height_attr)
        if wr.begin() < hr.begin():
            view.replace(edit, hr, utils.patch_attribute(height_attr, height))
            view.replace(edit, wr, utils.patch_attribute(width_attr, width))
        else:
            view.replace(edit, wr, utils.patch_attribute(width_attr, width))
            view.replace(edit, hr, utils.patch_attribute(height_attr, height))
    elif width_attr or height_attr:
        # Use existing attribute and replace it with patched variations
        attr = width_attr or height_attr
        data = '%s %s' % (utils.patch_attribute(attr, width, 'width'), utils.patch_attribute(attr, height, 'height'))
        view.replace(edit, utils.attribute_region(attr), data)
    elif 'src' in attrs:
        # At least 'src' attribute should be available
        attr = attrs['src']
        pos = attr.get('valueEnd', attr['nameEnd'])
        data = ' %s %s' % (utils.patch_attribute(attr, width, 'width'), utils.patch_attribute(attr, height, 'height'))
        view.insert(edit, pos, data)


def get_size(data: bytes):
    """
    Returns size of given image fragment, if possible.
    Based on image_size script by Paulo Scardine: https://github.com/scardine/image_size
    """
    size = len(data)
    if size >= 10 and data[:6] in (b'GIF87a', b'GIF89a'):
        # GIFs
        w, h = struct.unpack("<HH", data[6:10])
        return int(w), int(h)
    elif size >= 24 and data.startswith(b'\211PNG\r\n\032\n') and data[12:16] == b'IHDR':
        # PNGs
        w, h = struct.unpack(">LL", data[16:24])
        return int(w), int(h)
    elif size >= 16 and data.startswith(b'\211PNG\r\n\032\n'):
        # older PNGs
        w, h = struct.unpack(">LL", data[8:16])
        return int(w), int(h)
    elif size >= 30 and data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        # WebP
        webp_type = data[12:16]
        if webp_type == b'VP8 ': # Lossy WebP (old)
            w, h = struct.unpack("<HH", data[26:30])
        elif webp_type == b'VP8L': # Lossless WebP
            bits = struct.unpack("<I", data[21:25])[0]
            w = int(bits & 0x3FFF) + 1
            h = int((bits >> 14) & 0x3FFF) + 1
        elif webp_type == b'VP8X': # Extended WebP
            w = int((data[26] << 16) | (data[25] << 8) | data[24]) + 1
            h = int((data[29] << 16) | (data[28] << 8) | data[27]) + 1
        return w, h

    elif b'<svg' in data:
        # SVG
        start = data.index(b'<svg')
        end = data.index(b'>', start)
        svg = str(data[start:end + 1], 'utf8')
        w = re.search(r'width=["\'](\d+)', svg)
        h = re.search(r'height=["\'](\d+)', svg)
        if w and h:
            return int(w.group(1)), int(h.group(1))
    elif size >= 2 and data.startswith(b'\377\330'):
        # JPEG
        with io.BytesIO(data) as input:
            input.seek(0)
            input.read(2)
            b = input.read(1)
            while (b and ord(b) != 0xDA):
                while (ord(b) != 0xFF):
                    b = input.read(1)
                while (ord(b) == 0xFF):
                    b = input.read(1)
                if (ord(b) >= 0xC0 and ord(b) <= 0xC3):
                    input.read(3)
                    h, w = struct.unpack(">HH", input.read(4))
                    break
                else:
                    input.read(int(struct.unpack(">H", input.read(2))[0]) - 2)
                b = input.read(1)
            return int(w), int(h)
