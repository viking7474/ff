/* Camoufox RDP Input - WebSocket bridge to Python controller */
"use strict";

const RECONNECT_MS = 2000;
const PREF_KEY = "extensions.winfox.ws_port";
let ws = null;
let wsPort = 8775;
let reconnectTimer = null;

// Proxy config (injected by RDPBrowser into this file before launch)
let proxyConfig = null;
let proxyCredentials = null;

// --- Network response capture ---
let capturePatterns = [];   // URL substrings to match
let capturedResponses = []; // {url, status, body, timestamp}
const MAX_CAPTURES = 50;

// --- Request spy: captures outgoing request headers + body + response for URL patterns ---
let spyPatterns = [];
let spyPending = new Map();   // requestId -> partial entry
let spyResults = [];          // completed {url, method, headers, body, responseBody, timestamp}
let requestEvents = [];       // request-start events
const MAX_SPY = 100;
const MAX_REQUEST_EVENTS = 200;

function setupCaptureListener() {
  // Remove existing listener if any
  if (browser.webRequest.onBeforeRequest.hasListener(onBeforeRequestCapture)) {
    browser.webRequest.onBeforeRequest.removeListener(onBeforeRequestCapture);
  }
  if (capturePatterns.length === 0) return;

  browser.webRequest.onBeforeRequest.addListener(
    onBeforeRequestCapture,
    { urls: ["<all_urls>"] },
    ["blocking"]
  );
}

function onBeforeRequestCapture(details) {
  const url = details.url;
  const matched = capturePatterns.some(p => url.includes(p));
  if (!matched) return {};

  const filter = browser.webRequest.filterResponseData(details.requestId);
  const chunks = [];

  filter.ondata = (event) => {
    chunks.push(new Uint8Array(event.data));
    filter.write(event.data); // pass through to browser
  };

  filter.onstop = () => {
    filter.close();
    // Decode the full response
    try {
      const totalLen = chunks.reduce((s, c) => s + c.byteLength, 0);
      const merged = new Uint8Array(totalLen);
      let offset = 0;
      for (const chunk of chunks) {
        merged.set(chunk, offset);
        offset += chunk.byteLength;
      }
      const body = new TextDecoder("utf-8").decode(merged);
      capturedResponses.push({
        url: url,
        status: null,
        body: body,
        timestamp: Date.now(),
      });
      // Trim old entries
      if (capturedResponses.length > MAX_CAPTURES) {
        capturedResponses = capturedResponses.slice(-MAX_CAPTURES);
      }
    } catch (e) {
      console.error("[cap] decode error:", e);
    }
  };

  filter.onerror = () => {
    try { filter.close(); } catch (_) {}
  };

  return {};
}

// --- Spy listeners ---

function setupSpyListeners() {
  if (browser.webRequest.onBeforeRequest.hasListener(onSpyRequest)) {
    browser.webRequest.onBeforeRequest.removeListener(onSpyRequest);
  }
  if (browser.webRequest.onSendHeaders.hasListener(onSpyHeaders)) {
    browser.webRequest.onSendHeaders.removeListener(onSpyHeaders);
  }
  if (browser.webRequest.onCompleted.hasListener(onSpyCompleted)) {
    browser.webRequest.onCompleted.removeListener(onSpyCompleted);
  }
  if (browser.webRequest.onErrorOccurred.hasListener(onSpyError)) {
    browser.webRequest.onErrorOccurred.removeListener(onSpyError);
  }
  if (spyPatterns.length === 0) return;

  browser.webRequest.onBeforeRequest.addListener(
    onSpyRequest,
    { urls: ["<all_urls>"] },
    ["blocking", "requestBody"]
  );
  browser.webRequest.onSendHeaders.addListener(
    onSpyHeaders,
    { urls: ["<all_urls>"] },
    ["requestHeaders"]
  );
  browser.webRequest.onCompleted.addListener(
    onSpyCompleted,
    { urls: ["<all_urls>"] },
    ["responseHeaders"]
  );
  browser.webRequest.onErrorOccurred.addListener(
    onSpyError,
    { urls: ["<all_urls>"] }
  );
}

function onSpyRequest(details) {
  if (!spyPatterns.some(p => details.url.includes(p))) return {};

  let bodyText = null;
  if (details.requestBody && details.requestBody.raw) {
    try {
      const parts = details.requestBody.raw.map(p => new Uint8Array(p.bytes));
      const total = parts.reduce((s, p) => s + p.byteLength, 0);
      const merged = new Uint8Array(total);
      let off = 0;
      for (const p of parts) { merged.set(p, off); off += p.byteLength; }
      bodyText = new TextDecoder("utf-8").decode(merged);
    } catch (_) { bodyText = "[decode error]"; }
  } else if (details.requestBody && details.requestBody.formData) {
    bodyText = JSON.stringify(details.requestBody.formData);
  }

  const entry = {
    url: details.url,
    method: details.method,
    body: bodyText,
    headers: null,
    responseHeaders: null,
    responseBody: null,
    status: null,
    error: null,
    state: "request",
    timestamp: Date.now(),
  };
  spyPending.set(details.requestId, entry);
  requestEvents.push({ ...entry });
  if (requestEvents.length > MAX_REQUEST_EVENTS) {
    requestEvents = requestEvents.slice(-MAX_REQUEST_EVENTS);
  }

  // Also capture response body via filterResponseData
  try {
    const filter = browser.webRequest.filterResponseData(details.requestId);
    const chunks = [];
    filter.ondata = (event) => {
      chunks.push(new Uint8Array(event.data));
      filter.write(event.data);
    };
    filter.onstop = () => {
      filter.close();
      try {
        const totalLen = chunks.reduce((s, c) => s + c.byteLength, 0);
        const merged = new Uint8Array(totalLen);
        let off = 0;
        for (const c of chunks) { merged.set(c, off); off += c.byteLength; }
        entry.responseBody = new TextDecoder("utf-8").decode(merged);
      } catch (_) {}
      entry.state = "finished";
      spyResults.push(entry);
      spyPending.delete(details.requestId);
      if (spyResults.length > MAX_SPY) spyResults = spyResults.slice(-MAX_SPY);
    };
    filter.onerror = () => {
      try { filter.close(); } catch (_) {}
      entry.state = entry.error ? "failed" : "finished";
      spyResults.push(entry);
      spyPending.delete(details.requestId);
    };
  } catch (_) {
    // filterResponseData not available, save without response
    entry.state = "finished";
    spyResults.push(entry);
    spyPending.delete(details.requestId);
  }

  return {};
}

function onSpyHeaders(details) {
  const entry = spyPending.get(details.requestId);
  if (!entry) return;
  entry.headers = {};
  for (const h of details.requestHeaders) {
    entry.headers[h.name] = h.value;
  }
}

function onSpyCompleted(details) {
  const entry = spyPending.get(details.requestId);
  if (!entry) return;
  entry.status = details.statusCode || null;
  if (details.responseHeaders) {
    entry.responseHeaders = {};
    for (const h of details.responseHeaders) {
      entry.responseHeaders[h.name] = h.value;
    }
  }
}

function onSpyError(details) {
  if (!spyPatterns.some(p => details.url.includes(p))) return;
  const entry = spyPending.get(details.requestId) || {
    url: details.url,
    method: details.method || "GET",
    body: null,
    headers: null,
    responseHeaders: null,
    responseBody: null,
    status: null,
    error: null,
    state: "request",
    timestamp: Date.now(),
  };
  entry.error = details.error || "unknown";
  entry.state = "failed";
  spyPending.delete(details.requestId);
  spyResults.push(entry);
  if (spyResults.length > MAX_SPY) spyResults = spyResults.slice(-MAX_SPY);
}

async function initPort() {
  // Read port from Firefox pref (set by RDPBrowser per-instance)
  try {
    const port = await browser.nativeInput.getPort();
    if (port && port > 0) {
      wsPort = port;
      return;
    }
  } catch (_) {}
  // Fallback: scan ports 8775-8790
  for (let port = 8775; port <= 8790; port++) {
    try {
      const testWs = new WebSocket(`ws://127.0.0.1:${port}`);
      await new Promise((resolve, reject) => {
        testWs.addEventListener("open", () => {
          wsPort = port;
          testWs.close();
          resolve();
        });
        testWs.addEventListener("error", () => reject());
        setTimeout(() => reject(), 300);
      });
      break;
    } catch (_) {}
  }
}

function connect() {
  if (ws && ws.readyState === WebSocket.OPEN) return;

  try {
    ws = new WebSocket(`ws://127.0.0.1:${wsPort}`);
  } catch (_) {
    return;
  }

  ws.addEventListener("open", () => {
    console.log(`[ext] Connected on port ${wsPort}`);
    ws.send(JSON.stringify({ type: "hello", extensionId: "{d4a1e2b3-8f7c-4e5d-9a6b-3c2d1e0f4a5b}" }));
  });

  ws.addEventListener("message", async (event) => {
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch (_) {
      return;
    }

    const { id, cmd, params } = msg;
    let result = null;
    let error = null;

    try {
      switch (cmd) {
        case "click":
          await browser.nativeInput.click(
            params.tabId, params.x, params.y, params.button || 0
          );
          result = { ok: true };
          break;

        case "moveTo":
          await browser.nativeInput.moveTo(params.tabId, params.x, params.y);
          result = { ok: true };
          break;

        case "mouseDown":
          await browser.nativeInput.mouseDown(
            params.tabId, params.x, params.y, params.button || 0
          );
          result = { ok: true };
          break;

        case "mouseUp":
          await browser.nativeInput.mouseUp(
            params.tabId, params.x, params.y, params.button || 0
          );
          result = { ok: true };
          break;

        case "scroll":
          await browser.nativeInput.scroll(
            params.tabId, params.x, params.y, params.deltaX, params.deltaY
          );
          result = { ok: true };
          break;

        case "type":
          await browser.nativeInput.type(params.tabId, params.text);
          result = { ok: true };
          break;

        case "keyPress":
          await browser.nativeInput.keyPress(params.tabId, params.key);
          result = { ok: true };
          break;

        case "getActiveTab": {
          const tabs = await browser.tabs.query({ active: true, currentWindow: true });
          result = tabs.length > 0 ? { tabId: tabs[0].id, url: tabs[0].url } : null;
          break;
        }

        case "createTab": {
          const tab = await browser.tabs.create({
            url: params.url || "about:blank",
            active: params.active !== false,
          });
          result = { tabId: tab.id, url: tab.url };
          break;
        }

        case "activateTab": {
          const tab = await browser.tabs.update(params.tabId, { active: true });
          result = { tabId: tab.id, url: tab.url, active: tab.active };
          break;
        }

        case "closeTab": {
          await browser.tabs.remove(params.tabId);
          result = { ok: true, tabId: params.tabId };
          break;
        }

        case "screenshot": {
          const dataUrl = await browser.tabs.captureVisibleTab(null, {
            format: "png",
          });
          result = { dataUrl };
          break;
        }

        case "setProxyAuth":
          proxyAuth = {
            username: params.username,
            password: params.password,
          };
          result = { ok: true };
          break;

        case "startCapture":
          capturePatterns = params.patterns || [];
          capturedResponses = [];
          setupCaptureListener();
          result = { ok: true, patterns: capturePatterns };
          break;

        case "stopCapture":
          capturePatterns = [];
          setupCaptureListener();
          result = { ok: true };
          break;

        case "getCapturedResponses": {
          const minTs = params.since || 0;
          const filtered = capturedResponses.filter(r => r.timestamp > minTs);
          result = { responses: filtered };
          break;
        }

        case "clearCaptures":
          capturedResponses = [];
          result = { ok: true };
          break;

        case "navigate":
          await browser.nativeInput.navigateTo(params.tabId, params.url);
          result = { ok: true };
          break;

        case "startSpy":
          spyPatterns = params.patterns || [];
          spyPending = new Map();
          spyResults = [];
          requestEvents = [];
          setupSpyListeners();
          result = { ok: true, patterns: spyPatterns };
          break;

        case "stopSpy":
          spyPatterns = [];
          setupSpyListeners();
          result = { ok: true };
          break;

        case "getSpiedRequests": {
          const spySince = params.since || 0;
          const spyFiltered = spyResults.filter(r => r.timestamp > spySince);
          result = { requests: spyFiltered };
          break;
        }

        case "getRequestEvents": {
          const reqSince = params.since || 0;
          const reqFiltered = requestEvents.filter(r => r.timestamp > reqSince);
          result = { requests: reqFiltered };
          break;
        }

        case "clearSpied":
          spyResults = [];
          spyPending = new Map();
          requestEvents = [];
          result = { ok: true };
          break;

        case "bgFetch": {
          // Fetch from extension background (bypasses page JS monkey-patches)
          const resp = await fetch(params.url, {
            method: params.method || "GET",
            headers: params.headers || {},
            credentials: "include"  // send cookies
          });
          const text = await resp.text();
          result = { status: resp.status, body: text.substring(0, params.maxBody || 100000) };
          break;
        }

        case "clearCookies": {
          const domain = params.domain || null;
          const url = params.url || null;
          let removed = 0;
          let cookies;
          if (domain) {
            cookies = await browser.cookies.getAll({ domain });
          } else if (url) {
            cookies = await browser.cookies.getAll({ url });
          } else {
            cookies = await browser.cookies.getAll({});
          }
          for (const c of cookies) {
            const proto = c.secure ? "https://" : "http://";
            const cookieUrl = proto + c.domain.replace(/^\./, "") + c.path;
            try {
              await browser.cookies.remove({ url: cookieUrl, name: c.name });
              removed++;
            } catch (_) {}
          }
          result = { ok: true, removed };
          break;
        }

        case "getCookies": {
          const domain = params.domain || null;
          const url = params.url || null;
          let cookies;
          if (domain) {
            cookies = await browser.cookies.getAll({ domain });
          } else if (url) {
            cookies = await browser.cookies.getAll({ url });
          } else {
            cookies = await browser.cookies.getAll({});
          }
          result = { cookies };
          break;
        }

        case "setCookies": {
          const cookies = params.cookies || [];
          let set = 0;
          for (const c of cookies) {
            try {
              let cookieUrl = c.url || null;
              if (!cookieUrl && c.domain) {
                const proto = c.secure ? "https://" : "http://";
                cookieUrl = proto + String(c.domain).replace(/^\./, "") + (c.path || "/");
              }
              if (!cookieUrl) continue;
              const payload = {
                url: cookieUrl,
                name: c.name,
                value: c.value,
                domain: c.domain,
                path: c.path,
                secure: c.secure,
                httpOnly: c.httpOnly,
                sameSite: c.sameSite,
                expirationDate: c.expirationDate,
              };
              await browser.cookies.set(payload);
              set++;
            } catch (_) {}
          }
          result = { ok: true, set };
          break;
        }

        case "minimizeWindow": {
          // Minimize current window. Triggers real window.blur,
          // document.visibilitychange, visibilityState=hidden, and rAF throttle.
          // Anti-bot systems (PerimeterX, Shopee SFU) track these events.
          try {
            const win = await browser.windows.getCurrent();
            await browser.windows.update(win.id, { state: "minimized" });
            result = { ok: true, windowId: win.id };
          } catch (e) {
            error = e.message || String(e);
          }
          break;
        }

        case "restoreWindow": {
          try {
            const win = await browser.windows.getCurrent();
            await browser.windows.update(win.id, { state: "normal" });
            // Focus it too so window.focus fires
            await browser.windows.update(win.id, { focused: true });
            result = { ok: true };
          } catch (e) {
            error = e.message || String(e);
          }
          break;
        }

        case "closeOtherTabs": {
          const allTabs = await browser.tabs.query({ currentWindow: true });
          const keepId = params.keepTabId || null;
          let closed = 0;
          for (const t of allTabs) {
            if (keepId && t.id === keepId) continue;
            if (t.active && !keepId) continue;
            try {
              await browser.tabs.remove(t.id);
              closed++;
            } catch (_) {}
          }
          result = { ok: true, closed };
          break;
        }

        case "ping":
          result = { pong: true };
          break;

        default:
          error = `Unknown command: ${cmd}`;
      }
    } catch (e) {
      error = e.message || String(e);
    }

    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ id, result, error }));
    }
  });

  ws.addEventListener("close", () => {
    ws = null;
  });

  ws.addEventListener("error", () => {
    try { ws.close(); } catch (_) {}
    ws = null;
  });
}

// Cursor indicator: inject into every page via closed Shadow DOM
function injectCursor(tabId) {
  browser.tabs.executeScript(tabId, {
    file: "cursor.js",
    runAt: "document_idle",
    allFrames: false
  }).catch(() => {});
}

browser.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (changeInfo.status === "complete") {
    injectCursor(tabId);
  }
});

// Init: find port then connect
initPort().then(() => {
  connect();
  reconnectTimer = setInterval(() => {
    if (!ws || ws.readyState === WebSocket.CLOSED) {
      connect();
    }
  }, RECONNECT_MS);
});
