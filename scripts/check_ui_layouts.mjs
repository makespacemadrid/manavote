// Geometry and interaction checks against populated Flask test snapshots.
// Capture: MANAVOTE_UI_LAYOUT_DIR=/tmp/manavote-layouts pytest -q tests/test_ui_layouts.py
// Run: node scripts/check_ui_layouts.mjs /tmp/manavote-layouts
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

const snapshots = resolve(process.argv[2] ?? '/tmp/manavote-layouts');
const assets = resolve('static/react');
const server = createServer(async (request, response) => {
  const path = new URL(request.url, 'http://localhost').pathname;
  try {
    if (/^\/[a-z_-]+-(en|es)\.html$/.test(path)) {
      const html = await readFile(join(snapshots, path.slice(1)), 'utf8');
      response.setHeader('Content-Type', 'text/html');
      response.end(html.replaceAll(`file://${resolve('static')}/`, '/assets/'));
    } else if (path.startsWith('/assets/')) {
      const target=resolve('static',path.slice('/assets/'.length));
      assert.ok(target.startsWith(resolve('static')+'/'));
      response.setHeader('Content-Type',target.endsWith('.js')?'text/javascript':target.endsWith('.css')?'text/css':target.endsWith('.png')?'image/png':'image/x-icon');
      response.end(await readFile(target));
    } else if (path.startsWith('/qr-assets/')) {
      response.setHeader('Content-Type','image/png'); response.end(await readFile(join(snapshots,path.split('/').at(-1))));
    } else if (path === '/diagnostics/browser-errors') { response.writeHead(204);response.end();
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
  const consoleErrors = [];
  socket.onmessage = ({ data }) => {
    const message = JSON.parse(data);
    if (message.method === 'Runtime.consoleAPICalled' && message.params.type === 'error') consoleErrors.push(JSON.stringify(message.params.args));
    if (message.method === 'Runtime.exceptionThrown') consoleErrors.push(message.params.exceptionDetails.exception?.description ?? 'Browser exception');
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
  let checks=0;
  for (const language of ['en','es']) {
    const pages=JSON.parse(await readFile(join(snapshots,`manifest-${language}.json`),'utf8'));
    for (const page of pages) for (const width of [320,375,600,1280,1600,1920]) {
      consoleErrors.length=0;
      await cdp('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});
      await cdp('Page.navigate',{url:`${base}/${page.file}`});
      let ready=false;
      for(let attempt=0;attempt<50;attempt++){
        ready=await evaluate(`document.readyState==='complete'&&document.body.dataset.layoutFixture===${JSON.stringify(page.file)}&&!!document.querySelector('nav[data-react-hydrated]')`);
        if(ready)break;
        await new Promise(r=>setTimeout(r,100));
      }
      assert.ok(ready,`${page.file}/${width}: page did not finish loading`);
      await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
      assert.ok(await evaluate('!!document.querySelector("nav[data-react-hydrated]")'),`${page.file}/${width}: hydration`);
      assert.deepEqual(consoleErrors,[],`${page.file}/${width}: browser errors`);
      const issues=await evaluate(`(()=>{
        const issues=[];
        const visible=el=>el.getBoundingClientRect().width>0&&el.getBoundingClientRect().height>0&&getComputedStyle(el).visibility!=='hidden';
        if(document.documentElement.scrollWidth>innerWidth)issues.push('document overflow '+document.documentElement.scrollWidth);
        for(const group of document.querySelectorAll('.button-row,main form,.admin-toolbar,.chart-range,#calendarLegendFilters,.vote-form,.language-buttons,.feedback-status-form,.quantity-form,.form-row,.member-identity-row,.group-component-input-row,.component-input-row,.edit-cost-row')){
          if(!visible(group))continue;
          const buttons=[...group.querySelectorAll('button,a.btn')].filter(visible);
          for(let i=0;i<buttons.length;i++)for(let j=i+1;j<buttons.length;j++){
            const a=buttons[i].getBoundingClientRect(),b=buttons[j].getBoundingClientRect();
            if(Math.abs(a.top-b.top)<Math.min(a.height,b.height)/2&&Math.min(a.right,b.right)<=Math.max(a.left,b.left)+1){
              if(Math.abs(a.top-b.top)>1||Math.abs(a.bottom-b.bottom)>1)issues.push('button alignment: '+buttons[i].textContent.trim()+' / '+buttons[j].textContent.trim());
            }
          }
          if(group.matches('.form-row,.quantity-form,.group-component-input-row,.component-input-row,.edit-cost-row,.member-identity-row')){
            for(const button of buttons)for(const input of group.querySelectorAll('input:not([type=hidden]):not([type=checkbox]),select')){
              if(!visible(input))continue;
              const a=button.getBoundingClientRect(),b=input.getBoundingClientRect();
              if(Math.abs(a.bottom-b.bottom)<22&&Math.min(a.right,b.right)<=Math.max(a.left,b.left)+1&&Math.abs(a.bottom-b.bottom)>1)issues.push('field/action baseline: '+(input.name||input.id)+' / '+button.textContent.trim());
            }
          }
        }
        return issues;
      })()`);
      assert.deepEqual(issues,[],`${page.file}/${width}`);
      if(width===1920)assert.equal(await evaluate('Math.round(document.querySelector(".container").getBoundingClientRect().width)'),1600);
      if(page.name==='proposals'){
        assert.ok(await evaluate(`(()=>{const badge=document.querySelector('.proposal-age-watermark');if(!badge)return false;const a=badge.getBoundingClientRect(),b=badge.closest('.proposal-card-image').getBoundingClientRect();return badge.textContent.includes('45')&&a.left>=b.left-1&&a.right<=b.right+1&&a.top>=b.top-1&&a.bottom<=b.bottom+1})()`), 'Exact old age must overlay the photo within its bounds');
        assert.ok(await evaluate(`(()=>{const image=document.querySelector('.proposal-card-image');const info=document.querySelector('.proposal-info');if(!image)return false;const a=image.getBoundingClientRect(),b=info.getBoundingClientRect();return innerWidth<=600?a.bottom<=b.top+1:a.right<=b.left+1&&a.width>=150})()`), 'Proposal image must precede the entire content');
        if(width>=1280)assert.ok(await evaluate('document.querySelector(".proposal-card-image").getBoundingClientRect().width>=180'));
        assert.ok(await evaluate(`(()=>{const form=document.querySelector('#proposal-query');form.requestSubmit=()=>{window.filterSubmits=(window.filterSubmits||0)+1};form.querySelector('select').dispatchEvent(new Event('change'));document.querySelector('[name=age]').dispatchEvent(new Event('change'));return window.filterSubmits===2&&form.querySelector('[data-query-submit]').getBoundingClientRect().height===0})()`));
      }
      if(page.name==='new-proposal'){
        assert.ok(await evaluate(`(()=>{
          const form=document.querySelector('form[data-protect-changes]');
          const button=form.querySelector('button[type=submit]');
          button.name='test-action';button.value='keep-me';
          const title=form.elements.title;title.value='Keep my mobile entry';title.dispatchEvent(new Event('input',{bubbles:true}));
          const leaving=new Event('beforeunload',{cancelable:true});window.dispatchEvent(leaving);
          if(!leaving.defaultPrevented)return false;
          title.dispatchEvent(new Event('invalid',{cancelable:true}));
          if(title.getAttribute('aria-invalid')!=='true')return false;
          title.dispatchEvent(new Event('input',{bubbles:true}));
          if(title.hasAttribute('aria-invalid'))return false;
          Object.defineProperty(navigator,'onLine',{configurable:true,value:false});
          const offline=new SubmitEvent('submit',{cancelable:true,submitter:button});form.dispatchEvent(offline);
          if(!offline.defaultPrevented||form.hasAttribute('aria-busy')||title.value!=='Keep my mobile entry')return false;
          Object.defineProperty(navigator,'onLine',{configurable:true,value:true});
          const first=new SubmitEvent('submit',{cancelable:true,submitter:button});form.dispatchEvent(first);
          const second=new SubmitEvent('submit',{cancelable:true,submitter:button});form.dispatchEvent(second);
          const data=new FormData(form,button);
          if(first.defaultPrevented||!second.defaultPrevented||data.get('test-action')!=='keep-me'||button.disabled||form.getAttribute('aria-busy')!=='true')return false;
          window.dispatchEvent(new Event('pageshow'));
          if(form.hasAttribute('aria-busy')||button.hasAttribute('aria-disabled'))return false;
          const cancelled=new SubmitEvent('submit',{cancelable:true,submitter:button});cancelled.preventDefault();form.dispatchEvent(cancelled);
          if(form.hasAttribute('aria-busy'))return false;
          const image=form.elements.image;
          const bad=new DataTransfer();bad.items.add(new File(['invalid'],'phone.heic',{type:'image/heic'}));image.files=bad.files;image.dispatchEvent(new Event('change'));
          if(image.validity.valid||title.value!=='Keep my mobile entry')return false;
          const good=new DataTransfer();good.items.add(new File(['png'],'phone.PNG',{type:'image/png'}));image.files=good.files;image.dispatchEvent(new Event('change'));
          return image.validity.valid&&!image.hasAttribute('aria-invalid');
        })()`), 'Forms must retain entries offline, prevent repeat submits, preserve submitter values and reset on history navigation');
      }
      if(page.name==='groups'&&width<=600){
        assert.ok(await evaluate(`[...document.querySelectorAll('.purchase-debts-table')].every(table=>table.scrollWidth<=table.parentElement.clientWidth+1)`), 'Mobile payment rows must fit without scrolling');
      }
      if(page.name==='polls'){
        assert.ok(await evaluate(`(()=>{const input=document.querySelector('.poll-options:not(:disabled) input:not(:checked)');input.focus();return document.activeElement===input})()`));
        await cdp('Input.dispatchKeyEvent',{type:'keyDown',key:' ',code:'Space',windowsVirtualKeyCode:32});
        await cdp('Input.dispatchKeyEvent',{type:'keyUp',key:' ',code:'Space',windowsVirtualKeyCode:32});
        assert.ok(await evaluate('document.activeElement.checked'));
        assert.ok(await evaluate('!!document.querySelector(".poll-options:disabled")'));
      }
      if(process.env.MANAVOTE_LAYOUT_SCREENSHOTS==='1'&&[375,1920].includes(width)&&['polls','settings','about','groups'].includes(page.name)){
        const shot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});
        await writeFile(join(snapshots,`${page.name}-${language}-${width}.png`),Buffer.from(shot.data,'base64'));
      }
      checks++;
    }
  }
  console.log(`Passed ${checks} bilingual layouts: button alignment, field/action baselines, responsive width, filter submission, poll keyboard controls and hydration.`);

} finally {
  socket?.close();
  browser.kill();
  await new Promise((resolveExit) => { if (browser.exitCode !== null) resolveExit(); else browser.once('exit', resolveExit); });
  await rm(profile, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
  await new Promise((resolveClose) => server.close(resolveClose));
}
