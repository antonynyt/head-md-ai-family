'use strict';

const fs   = require('fs').promises;
const path = require('path');
const { DICT_PATH } = require('./config');

const FILE = path.resolve(DICT_PATH);

async function load() {
  try {
    return JSON.parse(await fs.readFile(FILE, 'utf8'));
  } catch (err) {
    if (err.code === 'ENOENT') return [];
    throw err;
  }
}

async function save(word) {
  const words = await load();
  if (words.some((w) => w.term.toLowerCase() === word.term.toLowerCase())) {
    console.log(`[dict] "${word.term}" already exists, skipping`);
    return;
  }
  words.push(word);
  await fs.writeFile(FILE, JSON.stringify(words, null, 2), 'utf8');
  console.log(`[dict] saved "${word.term}"`);
}

module.exports = { load, save };
