// Real Chromium checks against Flask-rendered test snapshots; no production server.
// Generate snapshots: MANAVOTE_UI_CAPTURE_DIR=/tmp/manavote-ui pytest -q tests/test_admin_interface.py
// Run: node scripts/check_dialogs.mjs /tmp/manavote-ui
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

const snapshots = resolve(process.argv[2] ?? '/tmp/manavote-ui');
const assets = resolve('static/react');
const server = createServer(async (request, response) => {
  const path = new URL(request.url, 'http://localhost').pathname;
  try {
    if (/^\/(admin|proposals)-(en|es)\.html$/.test(path)) {
      const html = await readFile(join(snapshots, path.slice(1)), 'utf8');
      response.setHeader('Content-Type', 'text/html');
      response.end(html.replaceAll(`file://${resolve('static')}/`, '/assets/'));
    } else if (path === '/assets/react/app.js' || path === '/assets/react/style.css') {
      response.setHeader('Content-Type', path.endsWith('.js') ? 'text/javascript' : 'text/css');
      response.end(await readFile(join(assets, path.split('/').at(-1))));
    } else { response.writeHead(404); response.end(); }
  } catch { response.writeHead(500); response.end(); }
});
await new Promise((resolveListen) => server.listen(0, '127.0.0.1', resolveListen));
const base = `http://127.0.0.1:${server.address().port}`;
const profile = await mkdtemp(join(tmpdir(), 'manavote-chromium-'));
const browser = spawn(process.env.CHROMIUM ?? 'chromium', [
  '--headless', '--no-sandbox', '--disable-dev-shm-usage', '--allow-file-access-from-files',
  '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank',
], { stdio: ['ignore', 'ignore', 'pipe'] });
let socket;
try {
  const endpoint = await new Promise((resolveEndpoint, reject) => {
    let stderr = '';
    const timer = setTimeout(() => reject(new Error('Chromium startup timed out')), 10000);
    browser.on('error', reject);
    browser.on('exit', (code) => reject(new Error(`Chromium exited: ${code}`)));
    browser.stderr.on('data', (chunk) => {
      stderr += chunk;
      const match = stderr.match(/DevTools listening on (ws:\/\/[^\s]+)/);
      if (match) { clearTimeout(timer); resolveEndpoint(match[1]); }
    });
  });
  const address = new URL(endpoint);
  const tab = await (await fetch(`http://${address.host}/json/new?about:blank`, { method: 'PUT' })).json();
  socket = new WebSocket(tab.webSocketDebuggerUrl);
  await new Promise((resolveOpen, reject) => { socket.onopen = resolveOpen; socket.onerror = reject; });
  let nextId = 0;
  const pending = new Map();
  socket.onmessage = ({ data }) => {
    const message = JSON.parse(data);
    if (message.method === 'Runtime.exceptionThrown') console.error('Browser error:', message.params.exceptionDetails.exception?.description);
    const request = pending.get(message.id);
    if (!request) return;
    pending.delete(message.id);
    if (message.error) request.reject(new Error(message.error.message)); else request.resolve(message.result);
  };
  const cdp = (method, params = {}) => new Promise((resolveRequest, reject) => {
    const id = ++nextId;
    pending.set(id, { resolve: resolveRequest, reject });
    socket.send(JSON.stringify({ id, method, params }));
  });
  const evaluate = async (expression) => {
    const result = await cdp('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    assert.equal(result.exceptionDetails, undefined, `Browser expression failed: ${expression}`);
    return result.result.value;
  };
  const key = async (name, shift = false) => {
    const code = name === 'Tab' ? 9 : name === 'Escape' ? 27 : 13;
    for (const type of ['keyDown', 'keyUp']) await cdp('Input.dispatchKeyEvent', {
      type, key: name, code: name, windowsVirtualKeyCode: code, modifiers: shift ? 8 : 0,
      ...(name === 'Enter' && type === 'keyDown' ? { text: '\r' } : {}),
    });
  };
  await cdp('Page.enable');
  await cdp('Page.bringToFront');
  await cdp('Runtime.enable');
  for (const language of ['en', 'es']) {
    for (const width of [375, 600, 1280]) {
      await cdp('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1, mobile: false });
      await cdp('Page.navigate', { url: `${base}/admin-${language}.html` });
      let loaded = false;
      for (let i = 0; i < 50; i++) {
        if (await evaluate('typeof window.confirmDangerAction === "function" && !!document.querySelector("[data-password-open]")')) { loaded = true; break; }
        await new Promise((resolveDelay) => setTimeout(resolveDelay, 100));
      }
      assert.ok(loaded, `Dialog module did not load: ${await evaluate('JSON.stringify({url:location.href,scripts:Array.from(document.scripts).map(s=>s.src)})')}`);
      assert.ok(await evaluate('document.documentElement.scrollWidth <= window.innerWidth'), `Admin page overflow: ${language}/${width}`);
      await evaluate('document.querySelector("[data-password-open]").focus()');
      assert.ok(await evaluate('document.activeElement.hasAttribute("data-password-open")'), 'Password opener is not focusable');
      await key('Enter');
      assert.equal(await evaluate('document.activeElement.id'), 'newPassword');
      assert.equal(await evaluate('document.getElementById("changePasswordMemberId").value'), '2');
      assert.equal(await evaluate('document.getElementById("changePasswordUser").textContent.includes("O\\\'Brien <member>")'), true);
      assert.ok(await evaluate('document.getElementById("changePasswordModal").querySelectorAll("h3").length === 1'));
      assert.ok(await evaluate('document.querySelector("label[for=newPassword]") !== null'));
      await key('Tab', true);
      assert.ok(await evaluate('document.activeElement.hasAttribute("data-password-cancel")'));
      await key('Tab');
      assert.equal(await evaluate('document.activeElement.id'), 'newPassword');
      await evaluate('document.getElementById("newPassword").value = "test-only-value"');
      await key('Escape');
      assert.ok(await evaluate('document.getElementById("changePasswordModal").hidden'));
      assert.ok(await evaluate('document.activeElement.hasAttribute("data-password-open")'));
      assert.equal(await evaluate('document.getElementById("newPassword").value'), '');
      await evaluate('window.confirmDangerAction(document.querySelector("form"), "test confirmation")');
      await key('Tab');
      assert.ok(await evaluate('document.activeElement.hasAttribute("data-danger-cancel")'));
      await key('Tab', true);
      assert.ok(await evaluate('document.activeElement.hasAttribute("data-danger-confirm")'));
      await key('Escape');
      assert.ok(await evaluate('document.getElementById("dangerActionModal").hidden'));
      await evaluate('window.dialogSubmitted = false; window.confirmDangerAction({submit(){window.dialogSubmitted = true}}, "test confirmation"); document.querySelector("[data-danger-confirm]").click()');
      assert.ok(await evaluate('window.dialogSubmitted && document.getElementById("dangerActionModal").hidden'));
      await evaluate('document.querySelector("[data-feedback-open]").click()');
      assert.equal(await evaluate('document.activeElement.id'), 'feedback-message');
      await key('Escape');
      assert.ok(await evaluate('document.getElementById("feedbackModal").hidden'));
      await cdp('Page.navigate', { url: `${base}/proposals-${language}.html` });
      await new Promise((resolveDelay) => setTimeout(resolveDelay, 150));
      assert.ok(await evaluate('document.documentElement.scrollWidth <= window.innerWidth'), `Proposal page overflow: ${language}/${width}`);
      assert.equal(await evaluate('getComputedStyle(document.querySelector(".quick-vote-btn.approve")).borderTopColor'), 'rgb(0, 217, 255)');
      console.log(`Passed keyboard/focus/dialog/palette/layout checks: ${language}, ${width}px`);
    }
  }
} finally {
  socket?.close();
  browser.kill();
  await new Promise((resolveExit) => { if (browser.exitCode !== null) resolveExit(); else browser.once('exit', resolveExit); });
  await rm(profile, { recursive: true, force: true });
  await new Promise((resolveClose) => server.close(resolveClose));
}
