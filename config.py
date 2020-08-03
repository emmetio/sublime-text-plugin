import sublime
from . import syntax
from .emmet import Config

# Cache for storing internal Emmet data
emmet_cache = {}
settings = None

def get_settings(key: str, default=None):
    "Returns value of given Emmet setting"
    global settings

    if settings is None:
        settings = sublime.load_settings('Emmet.sublime-settings')
        settings.add_on_change('config', handle_settings_change)

    return settings.get(key, default)


def handle_settings_change():
    global emmet_cache
    emmet_cache = {}


def field(index: int, placeholder: str, **kwargs):
    "Produces tabstops for editor"
    if placeholder:
        return '${%d:%s}' % (index, placeholder)
    return '${%d}' % index


def field_preview(index: int, placeholder: str, **kwargs):
    "Produces tabstops for abbreviation preview"
    return placeholder


def get_config(view: sublime.View, pos: int, params: dict = None) -> Config:
    "Returns Emmet options for given character location in editor"
    syntax_name = syntax.from_pos(view, pos)
    options = get_output_options(view)
    if syntax.is_jsx(syntax_name):
        options['jsx.enabled'] = True

    payload = {
        'type': syntax.get_type(syntax_name),
        'syntax': syntax_name or 'html',
        'options': options,
        'cache': emmet_cache
    }
    if params:
        payload.update(params)
    return Config(payload, get_settings('config'))


def get_preview_config(config: Config) -> Config:
    preview_config = Config(config.user_config, get_settings('config'))
    preview_config.options['output.field'] = field_preview
    preview_config.context = config.context
    return preview_config


def get_output_options(view: sublime.View, inline=False):
    "Returns Emmet output options for given location in editor"
    opt = {
        'output.field': field,
        'output.format': not inline,
        'output.attributeQuotes': get_settings('attribute_quotes')
    }

    if syntax.doc_syntax(view) == 'html':
        opt['output.selfClosingStyle'] = get_settings('markup_style')
        opt['output.compactBoolean'] = get_settings('markup_style') == 'html'

    if get_settings('comment'):
        opt['comment.enabled'] = True
        template = get_settings('comment_template')
        if template:
            opt['comment.after'] = template

    opt['bem.enabled'] = get_settings('bem')
    opt['stylesheet.shortHex'] = get_settings('short_hex')

    return opt
