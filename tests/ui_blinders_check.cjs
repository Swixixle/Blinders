// Disposable HTTP/SQLite + inbox UI exercise. Chrome extension APIs are simulated.
const {JSDOM} = require(process.env.STENCIL_JSDOM_PATH || 'jsdom');
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const {createHash} = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'stencil-blinders-'));
const server = spawn('python3', ['-u', '-c', [
  'from local_server import make_server',
  'from captures import Store, data_directory',
  'server = make_server(Store(data_directory()), 0)',
  'print(f"http://127.0.0.1:{server.server_port}", flush=True)',
  'server.serve_forever()'
].join('\n')], {
  cwd: root, env: {...process.env, STENCIL_DATA_DIR: directory}
});
const original = '  Water  pressure\tβ\nSecond line.  ';
const png = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ySFsAAAAASUVORK5CYII=';
const source = new JSDOM('<pre></pre>', {url: 'https://research.test/paper?private=1', runScripts: 'outside-only'});
source.window.document.title = 'Study notes';
source.window.document.querySelector('pre').textContent = original;
const range = source.window.document.createRange();
range.selectNodeContents(source.window.document.querySelector('pre'));
source.window.getSelection().addRange(range);
let inbox;

async function until(check) {
  for (let i = 0; i < 200; i++) {
    if (check()) return;
    await new Promise(resolve => setTimeout(resolve, 20));
  }
  throw Error('UI did not reach the expected state');
}

async function exercise(origin) {
  const dest = {id: 1, windowId: 1, url: origin + '/blinders'};
  const research = {id: 2, windowId: 1, url: source.window.location.href, title: 'Study notes'};
  const sender = {tab: dest, url: dest.url};
  const session = {};
  let click, receive, active = dest;
  const tabs = {1: dest, 2: research};
  const chrome = {
    action: {onClicked: {addListener(fn) { click = fn; }}, async setBadgeText() {}, async setTitle() {}},
    runtime: {onMessageExternal: {addListener(fn) { receive = fn; }}},
    storage: {session: {async get() { return {...session}; }, async set(obj) { Object.assign(session, obj); },
      async remove(key) { delete session[key]; }}},
    tabs: {async get(id) { return tabs[id]; }, async query() { return [active]; },
      async update(id) { active = tabs[id]; }, async captureVisibleTab() {
        assert.equal(active.id, research.id);
        return 'data:image/png;base64,' + png;
      }},
    scripting: {async executeScript({func, target}) {
      assert.equal(target.tabId, research.id);
      if (target.allFrames) return [{result: source.window.eval('(' + func.toString() + ')()')}];
      return [{documentId: 'doc', result: 'visible'}];
    }}
  };
  const agent = {chrome, URL, crypto: require('node:crypto').webcrypto};
  vm.runInNewContext(fs.readFileSync(path.join(root, 'browser/worker.js'), 'utf8'), agent);
  const message = (op, from = sender, params = {}) => new Promise(resolve => receive({op, ...params}, from, resolve));
  assert.match((await message('text')).error, /inbox first/);
  await click(dest);
  await click(research);
  assert.match((await message('text', {tab: research, url: research.url})).error, /inbox first/);

  let failAfterSave = true;
  inbox = await JSDOM.fromURL(dest.url, {
    resources: 'usable', runScripts: 'dangerously', pretendToBeVisual: true,
    beforeParse(w) {
      w.TextDecoder = TextDecoder;
      w.chrome = {runtime: {sendMessage: async (_id, {op, ...params}) => message(op, sender, params)}};
      w.fetch = async (input, options) => {
        const reply = await fetch(new URL(input, origin), options);
        if (failAfterSave && input === '/api/blinders' && options.method === 'POST') {
          failAfterSave = false;
          throw Error('Simulated lost response');
        }
        return reply;
      };
    }
  });
  const {window} = inbox;
  const element = id => window.document.getElementById(id);
  window.document.documentElement.dataset.blindersExtension = 'test-extension';
  window.dispatchEvent(new window.Event('focus'));
  await until(() => !element('text').disabled);
  element('text').click();
  await until(() => !element('retry').hidden);
  element('retry').click();
  await until(() => element('captures').children.length === 1 && !element('png').disabled);
  element('captures').firstElementChild.open = true;
  await until(() => element('captures').querySelector('pre'));
  assert.equal(element('captures').querySelector('pre').textContent, original);
  assert.ok(!element('captures').textContent.includes('?private'));
  element('png').click();
  await until(() => element('captures').children.length === 2);
  assert.equal(active.id, dest.id);
  assert.ok(element('captures').textContent.includes(createHash('sha256').update(Buffer.from(png, 'base64')).digest('hex')));
  const env = {...process.env, BLINDERS_PORT: new URL(origin).port, STENCIL_DATA_DIR: directory};
  const run = require('node:util').promisify(require('node:child_process').execFile);
  const cli = (...args) => run(path.join(root, 'bin/blinders'), args, {env});
  const status = JSON.parse((await cli('status')).stdout);
  assert.equal(status.connected, true);
  for (const kind of ['text', 'png']) {
    const receipt = JSON.parse((await cli('capture', kind)).stdout);
    const bytes = kind === 'text' ? Buffer.from(original) : Buffer.from(png, 'base64');
    assert.equal(receipt.sha256, createHash('sha256').update(bytes).digest('hex'));
  }
  assert.equal(element('captures').children.length, 4);
  source.window.getSelection().removeAllRanges();
  assert.match((await message('text')).error, /Select text/);
  research.url = 'https://different.test/page';
  assert.match((await message('png')).error, /connect/);
  console.log('PASS: exact DOM selection, one retry record, screenshot bytes, tab restoration, wrong sender and origin rejection.');
}

new Promise((resolve, reject) => {
  server.stdout.on('data', data => {
    const url = data.toString().match(/http:\/\/127\.0\.0\.1:\d+/);
    if (url) resolve(url[0]);
  });
  server.on('error', reject);
  server.on('exit', code => reject(Error('Server exited: ' + code)));
}).then(exercise).catch(error => {
  console.error(error);
  process.exitCode = 1;
}).finally(() => {
  inbox?.window.close();
  source.window.close();
  server.kill();
  fs.rmSync(directory, {recursive: true, force: true});
});
