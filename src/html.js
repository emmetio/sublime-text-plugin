import { scan, attributes, createOptions } from '@emmetio/html-matcher';
import { pushRange, isSpace } from './utils';

/**
 * @typedef {[number, number]} Range
 * @typedef {import('@emmetio/html-matcher/dist/attributes').AttributeToken} AttributeToken
 * @typedef {{name: string, start: number, end: number, ranges: Range[], selfClose: boolean}} SelectTagModel
 */

/**
 * Returns context tag for given position in code. If open or self-closed tag found,
 * returns parsed attributes as well
 * @param {string} code
 * @param {number} pos
 * @return {Object | undefined}
 */
export function contextTag(code, pos) {
    let tag = null;
    const opt = createOptions();
    // Find open or self-closing tag, closest to given position
    scan(code, (name, type, start, end) => {
        if (start < pos && end > pos) {
            tag = { name, type, start, end };
            if (type === 1 || type === 3) {
                tag.attributes = shiftAttributeRanges(attributes(code.slice(start, end), name), start)
            }

            return false;
        }
        if (end > pos) {
            return false;
        }
    }, opt.special);

    return tag;
}

/**
 * Returns list of ranges for Select Next/Previous Item action
 * @param {string} code
 * @param {number} pos
 * @param {boolean} isPrev
 * @returns {Range[] | undefined}
 */
export function selectItem(code, pos, isPrev) {
    return isPrev ? selectPreviousItem(code, pos) : selectNextItem(code, pos);
}

/**
 * Returns list of ranges for Select Next Item action
 * @param {string} code
 * @param {number} pos
 * @return {Range[] | undefined}
 */
function selectNextItem(code, pos) {
    /** @type {Range[] | null} */
    let ranges = null;
    const opt = createOptions();
    // Find open or self-closing tag, closest to given position
    scan(code, (name, type, start, end) => {
        if ((type === 1 || type === 3) && end > pos) {
            // Found open or self-closing tag
            ranges = getTagSelectionModel(code, name, start, end);
            return false;
        }
    }, opt.special);

    return ranges;
}

/**
 * Returns list of ranges for Select Previous Item action
 * @param {string} code
 * @param {number} pos
 * @return {Range[] | undefined}
 */
function selectPreviousItem(code, pos) {
    const opt = createOptions();
    let lastType = null, lastName = null, lastStart = null, lastEnd = null;

    // We should find the closest open or self-closing tag left to given `pos`.
    scan(code, (name, type, start, end) => {
        if (start >= pos) {
            return false;
        }

        if (type === 1 || type === 3) {
            // Found open or self-closing tag
            lastName = name;
            lastType = type;
            lastStart = start;
            lastEnd = end;
        }
    }, opt.special);

    if (lastType != null) {
        return getTagSelectionModel(code, lastName, lastStart, lastEnd);
    }
}

/**
 * Parses open or self-closing tag in `start:end` range of `code` and returns its
 * model for selecting items
 * @param {string} code Document source code
 * @param {string} name Name of matched tag
 * @param {number} start Range in `code` of matched tag
 * @param {number} end
 * @returns {Range[]}
 */
function getTagSelectionModel(code, name, start, end) {
    /** @type {Range[]} */
    const ranges = [
        // Add tag name range
        [start + 1, start + 1 + name.length]
    ];

    // Parse and add attributes ranges
    const tagSrc = code.slice(start, end);
    for (const attr of attributes(tagSrc, name)) {
        if (attr.value != null) {
            // Attribute with value
            pushRange(ranges, [start + attr.nameStart, start + attr.valueEnd]);

            // Add (unquoted) value range
            const val = valueRange(attr);
            if (val[0] !== val[1]) {
                pushRange(ranges, [start + val[0], start + val[1]]);

                if (attr.name === 'class') {
                    // For class names, split value into space-separated tokens
                    const tokens = tokenList(tagSrc.slice(val[0], val[1]), start + val[0]);
                    for (const token of tokens) {
                        pushRange(ranges, token);
                    }
                }
            }
        } else {
            // Attribute without value (boolean)
            pushRange(ranges, [start + attr.nameStart, start + attr.nameEnd]);
        }
    }

    return ranges;
}

/**
 * Returns ranges of tokens in given value. Tokens are space-separated words.
 * @param {string} value
 * @returns {Range[]}
 */
function tokenList(value, offset = 0) {
    /** @type {Range[]} */
    const ranges = [];
    const len = value.length;
    let pos = 0;
    let start = 0, end = 0;
    while (pos < len) {
        end = pos;
        const ch = value.charCodeAt(pos++);
        if (isSpace(ch)) {
            if (start !== end) {
                ranges.push([offset + start, offset + end]);
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

/**
 * @param {AttributeToken[]} attrs
 * @param {number} offset
 * @returns {AttributeToken[]}
 */
function shiftAttributeRanges(attrs, offset) {
    attrs.forEach(attr => {
        attr.nameStart += offset;
        attr.nameEnd += offset;
        if ('value' in attr) {
            attr.valueStart += offset;
            attr.valueEnd += offset;
        }
    });
    return attrs;
}
