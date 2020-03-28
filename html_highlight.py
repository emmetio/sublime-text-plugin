import re
import html
from .emmet.html_matcher import scan, get_attributes, ElementType

re_tag_end = re.compile(r'\s*\/?>$')

def highlight(code: str) -> str:
    chunks = []
    offset = [0]

    def cb(name: str, elem_type: int, start: int, end: int):
        if offset[0] != start:
            chunks.append(escape(code[offset[0]:start]))
        offset[0] = end

        if elem_type == ElementType.Close:
            chunks.append('<span class="tag close">&lt;/<span class="tag-name">%s</span>&gt;</span>' % name)
        else:
            chunks.append('<span class="tag open">&lt;<span class="tag-name">%s</span>' % name)
            for attr in get_attributes(code, start, end, name):
                chunks.append(' <span class="attr">')
                chunks.append('<span class="attr-name">%s</span>' % attr.name)
                if attr.value is not None:
                    chunks.append('=<span class="attr-value">%s</span>' % attr.value)
                chunks.append('</span>')

            tag_end = re_tag_end.search(code[start:end])
            if tag_end:
                chunks.append(escape(tag_end.group(0)))
            chunks.append('</span>')

    scan(code, cb)
    chunks.append(escape(code[offset[0]:]))

    return ''.join(chunks)


def styles():
    return """
    .dark .tag { color: #77c7b4; }
    .dark .attr-name { color: #8fd260; }
    .dark .attr-value { color: #ff6e61; }

    .light .tag { color: #0046aa; }
    .light .attr-name { color: #017ab7; }
    .light .attr-value { color: #017ab7; }
    """


def escape(code: str):
    return html.escape(code, False)
