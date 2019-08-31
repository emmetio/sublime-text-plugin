import expandAbbreviation from 'emmet';

export { extract } from 'emmet';

/**
 * @param {number} index
 * @param {string} placeholder
 * @returns {string}
 */
function field(index, placeholder) {
    return `\${${index}${placeholder ? `:${placeholder}` : ''}}`;
}

/**
 * Expands given abbreviation
 * @param {string} abbr
 * @param {import('emmet').UserConfig} [config]
 * @returns {string}
 */
export function expand(abbr, config) {
    return expandAbbreviation(abbr, {
        ...config,
        options: {
            'output.field': field,
            ...(config && config.options),
        }
    });
}
