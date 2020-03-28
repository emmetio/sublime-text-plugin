import sublime

__doc__ = "Syntax-related methods"

markup_syntaxes = ['html', 'xml', 'xsl', 'jsx', 'haml', 'jade', 'pug', 'slim']
stylesheet_syntaxes = ['css', 'scss', 'sass', 'less', 'sss', 'stylus', 'postcss']
xml_syntaxes = ['xml', 'xsl', 'jsx']
html_syntaxes = ['html']

# NB: avoid circular reference for `emmet_sublime` module,
# create own settings instance
settings = None

def get_settings(key: str, default=None):
    "Returns value of given Emmet setting"
    global settings

    if settings is None:
        settings = sublime.load_settings('Emmet.sublime-settings')

    return settings.get(key, default)


def info(view: sublime.View, pt: int, fallback=None):
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


def from_pos(view: sublime.View, pt: int):
    "Returns Emmet syntax for given location in view"
    scopes = get_settings('syntax_scopes', {})
    if scopes:
        for name, sel in scopes.items():
            if view.match_selector(pt, sel):
                return name

    return None


def is_xml(syntax: str):
    "Check if given syntax is XML dialect"
    return syntax in xml_syntaxes


def is_html(syntax: str):
    "Check if given syntax is HTML dialect (including XML)"
    return syntax in html_syntaxes or is_xml(syntax)


def is_supported(syntax: str):
    "Check if given syntax name is supported by Emmet"
    return syntax in markup_syntaxes or syntax in stylesheet_syntaxes


def is_css(syntax: str):
    """
    Check if given syntax is a CSS dialect. Note that it’s not the same as stylesheet
    syntax: for example, SASS is a stylesheet but not CSS dialect (but SCSS is)
    """
    return syntax in ('css', 'scss', 'less')

def is_jsx(syntax: str):
    "Check if given syntax is JSX"
    return syntax == 'jsx'

def is_inline(view: sublime.View, pt: int):
    "Check if abbreviation in given location must be expanded as single line"
    scopes = get_settings('inline_scopes', [])
    return matches_selector(view, pt, scopes)


def in_activation_scope(view: sublime.View, pt: int):
    """
    Check if given location in view can be used for abbreviation marker activation.
    Note that this method implies that caret is in Emmet-supported syntax
    """
    ignore = get_settings('ignore_scopes', [])
    if matches_selector(view, pt, ignore):
        return False

    scopes = get_settings('abbreviation_scopes', [])
    return matches_selector(view, pt, scopes)


def matches_selector(view: sublime.View, pt: int, selectors: list):
    "Check if given location in view one of the given selectors"
    for sel in selectors:
        if view.match_selector(pt, sel):
            return True

    return False
