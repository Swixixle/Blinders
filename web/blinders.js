'use strict';
const byId = id => document.getElementById(id);
const headers = {'X-Stencil-Token': document.querySelector('meta[name="stencil-token"]').content};
let pending = null;
let connected = false;
let busy = false;
let offset = 0;

function controls() {
  byId('text').disabled = byId('png').disabled = !connected || busy || !!pending;
  byId('disconnect').hidden = !connected;
  byId('disconnect').disabled = busy;
  byId('retry').hidden = byId('discard').hidden = !pending || busy;
}

async function browserAction(op, pair, selector) {
  const id = document.documentElement.dataset.blindersExtension;
  if (!id || !globalThis.chrome?.runtime?.sendMessage) {
    throw new Error('Load the Blinders extension in Chrome, then reload this inbox.');
  }
  const reply = await chrome.runtime.sendMessage(id, {op, pair, selector});
  if (!reply || reply.error) throw new Error(reply?.error || 'The browser connection closed.');
  return reply.value;
}

async function connection() {
  try {
    const tab = await browserAction('status');
    byId('connection').textContent = tab.title;
    connected = true;
  } catch (error) {
    connected = false;
    byId('connection').textContent = error.message;
  }
  controls();
}

async function request(path, options = {}) {
  const response = await fetch(path, {...options, headers: {...headers, ...options.headers}});
  if (!response.ok) throw new Error((await response.json()).error);
  return response;
}

function captureRow(item) {
  const details = document.createElement('details');
  details.className = 'capture';
  const summary = document.createElement('summary');
  summary.textContent = (item.kind === 'text' ? 'Text' : 'Screenshot') + ' · ' + (item.title || item.source);
  const meta = document.createElement('small');
  meta.textContent = item.source + ' · ' + new Date(item.saved_at).toLocaleString();
  const receipt = document.createElement('small');
  receipt.textContent = item.bytes.toLocaleString() + ' bytes · SHA-256 ' + item.sha256;
  const original = document.createElement('div');
  details.append(summary, meta, receipt, original);
  let loading = false;
  details.ontoggle = async () => {
    if (!details.open || loading || original.childElementCount) return;
    loading = true;
    try {
      const response = await request('/api/blinders/original/' + item.id);
      const blob = await response.blob();
      const view = document.createElement(item.kind === 'text' ? 'pre' : 'img');
      if (item.kind === 'text') {
        // Keep a leading BOM if the selection contained one.
        view.textContent = new TextDecoder('utf-8', {ignoreBOM: true}).decode(await blob.arrayBuffer());
      } else {
        view.alt = 'Captured viewport of ' + (item.title || item.source);
        // The existing Stencil CSP allows data: images.
        const reader = new FileReader();
        reader.onload = () => { view.src = reader.result; };
        reader.readAsDataURL(blob);
      }
      const save = document.createElement('button');
      save.className = 'button secondary';
      save.textContent = 'Download original';
      save.onclick = () => {
        const link = document.createElement('a');
        const url = URL.createObjectURL(blob);
        link.href = url;
        link.download = 'blinders-' + item.id + (item.kind === 'text' ? '.txt' : '.png');
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      };
      original.replaceChildren(view, save);
    } catch (error) {
      original.textContent = error.message;
    } finally {
      loading = false;
    }
  };
  return details;
}

async function list(start = 0) {
  const page = await (await request('/api/blinders?offset=' + start)).json();
  offset = start;
  byId('captures').replaceChildren(...page.items.map(captureRow));
  byId('empty').hidden = !!page.items.length;
  byId('older').hidden = !page.more;
  byId('newer').hidden = start === 0;
}

async function save(kind) {
  if (busy) return;
  busy = true;
  controls();
  try {
    if (!pending) {
      const capture = await browserAction(kind);
      pending = {...capture, id: crypto.randomUUID()};
    }
    const receipt = await (await request('/api/blinders', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(pending)
    })).json();
    pending = null;
    byId('outcome').textContent = 'Saved ' + receipt.bytes.toLocaleString() + ' bytes.';
    await list(0);
  } catch (error) {
    byId('outcome').textContent = error.message;
  } finally {
    busy = false;
    controls();
    await connection();
  }
}

function report(error) { byId('outcome').textContent = error.message; }
byId('refresh').onclick = connection;
byId('text').onclick = () => save('text');
byId('png').onclick = () => save('png');
byId('retry').onclick = () => save();
byId('discard').onclick = () => {
  pending = null;
  byId('outcome').textContent = 'Pending copy cleared.';
  controls();
};
byId('older').onclick = () => list(offset + 50).catch(report);
byId('newer').onclick = () => list(Math.max(0, offset - 50)).catch(report);
byId('disconnect').onclick = async () => {
  try { await browserAction('disconnect'); } catch (error) { report(error); }
  await connection();
};
window.addEventListener('focus', connection);
document.addEventListener('visibilitychange', () => { if (!document.hidden) connection(); });
window.addEventListener('load', connection);
connection();
list().catch(report);

// The browser sends bytes only for a request issued by the local CLI or MCP.
async function receiveRequests() {
  for (;;) {
    try {
      const {pair, title} = await browserAction('status');
      const post = (path, value) => request(path, {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(value)
      });
      const job = await (await post('/api/bridge/next', {pair, title})).json();
      if (!job.id) continue;
      let result;
      try {
        result = await browserAction(job.kind, job.pair, job.selector);
      } catch (error) {
        result = {error: error.message};
      }
      await post('/api/bridge/finish', {...result, id: job.id, pair: job.pair});
      await list();
    } catch {
      await new Promise(resolve => setTimeout(resolve, 1500));
    }
  }
}
receiveRequests();
