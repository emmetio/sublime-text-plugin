import { scan, splitValue } from '@emmetio/css-matcher';
import { pushRange } from './utils';

/**
 * Returns context CSS section for given location in source code
 * @param {string} code
 * @param {number} pos
 * @returns {CSSSection | null}
 */
export function contextSection(code, pos) {
    /** @type {CSSTokenRange[]} */
    const stack = [];
    /** @type {CSSTokenRange[]} */
    const pool = [];
    /** @type {CSSSection} */
    let result = null;
    scan(code, (type, start, end, delimiter) => {
        if (start > pos && !stack.length) {
            return false;
        }

        if (type === 'selector') {
            stack.push(allocRange(pool, start, end, delimiter));
        } else if (type === 'blockEnd') {
            const sel = stack.pop();
            if (sel && sel[0] <= pos && pos <= end) {
                result = {
                    start: sel[0],
                    end,
                    bodyStart: sel[2],
                    bodyEnd: start
                };
                return false;
            }
            releaseRange(pool, sel);
        }
    });

    return result;
}

/**
 * Returns list of ranges for Select Next/Previous CSS Item  action
 * @param {string} code
 * @param {number} pos
 * @param {boolean} isPrev
 * @returns {SelectItemModel | void}
 */
export function selectItemCSS(code, pos, isPrev) {
    return isPrev ? selectPreviousItem(code, pos) : selectNextItem(code, pos);
}

/**
 * Returns regions for selecting next item in CSS
 * @param {string} code
 * @param {number} pos
 * @returns {SelectItemModel | void}
 */
export function selectNextItem(code, pos) {
    /** @type {SelectItemModel} */
    let result = null;
    /** @type {CSSTokenRange} */
    let pendingProperty = null;

    scan(code, (type, start, end, delimiter) => {
        if (start < pos) {
            return;
        }

        if (type === 'selector') {
            result = { start, end, ranges: [[start, end]] };
            return false;
        } else if (type === 'propertyName') {
            pendingProperty = [start, end, delimiter];
        } else if (type === 'propertyValue') {
            result = {
                start,
                end: delimiter !== -1 ? delimiter + 1 : end,
                ranges: []
            };
            if (pendingProperty) {
                // Full property range
                result.start = pendingProperty[0];
                pushRange(result.ranges, [pendingProperty[0], result.end]);
            }

            // Full value range
            pushRange(result.ranges, [start, end]);

            // Value fragments
            for (const r of splitValue(code.substring(start, end))) {
                pushRange(result.ranges, [r[0] + start, r[1] + start]);
            }
            return false;
        } else if (pendingProperty) {
            result = {
                start: pendingProperty[0],
                end: pendingProperty[1],
                ranges: [[pendingProperty[0], pendingProperty[1]]]
            }
            return false;
        }
    });

    return result;
}

/**
 * Returns regions for selecting previous item in CSS
 * @param {string} code
 * @param {number} pos
 * @returns {SelectItemModel | void}
 */
export function selectPreviousItem(code, pos) {
    const state = {
        type: null,
        start: -1,
        end: -1,
        valueStart: -1,
        valueEnd: -1,
        valueDelimiter: -1,
    };

    scan(code, (type, start, end, delimiter) => {
        // Accumulate context until we reach given position
        if (start >= pos && type !== 'propertyValue') {
            return false;
        }

        if (type === 'selector' || type === 'propertyName') {
            state.start = start;
            state.end = end;
            state.type = type;
            state.valueStart = state.valueEnd = state.valueDelimiter = -1;
        } else if (type === 'propertyValue') {
            state.valueStart = start;
            state.valueEnd = end;
            state.valueDelimiter = delimiter;
        }
    });

    if (state.type === 'selector') {
        return {
            start: state.start,
            end: state.end,
            ranges: [[state.start, state.end]]
        };
    }

    if (state.type === 'propertyName') {
        /** @type {SelectItemModel} */
        const result = {
            start: state.start,
            end: state.end,
            ranges: []
        };

        if (state.valueStart !== -1) {
            result.end = state.valueDelimiter !== -1 ? state.valueDelimiter + 1 : state.valueEnd;
            // Full property range
            pushRange(result.ranges, [state.start, result.end]);

            // Full value range
            pushRange(result.ranges, [state.valueStart, state.valueEnd]);

            // Value fragments
            for (const r of splitValue(code.substring(state.valueStart, state.valueEnd))) {
                pushRange(result.ranges, [r[0] + state.valueStart, r[1] + state.valueStart]);
            }
        } else {
            pushRange(result.ranges, [state.start, state.end]);
        }

        return result;
    }
}

/**
 * Allocates new token range from pool
 * @param {CSSTokenRange[]} pool
 * @param {number} start
 * @param {number} end
 * @param {number} delimiter
 * @returns {CSSTokenRange}
 */
function allocRange(pool, start, end, delimiter) {
    if (pool.length) {
        const range = pool.pop();
        range[0] = start;
        range[1] = end;
        range[2] = delimiter;
        return range;
    }
    return [start, end, delimiter];
}

/**
 * Releases given token range and pushes it back into the pool
 * @param {CSSTokenRange[]} pool
 * @param {CSSTokenRange} range
 */
function releaseRange(pool, range) {
    range && pool.push(range);
    return null;
}
