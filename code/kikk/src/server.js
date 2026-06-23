'use strict';

const http = require('http');
const fs   = require('fs');
const path = require('path');

const PUBLIC = path.join(__dirname, '..', 'public');

/**
 * Minimal HTTP server — serves /public for the iPad UI and nothing else.
 * No framework needed.
 */
function createServer() {
  const server = http.createServer((req, res) => {
    if (req.method !== 'GET') {
      res.writeHead(405).end();
      return;
    }

    // Resolve the file path, defaulting to index.html
    const rel  = req.url === '/' ? '/index.html' : req.url;
    const file = path.join(PUBLIC, path.normalize(rel));

    // Prevent path traversal outside /public
    if (!file.startsWith(PUBLIC)) {
      res.writeHead(403).end();
      return;
    }

    fs.readFile(file, (err, data) => {
      if (err) {
        res.writeHead(err.code === 'ENOENT' ? 404 : 500).end();
        return;
      }
      res.writeHead(200, { 'Content-Type': mime(file) });
      res.end(data);
    });
  });

  return server;
}

function mime(file) {
  const ext = path.extname(file);
  return { '.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript' }[ext]
    ?? 'application/octet-stream';
}

module.exports = { createServer };
