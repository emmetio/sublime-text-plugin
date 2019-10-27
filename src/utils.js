/**
 * Returns `true` if given character code is a space
 * @param {number} code
 */
export function isSpace(code) {
    return code === 32  /* space */
        || code === 9   /* tab */
        || code === 160 /* non-breaking space */
        || code === 10  /* LF */
        || code === 13; /* CR */
}

/**
 * @param {Array} ranges
 * @param {[number, number]} range
 */
export function pushRange(ranges, range) {
    const prev = ranges[ranges.length - 1];
    if (range && range[0] !== range[1] && (!prev || prev[0] !== range[0] || prev[1] !== range[1])) {
        ranges.push(range);
    }
}
