import expandAbbreviation, { markupAbbreviation, stylesheetAbbreviation, resolveConfig } from 'emmet';

export { extract } from 'emmet';

const reSimple = /^([\w!-]+)\.?$/;
const knownTags = [
    'a', 'abbr', 'address', 'area', 'article', 'aside', 'audio',
    'b', 'base', 'bdi', 'bdo', 'blockquote', 'body', 'br', 'button',
    'canvas', 'caption', 'cite', 'code', 'col', 'colgroup', 'content',
    'data', 'datalist', 'dd', 'del', 'details', 'dfn', 'dialog', 'div', 'dl', 'dt',
    'em', 'embed',
    'fieldset', 'figcaption', 'figure', 'footer', 'form',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'head', 'header', 'hr', 'html',
    'i', 'iframe', 'img', 'input', 'ins',
    'kbd', 'keygen',
    'label', 'legend', 'li', 'link',
    'main', 'map', 'mark', 'menu', 'menuitem', 'meta', 'meter',
    'nav', 'noscript',
    'object', 'ol', 'optgroup', 'option', 'output',
    'p', 'param', 'picture', 'pre', 'progress',
    'q',
    'rp', 'rt', 'rtc', 'ruby',
    's', 'samp', 'script', 'section', 'select', 'shadow', 'slot', 'small', 'source', 'span', 'strong', 'style', 'sub', 'summary', 'sup',
    'table', 'tbody', 'td', 'template', 'textarea', 'tfoot', 'th', 'thead', 'time', 'title', 'tr', 'track',
    'u', 'ul', 'var', 'video', 'wbr'
];

/**
 * @param {number} index
 * @param {string} placeholder
 * @returns {string}
 */
function field(index, placeholder) {
    return `\${${index}${placeholder ? `:${placeholder}` : ''}}`;
}

/**
 * @param {number} index
 * @param {string} placeholder
 * @returns {string}
 */
function fieldPreview(index, placeholder) {
    return placeholder;
}

/**
 * @param {string} str
 * @returns {string}
 */
function text(str) {
    // Escape all `$` in plain text for snippet output
    return str.replace(/\$/g, '\\$');
}

/**
 * Expands given abbreviation
 * @param {string} abbr
 * @param {import('emmet').UserConfig} [config]
 * @returns {string}
 */
export function expand(abbr, config) {
    const isPreview = config && config.preview;
    return expandAbbreviation(abbr, {
        ...config,
        options: {
            'output.field': isPreview ? fieldPreview : field,
            'output.text': text,
            ...(config && config.options),
        }
    });
}

/**
 * Validates given abbreviation and provides some insights about it
 * @param {string} abbr
 * @param {import('emmet').UserConfig} config
 */
export function validate(abbr, config) {
    config = resolveConfig(config);

    try {
        if (config.type === 'stylesheet') {
            stylesheetAbbreviation(abbr)
        } else {
            let parserConf = config;
            if (config.options['jsx.enabled']) {
                parserConf = { ...parserConf, jsx: true };
            }
            markupAbbreviation(abbr, parserConf);
        }

        const m = abbr.match(reSimple);
        return {
            valid: true,
            simple: !!m,
            matched: m ? knownTags.includes(m[1]) || (m[1] in config.snippets) : false
        };
    } catch (err) {
        let snippet = '';
        if (err.pos != null) {
            snippet = `${abbr}\n${'-'.repeat(err.pos)}^`;
        }

        return {
            valid: false,
            error: err.message,
            pos: err.pos,
            snippet
        };
    }
}
