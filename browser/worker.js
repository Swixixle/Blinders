const localInbox = url => {
  const address = new URL(url);
  return address.protocol === 'http:' && address.hostname === '127.0.0.1' && address.pathname === '/blinders';
};

async function bindTab(tab) {
  if (!tab.url || !/^https?:\/\//.test(tab.url)) throw new Error('Choose an HTTP or HTTPS page.');
  const {source} = await chrome.storage.session.get('source');
  if (localInbox(tab.url)) {
    await chrome.storage.session.set({inbox: {tabId: tab.id, url: tab.url}, source: null});
    await chrome.action.setBadgeText({tabId: tab.id, text: 'IN'});
  } else {
    const {inbox} = await chrome.storage.session.get('inbox');
    if (!inbox) throw new Error('Connect the Stencil Blinders inbox first.');
    const destination = await chrome.tabs.get(inbox.tabId);
    if (destination.url !== inbox.url) throw new Error('Reconnect the Stencil Blinders inbox.');
    await chrome.storage.session.set({source: {tabId: tab.id, origin: new URL(tab.url).origin, pair: crypto.randomUUID()}});
    await chrome.action.setBadgeText({tabId: tab.id, text: 'ON'});
  }
  if (source && source.tabId !== tab.id) {
    await chrome.action.setBadgeText({tabId: source.tabId, text: ''}).catch(() => {});
  }
  await chrome.action.setTitle({tabId: tab.id, title: 'Connected to Blinders'});
}

chrome.action.onClicked.addListener(tab => bindTab(tab).catch(async error => {
  await chrome.action.setBadgeText({tabId: tab.id, text: '!'});
  await chrome.action.setTitle({tabId: tab.id, title: error.message});
}));

function documentSelection(selector) {
  if (selector) {
    const matches = [...document.querySelectorAll(selector)].filter(el =>
      el instanceof HTMLElement && el.getClientRects().length && getComputedStyle(el).visibility === 'visible');
    if (matches.length > 1) return {ambiguous: true};
    const el = matches[0];
    return {text: el?.innerText || '', source: location.href, title: document.title};
  }
  const field = document.activeElement;
  let text = '';
  if (field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement) {
    if (field.type !== 'password' && typeof field.selectionStart === 'number') {
      text = field.value.slice(field.selectionStart, field.selectionEnd);
    }
  } else {
    text = window.getSelection()?.toString() || '';
  }
  return {text, source: location.href, title: document.title};
}

async function selectedText(tab, selector) {
  const results = await chrome.scripting.executeScript({
    target: {tabId: tab.id, allFrames: true}, func: documentSelection, args: [selector || null]
  });
  if (results.some(row => row.result?.ambiguous)) throw new Error('The selector must match one visible element.');
  const values = results.map(row => row.result).filter(value => value?.text);
  if (values.length !== 1) {
    throw new Error(values.length ? 'Select text in a single frame.' :
      'Select text in an accessible frame of the connected tab, or save its visible view.');
  }
  const after = await chrome.tabs.get(tab.id);
  if (after.url !== tab.url || after.pendingUrl) throw new Error('The source changed during capture.');
  const {text: content, source, title} = values[0];
  return {kind: 'text', content, source, title};
}

async function visibleTab(tab, inbox) {
  const [previous] = await chrome.tabs.query({windowId: tab.windowId, active: true});
  if (![tab.id, inbox.tabId].includes(previous?.id)) {
    throw new Error('Bring the connected source to the front of its window and retry.');
  }
  const switched = previous.id !== tab.id;
  const currentTab = async () => (await chrome.tabs.query({windowId: tab.windowId, active: true}))[0];
  try {
    if (switched) await chrome.tabs.update(tab.id, {active: true});
    const [frame] = await chrome.scripting.executeScript({
      target: {tabId: tab.id}, func: () => new Promise(resolve => {
        const timer = setTimeout(() => resolve('hidden'), 1500);
        requestAnimationFrame(() => requestAnimationFrame(() => {
          clearTimeout(timer);
          resolve(document.visibilityState);
        }));
      })
    });
    if (frame.result !== 'visible') throw new Error('Bring the connected tab into view.');
    const before = await currentTab();
    if (before?.id !== tab.id || before.url !== tab.url || before.pendingUrl) throw new Error('The source changed.');
    const image = await chrome.tabs.captureVisibleTab(tab.windowId, {format: 'png'});
    const after = await currentTab();
    const [confirmed] = await chrome.scripting.executeScript({target: {tabId: tab.id}, func: () => location.href});
    if (confirmed.documentId !== frame.documentId || after?.id !== tab.id || after.url !== tab.url || after.pendingUrl) throw new Error('The source changed during capture.');
    return {kind: 'png', content: image.slice('data:image/png;base64,'.length), source: tab.url, title: tab.title || ''};
  } finally {
    if (switched && (await currentTab())?.id === tab.id) await chrome.tabs.update(previous.id, {active: true});
  }
}

async function handle(message, sender) {
  const {inbox, source} = await chrome.storage.session.get(['inbox', 'source']);
  if (!inbox || sender.tab?.id !== inbox.tabId || sender.url !== inbox.url || !localInbox(sender.url)) {
    throw new Error('Click the Blinders extension on this inbox first.');
  }
  if (message.op === 'disconnect') {
    await chrome.storage.session.remove('source');
    if (source) await chrome.action.setBadgeText({tabId: source.tabId, text: ''}).catch(() => {});
    return {};
  }
  const tab = source && await chrome.tabs.get(source.tabId).catch(() => null);
  if (!tab?.url || new URL(tab.url).origin !== source.origin) {
    throw new Error('Click the Blinders extension on the research tab you want to connect.');
  }
  if (message.op === 'status') return {title: tab.title || tab.url, pair: source.pair};
  if (message.pair && message.pair !== source.pair) throw new Error('The connected tab changed.');
  if (!['text', 'png'].includes(message.op)) throw new Error('Unknown capture action.');
  const capture = message.op === 'text' ? await selectedText(tab, message.selector) : await visibleTab(tab, inbox);
  const address = new URL(capture.source);
  capture.source = address.origin + address.pathname;
  return capture;
}

chrome.runtime.onMessageExternal.addListener((message, sender, respond) => {
  handle(message, sender).then(value => respond({value})).catch(error => respond({error: error.message}));
  return true;
});
