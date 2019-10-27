import { scan, splitValue } from '@emmetio/css-matcher';
import { pushRange } from './utils';

/**
 * @typedef {{start: number, end: number, bodyStart: number, bodyEnd: number}} CSSSection
 * @typedef {[number, number, number]} TokenRange
 * @typedef {[number, number]} Range
 */

/**
 * Returns context CSS section for given location in source code
 * @param {string} code
 * @param {number} pos
 * @returns {CSSSection | null}
 */
export function contextSection(code, pos) {
    const stack = [];
    const pool = [];
    /** @type {CSSSection | null} */
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
 * Returns regions for selecting next item in CSS
 * @param {string} code
 * @param {number} pos
 * @returns {Range[]}
 */
export function selectNextItemCSS(code, pos) {
    /** @type {Range[]} */
    const result = [];
    /** @type {TokenRange | null} */
    let pendingProperty = null;

    scan(code, (type, start, end, delimiter) => {
        if (start < pos) {
            return;
        }

        if (type === 'selector') {
            result.push([start, end]);
            return false;
        } else if (type === 'propertyName') {
            pendingProperty = [start, end, delimiter];
        } else if (type === 'propertyValue') {
            if (pendingProperty) {
                // Full property range
                pushRange(result, [pendingProperty[0], delimiter !== -1 ? delimiter + 1 : end]);
            }

            // Full value range
            pushRange(result, [start, end]);

            // Value fragments
            for (r of splitValue(code.substring(start, end))) {
                pushRange(result, r[0] + start, r[1] + start);
            }
            return false;
        } else if (pendingProperty) {
            result.push(pendingProperty[0], pendingProperty[1]);
            return false;
        }
    });

    return result;
}

/**
 * Returns regions for selecting previous item in CSS
 * @param {string} code
 * @param {number} pos
 * @returns {Range[]}
 */
export function selectPreviousItemCSS(code, pos) {
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
        if (start > pos && type !== 'propertyValue') {
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
        return [[state.start, state.end]];
    }

    if (state.type === 'propertyName') {
        /** @type {Range[]} */
        const result = [];

        if (state.valueStart !== -1) {
            // Full property range
            pushRange(result, [state.start, state.valueDelimiter !== -1 ? state.valueDelimiter + 1 : state.valueEnd]);

            // Full value range
            pushRange(result, [start, end]);

            // Value fragments
            for (r of splitValue(code.substring(state.valueStart, state.valueEnd))) {
                pushRange(result, r[0] + state.valueStart, r[1] + state.valueStart);
            }
        } else {
            pushRange(result, [state.start, state.end]);
        }

        return result;
    }

    return [];
}

/**
 * Allocates new token range from pool
 * @param {TokenRange[]} pool
 * @param {number} start
 * @param {number} end
 * @param {number} delimiter
 * @returns {TokenRange}
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
 * @param {TokenRange[]} pool
 * @param {TokenRange} range
 */
function releaseRange(pool, range) {
    range && pool.push(range);
    return null;
}
