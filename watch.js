#!/usr/bin/env node
const fs = require('fs');

let scheduled = false;

function watchCallback() {
    if (!scheduled) {
        scheduled = true;
        setTimeout(() => {
            scheduled = false;
            const now = new Date();
            fs.utimesSync('./main.py', now, now);
        }, 100).unref();
    }
}

fs.watch('./lib', { recursive: true }, watchCallback);
fs.watch('./emmet', { recursive: true }, watchCallback);
console.log('Watcher started');
