import nodeResolve from 'rollup-plugin-node-resolve';

export default {
    input: './src/emmet.js',
    plugins: [nodeResolve()],
    output: {
        format: 'iife',
        name: 'emmet',
        file: './emmet.js'
    }
}
