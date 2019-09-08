import re
import sublime

re_string_scope = re.compile(r'\bstring\b')
re_source_scope = re.compile(r'\bsource\.([\w\-]+)')

markup_syntaxes = ['html', 'xml', 'xsl', 'jsx', 'haml', 'jade', 'pug', 'slim']
stylesheet_syntaxes = ['css', 'scss', 'sass', 'less', 'sss', 'stylus', 'postcss']

def is_know_syntax(syntax):
    return syntax in markup_syntaxes or syntax in stylesheet_syntaxes

def get_syntax_type(syntax):
    """
    Returns type of given syntax: either 'markup' or 'stylesheet'
    """
    return syntax in stylesheet_syntaxes and 'stylesheet' or 'markup'

def get_syntax(view: sublime.View, pt: int):
    """
    Returns context syntax for given point
    """

    scope = view.scope_name(pt)

    if not re_string_scope.search(scope):
        m = re_source_scope.search(scope)
        if m and is_know_syntax(m.group(1)):
            return m.group(1)

    # Unknown syntax, fallback to HTML
    return 'html'
