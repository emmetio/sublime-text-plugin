import expandAbbreviation, { markupAbbreviation, stylesheetAbbreviation, resolveConfig } from 'emmet';
import { balancedInward, balancedOutward, scan, attributes, createOptions } from '@emmetio/html-matcher';

export { extract } from 'emmet';
export { default as match } from '@emmetio/html-matcher';

/**
 * @typedef {{name: string, start: number, end: number, ranges: Array<[number, number]>, selfClose: boolean}} SelectTagModel
 */

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
            'output.format': !(config && config.inline),
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

        const m = abbr === '.' || abbr.match(reSimple);
        return {
            valid: true,
            simple: !!m,
            matched: m ? knownTags.includes(m[1]) || (m[1] in config.snippets) : false
        };
    } catch (err) {
        return {
            valid: false,
            error: err.message + err.stack,
            pos: err.pos,
            snippet: err.pos != null ? `${'-'.repeat(err.pos)}^` : ''
        };
    }
}

/**
 * Returns list of tags for balancing for given location
 * @param {string} code
 * @param {number} pos
 * @param {'inward' | 'outward'} dir
 * @param {import('@emmetio/html-matcher').ScannerOptions} options
 */
export function balance(code, pos, dir, options) {
    return dir === 'inward'
        ? balancedInward(code, pos, options)
        : balancedOutward(code, pos, options)
}

/**
 * Returns list of ranges for Select Next/Previous Item action
 * @param {string} code
 * @param {number} pos
 * @param {boolean} isPrev
 * @returns {SelectTagModel | undefined}
 */
export function selectItem(code, pos, isPrev) {
    return isPrev ? selectPreviousItem(code, pos) : selectNextItem(code, pos);
}

/**
 * Returns list of ranges for Select Next Item action
 * @param {string} code
 * @param {number} pos
 * @return {SelectTagModel | undefined}
 */
function selectNextItem(code, pos) {
    /** @type {SelectTagModel | null} */
    let tag = null;
    const opt = createOptions();
    // Find open or self-closing tag, closest to given position
    scan(code, (name, type, start, end) => {
        if ((type === 1 || type === 3) && end > pos) {
            // Found open or self-closing tag
            tag = getTagSelectionModel(code, name, start, end, type === 3);
            return false;
        }
    }, opt.special);

    return tag;
}

/**
 * Returns list of ranges for Select Previous Item action
 * @param {string} code
 * @param {number} pos
 * @return {SelectTagModel | undefined}
 */
function selectPreviousItem(code, pos) {
    const opt = createOptions();
    let lastType = null, lastName = null, lastStart = null, lastEnd = null;

    // We should find the closest open or self-closing tag left to given `pos`.
    scan(code, (name, type, start, end) => {
        if (start >= pos) {
            return false;
        }

        if ((type === 1 || type === 3)) {
            // Found open or self-closing tag
            lastName = name;
            lastType = type;
            lastStart = start;
            lastEnd = end;
        }
    }, opt.special);

    if (lastType != null) {
        return getTagSelectionModel(code, lastName, lastStart, lastEnd, lastType === 3);
    }
}

/**
 * Parsed open or self-closing tag in `start:end` range of `code` and returns its
 * model for selecting items
 * @param {string} code Document source code
 * @param {string} name Name of matched tag
 * @param {number} start Range in `code` of matched tag
 * @param {number} end
 * @param {boolean} selfClose Tag is self-closing
 * @returns {SelectTagModel}
 */
function getTagSelectionModel(code, name, start, end, selfClose) {
    // Found open or self-closing tag
    const ranges = [
        // Add tag name range
        [start + 1, start + 1 + name.length]
    ];

    // Parse and add attributes ranges
    const tagSrc = code.slice(start, end);
    for (const attr of attributes(tagSrc, name)) {
        if (attr.value != null) {
            // Attribute with value
            ranges.push([start + attr.nameStart, start + attr.valueEnd]);

            // Add (unquoted) value range
            const val = valueRange(attr);
            if (val[0] !== val[1]) {
                ranges.push([start + val[0], start + val[1]]);

                if (attr.name === 'class') {
                    // For class names, split value into space-separated tokens
                    const tokens = tokenList(tagSrc.slice(val[0], val[1]));
                    const offset = start + val[0];
                    for (const token of tokens) {
                        ranges.push([offset + token[0], offset + token[1]]);
                    }
                }
            }
        } else {
            // Attribute without value (boolean)
            ranges.push([start + attr.nameStart, start + attr.nameEnd]);
        }
    }

    return { name, start, end, ranges, selfClose };
}

/**
 * Returns ranges of tokens in given value. Tokens are space-separated words.
 * @param {string} value
 * @returns {Array<[number, number]>}
 */
function tokenList(value) {
    const ranges = [];
    const len = value.length;
    let pos = 0;
    let start = 0, end = 0;
    while (pos < len) {
        end = pos;
        const ch = value.charCodeAt(pos++);
        if (isSpace(ch)) {
            if (start !== end) {
                ranges.push([start, end]);
            }

            while (isSpace(value.charCodeAt(pos))) {
                pos++;
            }

            start = pos;
        }
    }

    if (start !== pos) {
        ranges.push([start, pos]);
    }

    return ranges;
}

/**
 * Returns `true` if given character code is a space
 * @param {number} code
 */
function isSpace(code) {
    return code === 32  /* space */
        || code === 9   /* tab */
        || code === 160 /* non-breaking space */
        || code === 10  /* LF */
        || code === 13; /* CR */
}

/**
 * Returns value range of given attribute. Value range is unquoted.
 * @param {import('@emmetio/html-matcher/dist/attributes').AttributeToken} attr
 * @returns {[number, number]}
 */
function valueRange(attr) {
    const ch = attr.value[0];
    const lastCh = attr.value[attr.value.length - 1];
    if (ch === '"' || ch === '\'') {
        return [
            attr.valueStart + 1,
            attr.valueEnd - (lastCh === ch ? 1 : 0)
        ];
    }

    if (ch === '{' && lastCh === '}') {
        return [
            attr.valueStart + 1,
            attr.valueEnd - 1
        ];
    }

    return [attr.valueStart, attr.valueEnd];
}
