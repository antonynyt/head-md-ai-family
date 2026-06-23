'use strict';

const { WebSocketServer, WebSocket } = require('ws');

/**
 * Attaches a WebSocket server to the existing HTTP server.
 * Returns a broadcast(msg) function that sends JSON to every connected iPad.
 *
 * Message shapes the iPad will receive:
 *   { type: 'session:start' }
 *   { type: 'session:end' }
 *   { type: 'session:error', message: string }
 *   { type: 'transcript', text: string, turn: 'user'|'model', final: boolean }
 *   { type: 'word:saved', word: { term, definition, example, savedAt } }
 */
function createBroadcaster(httpServer) {
  const wss = new WebSocketServer({ server: httpServer });

  wss.on('connection', (ws, req) => {
    const ip = req.socket.remoteAddress;
    console.log(`[ws] client connected: ${ip}  (total: ${wss.clients.size})`);

    ws.on('close', () => {
      console.log(`[ws] client disconnected: ${ip}  (total: ${wss.clients.size})`);
    });

    ws.on('error', (err) => {
      console.warn('[ws] client error:', err.message);
    });

    // Send current dictionary on connection so the iPad can bootstrap its state
    const dictionary = require('./dictionary');
    dictionary.load().then((words) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'dictionary:init', words }));
      }
    }).catch(() => {});
  });

  function broadcast(msg) {
    const payload = JSON.stringify(msg);
    for (const client of wss.clients) {
      if (client.readyState === WebSocket.OPEN) {
        client.send(payload);
      }
    }
  }

  return broadcast;
}

module.exports = { createBroadcaster };
