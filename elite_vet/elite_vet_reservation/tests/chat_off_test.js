// Chat widget with "Rezervace na webu" = WinVet: no booking flow, a link to /rezervacni-system.
// Run: node tests/chat_off_test.js (no browser, a minimal DOM stand-in).
const assert = require('assert');
const path = require('path');

function node(tag) {
 const n = {tagName: tag, children: [], className: '', textContent: '', hidden: false, attrs: {}, listeners: {},
  appendChild(c) { this.children.push(c); return c; },
  append(...cs) { cs.forEach(c => this.children.push(c)); },
  replaceChildren(...cs) { this.children = cs; },
  setAttribute(k, v) { this.attrs[k] = v; },
  addEventListener(k, fn) { (this.listeners[k] = this.listeners[k] || []).push(fn); },
  click() { (this.listeners.click || []).forEach(fn => fn({})); },
  focus() {}, querySelector() { return null; }};
 return n;
}
function all(n) { return [n].concat(...n.children.map(all)); }

const body = node('body');
global.document = {documentElement: {lang: 'cs-CZ', classList: {add() {}, remove() {}}}, body,
 createElement: node, createTextNode: t => ({textContent: t, children: []}), getElementById: () => null};
global.window = global;
global.AbortController = class { constructor() { this.signal = {}; } abort() {} };
const calls = [];
let answer = {ok: false, error: 'web_booking_off', fields: {}, message: 'x', url: '/de/rezervacni-system'};
global.fetch = async (url) => { calls.push(url); return {ok: true, json: async () => ({result: answer})}; };

window.EliteVetChatBooking = require(path.join(__dirname, '../static/src/chat/chat_core.js'));
require(path.join(__dirname, '../static/src/chat/chat.js'));

(async function () {
 const launcher = body.children[0], panel = body.children[1];
 launcher.click();
 assert.equal(panel.hidden, false);
 await new Promise(r => setTimeout(r, 10));
 const nodes = all(panel);
 const link = nodes.find(n => n.tagName === 'a');
 assert.ok(link, 'link to the booking page');
 assert.equal(link.href, '/de/rezervacni-system');
 assert.equal(link.textContent, 'Otevřít rezervační systém');
 assert.ok(nodes.some(n => n.textContent === 'Online rezervace teď přijímáme na stránce Rezervační systém.'));
 assert.ok(!nodes.some(n => n.tagName === 'select'), 'no procedure choice');
 assert.deepEqual(calls, ['/rezervace/api/options']);
 console.log('PASS: chat in WinVet mode shows only the link to /rezervacni-system');
})().catch(e => { console.error(e); process.exit(1); });
