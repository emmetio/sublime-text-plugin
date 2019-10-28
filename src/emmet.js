import expandAbbreviation, { markupAbbreviation, stylesheetAbbreviation, resolveConfig } from 'emmet';
import { balancedInward, balancedOutward } from '@emmetio/html-matcher';
import { balancedInward as balancedInwardCSS, balancedOutward as balancedOutwardCSS } from '@emmetio/css-matcher';
import evaluateMath, { extract as extractMath } from '@emmetio/math-expression';

export { extract } from 'emmet';
export { default as match } from '@emmetio/html-matcher';
export { default as matchCSS } from '@emmetio/css-matcher';
export { contextTag, selectItem } from './html';
export { contextSection, selectItemCSS } from './css';

/**
 * @typedef {[number, number]} Range
 * @typedef {import('@emmetio/html-matcher/dist/attributes').AttributeToken} AttributeToken
 * @typedef {{name: string, start: number, end: number, ranges: Range[], selfClose: boolean}} SelectTagModel
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
 * @param {EmmetUserConfig} [config]
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
 * @param {EmmetUserConfig} config
 */
export function validate(abbr, config) {
    /** @type {EmmetConfig} */
    const resolved = resolveConfig(config);

    try {
        if (resolved.type === 'stylesheet') {
            stylesheetAbbreviation(abbr)
        } else {
            let parserConf = resolved;
            if (resolved.options['jsx.enabled']) {
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
        : balancedOutward(code, pos, options);
}

/**
 * Returns list of selector/property ranges for balancing for given location
 * @param {string} code
 * @param {number} pos
 * @param {'inward' | 'outward'} dir
 */
export function balanceCSS(code, pos, dir) {
    return dir === 'inward'
        ? balancedInwardCSS(code, pos)
        : balancedOutwardCSS(code, pos);
}

/**
 * Locates math expression from given `pos` and evaluates it.
 * On success, returns object with, `start`, `end` and `result` properties
 * @param {string} code
 * @param {number} pos
 * @param {Object} [options] Extract options
 */
export function math(code, pos, options) {
    const range = extractMath(code, pos, options);
    if (range) {
        try {
            const [start, end] = range;
            return { start, end, result: evaluateMath(code.substring(start, end)) }
        } catch (err) {}
    }
}
