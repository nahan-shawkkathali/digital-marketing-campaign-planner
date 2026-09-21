// Browser-only layout checks of HTML rendered by the isolated workflow rehearsal.
// Uses installed Chrome and Node built-ins; it does not install packages.
import { createServer } from 'node:http';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { setTimeout as delay } from 'node:timers/promises';
import assert from 'node:assert/strict';

const out = dirname(fileURLToPath(import.meta.url));
const root = resolve(out, '../..');
const manifest = JSON.parse(readFileSync(join(out, 'snapshot-manifest.json'), 'utf8'));
const profile = join(out, 'chrome-profile');
mkdirSync(profile, { recursive: true });
const server = createServer((req, res) => {
  const url = new URL(req.url, 'http://127.0.0.1');
  let file;
  let type = 'text/html; charset=utf-8';
  if (url.pathname === '/favicon.ico') { res.writeHead(204).end(); return; }
  if (url.pathname.startsWith('/__snapshot/')) {
    const snapshot = manifest[url.pathname.slice('/__snapshot/'.length)];
    if (snapshot) file = join(out, snapshot.file);
  } else if (['/static/campaigns/css/home.css', '/static/campaigns/css/report.css'].includes(url.pathname)) {
    file = join(root, 'campaigns', url.pathname.slice(1));
    type = 'text/css';
  } else {
    const snapshot = Object.entries(manifest).find(([key, value]) => !key.endsWith('_empty') && !key.endsWith('_pending') && value.url === url.pathname)?.[1];
    if (snapshot) file = join(out, snapshot.file);
  }
  if (!file) { res.writeHead(404).end('No verification snapshot'); return; }
  res.writeHead(200, { 'Content-Type': type }).end(readFileSync(file));
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const base = `http://127.0.0.1:${server.address().port}`;
let chrome;
let socket;
const checks = [];
const errors = [];
try {
  chrome = spawn('C:/Program Files/Google/Chrome/Application/chrome.exe', [
    '--headless=new', '--remote-debugging-port=0', `--user-data-dir=${profile}`,
    '--no-first-run', '--no-default-browser-check', 'about:blank',
  ], { windowsHide: true, stdio: ['ignore', 'ignore', 'pipe'] });
  let stderr = '';
  chrome.stderr.on('data', chunk => { stderr += chunk; });
  const deadline = Date.now() + 20000;
  while (!stderr.includes('DevTools listening on') && Date.now() < deadline) await delay(100);
  const address = stderr.match(/DevTools listening on (ws:\/\/[^\s]+)/)?.[1];
  assert.ok(address, 'Chrome debugging endpoint did not start: ' + stderr);
  const endpoint = new URL(address);
  const targets = await (await fetch(`http://${endpoint.host}/json/list`)).json();
  const page = targets.find(target => target.type === 'page');
  socket = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  const pending = new Map();
  let id = 0;
  socket.onmessage = event => {
    const message = JSON.parse(event.data);
    if (message.id) {
      const promise = pending.get(message.id);
      pending.delete(message.id);
      message.error ? promise.reject(new Error(JSON.stringify(message.error))) : promise.resolve(message.result);
    } else if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails);
    else if (message.method === 'Network.loadingFailed' && !message.params.canceled) errors.push(message.params);
  };
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const requestId = ++id;
    pending.set(requestId, { resolve, reject });
    socket.send(JSON.stringify({ id: requestId, method, params }));
  });
  const evaluate = async expression => {
    const result = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    assert.ok(!result.exceptionDetails, JSON.stringify(result.exceptionDetails));
    return result.result.value;
  };
  await send('Page.enable');
  await send('Runtime.enable');
  await send('Network.enable');
  for (const width of [1440, 390, 320]) {
    await send('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1, mobile: false });
    for (const key of Object.keys(manifest)) {
      const url = `${base}/__snapshot/${key}`;
      await send('Page.navigate', { url });
      const readyDeadline = Date.now() + 20000;
      while (!(await evaluate(`location.href === ${JSON.stringify(url)} && document.readyState === 'complete'`))) {
        assert.ok(Date.now() < readyDeadline, `Page load timed out: ${key}`);
        await delay(50);
      }
      const measurement = await evaluate(`({
        width: innerWidth, scrollWidth: document.documentElement.scrollWidth,
        title: document.title, bootstrap: typeof bootstrap !== 'undefined',
        bootstrapCss: getComputedStyle(document.querySelector('.container')).getPropertyValue('--bs-gutter-x').trim(),
        toggleVisible: getComputedStyle(document.querySelector('.navbar-toggler')).display !== 'none'
      })`);
      assert.ok(measurement.bootstrap, `${key}: Bootstrap JavaScript did not load`);
      assert.ok(measurement.bootstrapCss, `${key}: Bootstrap CSS did not load`);
      assert.ok(measurement.scrollWidth <= width + 1, `${key} overflows at ${width}: ${measurement.scrollWidth}`);
      if (width < 992) {
        assert.ok(measurement.toggleVisible, `${key}: mobile toggle missing`);
        await evaluate(`document.querySelector('.navbar-toggler').click()`);
        await delay(380);
        const expanded = await evaluate(`document.querySelector('.navbar-toggler').getAttribute('aria-expanded') === 'true' && document.querySelector('#mainNavigation').classList.contains('show')`);
        assert.ok(expanded, `${key}: mobile navigation failed to expand`);
        await evaluate(`document.querySelector('.navbar-toggler').click()`);
        await delay(380);
        const collapsed = await evaluate(`document.querySelector('.navbar-toggler').getAttribute('aria-expanded') === 'false' && !document.querySelector('#mainNavigation').classList.contains('show')`);
        assert.ok(collapsed, `${key}: mobile navigation failed to collapse`);
      }
      checks.push({ page: key, width, scrollWidth: measurement.scrollWidth, mobileMenu: width < 992 ? 'PASS' : 'desktop' });
      if ((width === 1440 && key === 'client_campaign_report') || (width === 390 && ['client_deliverables_pending', 'employee_deliverable_campaigns', 'client_campaign_report'].includes(key))) {
        const metrics = await send('Page.getLayoutMetrics');
        const screenshot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true,
          clip: { x: 0, y: 0, width, height: metrics.cssContentSize.height, scale: 1 } });
        writeFileSync(join(out, `${key}-${width}.png`), Buffer.from(screenshot.data, 'base64'));
      }
    }
    console.log(`PASS: ${Object.keys(manifest).length} rendered pages at ${width}px, no page overflow; navigation checked.`);
  }
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
  await send('Page.navigate', { url: `${base}/__snapshot/client_campaign_report` });
  await delay(800);
  const printButton = await evaluate(`(() => { let called = false; window.print = () => { called = true; }; document.querySelector('[onclick="window.print()"]').click(); return called; })()`);
  assert.ok(printButton, 'Print button did not invoke window.print');
  await send('Emulation.setEmulatedMedia', { media: 'print' });
  const printLayout = await evaluate(`({ hidden: ['nav.navbar', 'footer', '.report-actions'].every(selector => getComputedStyle(document.querySelector(selector)).display === 'none'), reportVisible: getComputedStyle(document.querySelector('.campaign-report')).display !== 'none' })`);
  assert.ok(printLayout.hidden && printLayout.reportVisible, 'Print controls/layout incorrect');
  const pdf = await send('Page.printToPDF', { printBackground: true, preferCSSPageSize: true, paperWidth: 8.27, paperHeight: 11.69 });
  const pdfBytes = Buffer.from(pdf.data, 'base64');
  assert.equal(pdfBytes.subarray(0, 5).toString(), '%PDF-');
  writeFileSync(join(out, 'campaign-report.pdf'), pdfBytes);
  assert.deepEqual(errors, [], 'Browser resource or JavaScript errors found');
  const result = { result: 'PASS', method: 'Chrome headless rendering of isolated Django HTML snapshots', checks,
    print: { buttonInvokesPrint: printButton, ...printLayout, pdfBytes: pdfBytes.length }, errors };
  writeFileSync(join(out, 'browser-results.json'), JSON.stringify(result, null, 2));
  console.log(`PASS: report print button, print styling, PDF generation (${pdfBytes.length} bytes), no browser errors.`);
  await send('Browser.close');
} catch (error) {
  writeFileSync(join(out, 'browser-results.json'), JSON.stringify({ result: 'FAIL', error: String(error), checks, errors }, null, 2));
  console.error(error);
  process.exitCode = 1;
} finally {
  socket?.close();
  chrome?.kill();
  server.close();
}
