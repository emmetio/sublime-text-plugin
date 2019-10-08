"""
Syntax-related methods
"""

# Editor scope to Emmet syntax mapping
syntax_scopes = {
    'html': 'text.html - source - meta.attribute-with-value.style',
    'xml': 'text.xml - text.xml.xsl',
    'xsl': 'text.xml.xsl',
    'jsx': 'source.js.jsx',
    'haml': 'source.haml',
    'jade': 'text.jade | source.pyjade',
    'pug': 'text.pug | source.pypug',
    'slim': 'text.slim',

    'css': 'source.css | meta.attribute-with-value.style.html string.quoted',
    'sass': 'source.sass',
    'scss': 'source.scss',
    'less': 'source.less',
    'stylus': 'source.stylus',
    'sss': 'source.sss'
}

# List of scopes with inline context
inline_scopes = [
    'meta.attribute-with-value.style.html'
]

# List of scope selectors where abbreviation marker should be activated,
# e.g. plugin will mark text that user types as abbreviation
marker_activation_scopes = [
    'text - (entity, punctuation.definition.tag.end)',
    'source - meta.selector - meta.property-value - meta.property-name - string - punctuation - comment',
    # Inline CSS
    'text.html meta.attribute-with-value.style string.quoted'
]

markup_syntaxes = ['html', 'xml', 'xsl', 'jsx', 'haml', 'jade', 'pug', 'slim']
stylesheet_syntaxes = ['css', 'scss', 'sass', 'less', 'sss', 'stylus', 'postcss']
xml_syntaxes = ['xml', 'xsl', 'jsx']
html_syntaxes = ['html']

def info(view, pt, fallback=None):
    """
    Returns Emmet syntax info for given location in view.
    Syntax info is an abbreviation type (either 'markup' or 'stylesheet') and syntax
    name, which is used to apply syntax-specific options for output.

    By default, if given location doesn’t match any known context, this method
    returns `None`, but if `fallback` argument is provided, it returns data for
    given fallback syntax
    """
    syntax = from_pos(view, pt) or fallback
    if syntax:
        return {
            'syntax':  syntax,
            'type': syntax in stylesheet_syntaxes and 'stylesheet' or 'markup'
        }


def from_pos(view, pt):
    "Returns Emmet syntax for given location in view"
    for name, sel in syntax_scopes.items():
        if view.match_selector(pt, sel):
            return name

    return None


def is_xml(syntax):
    "Check if given syntax is XML dialect"
    return syntax in xml_syntaxes


def is_html(syntax):
    "Check if given syntax is HTML dialect (including XML)"
    return syntax in html_syntaxes or is_xml(syntax)


def is_supported(syntax):
    "Check if given syntax name is supported by Emmet"
    return syntax in markup_syntaxes or syntax in stylesheet_syntaxes


def is_inline(view, pt):
    "Check if abbreviation in given location must be expanded as single line"
    return matches_selector(view, pt, inline_scopes)


def in_activation_scope(view, pt):
    """
    Check if given location in view can be used for abbreviation marker activation.
    Note that this method implies that caret is in Emmet-supported syntax
    """
    return matches_selector(view, pt, marker_activation_scopes)


def matches_selector(view, pt, selectors):
    "Check if given location in view one of the given selectors"
    for sel in selectors:
        if view.match_selector(pt, sel):
            return True

    return False
