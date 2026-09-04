// Antigravity Edge Bridge - Background Service Worker
// Handles all commands and acts as the singleton bridge client.
const BRIDGE_URL = "http://127.0.0.1:18999";
let lastLog = "Initializing...";
let isPolling = false;

console.log("[Antigravity Bridge] Service worker loaded");

function log(msg) {
  lastLog = `[${new Date().toLocaleTimeString()}] ${msg}`;
  console.log(`[Antigravity Bridge] ${msg}`);
  try {
    chrome.storage.local.set({ lastLog });
  } catch (e) {}
}

async function postResult(cmdId, result) {
  try {
    await fetch(`${BRIDGE_URL}/result`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: cmdId, result: result || {} })
    });
  } catch (err) {
    log(`Failed to post result for ${cmdId}: ${err.message}`);
  }
}

async function getTargetTab(tabId) {
  if (tabId !== undefined && tabId !== null && tabId !== "") {
    try {
      return await chrome.tabs.get(Number(tabId));
    } catch (e) {
      return null;
    }
  }
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (tab) return tab;
  const [anyTab] = await chrome.tabs.query({ active: true });
  return anyTab || null;
}

function waitForTabLoad(tabId, timeoutMs = 15000) {
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener);
      resolve(false);
    }, timeoutMs);

    function listener(updatedTabId, changeInfo) {
      if (updatedTabId === tabId && changeInfo.status === "complete") {
        clearTimeout(timer);
        chrome.tabs.onUpdated.removeListener(listener);
        resolve(true);
      }
    }
    chrome.tabs.onUpdated.addListener(listener);
  });
}

async function execInTab(tabId, func, args = [], world = "ISOLATED") {
  try {
    const cleanArgs = (args || []).map(a => (a === undefined ? null : a));
    const results = await chrome.scripting.executeScript({
      target: { tabId },
      func,
      args: cleanArgs,
      world,
    });
    if (results && results[0]) {
      return results[0].result;
    }
    return { success: false, error: "Script injected but returned no result" };
  } catch (err) {
    return { success: false, error: err.message };
  }
}

const PageActions = {
  moveAt: (x, y) => {
    try {
      let style = document.getElementById("__ag_cursor_style");
      if (!style) {
        style = document.createElement("style");
        style.id = "__ag_cursor_style";
        style.textContent = `
          @keyframes __ag_click_pulse {
            0% { transform: translate(-50%, -50%) scale(0.3); opacity: 0.85; }
            100% { transform: translate(-50%, -50%) scale(2.0); opacity: 0; }
          }
          .__ag_cursor_wrap {
            position: fixed !important; pointer-events: none !important; z-index: 2147483647 !important;
            top: 0 !important; left: 0 !important; will-change: transform !important;
            transition: transform 0.08s cubic-bezier(0.2, 0, 0.2, 1) !important;
            filter: drop-shadow(0 2px 4px rgba(0,0,0,0.35)) drop-shadow(0 1px 2px rgba(0,0,0,0.25)) !important;
          }
          .__ag_cursor_svg { display: block !important; transform-origin: 0 0 !important; transition: transform 0.06s ease !important; }
          .__ag_cursor_pressed .__ag_cursor_svg { transform: scale(0.92) translate(1px, 1px) !important; }
          .__ag_cursor_ripple {
            position: fixed !important; pointer-events: none !important; z-index: 2147483646 !important;
            width: 24px !important; height: 24px !important; border-radius: 50% !important;
            border: 2px solid rgba(0, 120, 212, 0.85) !important; background: rgba(0, 120, 212, 0.15) !important;
            animation: __ag_click_pulse 0.35s cubic-bezier(0.1, 0.8, 0.3, 1) forwards !important;
          }
        `;
        (document.head || document.documentElement).appendChild(style);
      }

      let cur = document.getElementById("__ag_cursor");
      if (!cur) {
        cur = document.createElement("div");
        cur.id = "__ag_cursor";
        (document.body || document.documentElement).appendChild(cur);
      }
      cur.className = "__ag_cursor_wrap";
      cur.style.cssText = "position:fixed!important;pointer-events:none!important;z-index:2147483647!important;top:0!important;left:0!important;will-change:transform!important;background:transparent!important;border:none!important;box-shadow:none!important;width:auto!important;height:auto!important;border-radius:0!important;padding:0!important;margin:0!important;filter:drop-shadow(0 2px 4px rgba(0,0,0,0.35)) drop-shadow(0 1px 2px rgba(0,0,0,0.25))!important;transition:transform 0.08s cubic-bezier(0.2, 0, 0.2, 1)!important;";

      const el = document.elementFromPoint(x, y);
      let cursorType = "arrow";
      let offsetX = 0;
      let offsetY = 0;

      if (el) {
        const comp = window.getComputedStyle(el);
        const isInput = el.matches("input[type='text'], input[type='password'], input[type='search'], input:not([type]), textarea, [contenteditable='true']");
        const isClickable = comp.cursor === "pointer" || el.matches("button, a, select, [role='button'], [role='checkbox'], [role='radio'], [role='menuitem'], [role='treeitem'], [role='tab'], fluent-button, fluent-tree-item, fluent-checkbox, fluent-radio, svg");

        if (isInput) {
          cursorType = "text";
          offsetX = -8;
          offsetY = -12;
        } else if (isClickable) {
          cursorType = "pointer";
          offsetX = -5;
          offsetY = -1;
        }
      }

      let svgHtml = "";
      if (cursorType === "pointer") {
        svgHtml = `<svg class="__ag_cursor_svg" width="22" height="26" viewBox="0 0 22 26" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M6.5 1.5C6.5 0.67 5.83 0 5 0C4.17 0 3.5 0.67 3.5 1.5V11.5L2.3 10.3C1.7 9.7 0.8 9.7 0.2 10.3C-0.3 10.8 -0.3 11.7 0.2 12.3L4.5 16.6C5.9 18 7.8 18.5 9.8 18.5H11.5C14.5 18.5 17 16 17 13V7.5C17 6.67 16.33 6 15.5 6C14.67 6 14 6.67 14 7.5V8.5C14 7.67 13.33 7 12.5 7C11.67 7 11 7.67 11 8.5V7C11 6.17 10.33 5.5 9.5 5.5C8.67 5.5 8 6.17 8 7V1.5C8 0.67 7.33 0 6.5 0" transform="translate(1, 1)" fill="#FFFFFF" stroke="#1A1A1A" stroke-width="1.3" stroke-linejoin="round"/></svg>`;
      } else if (cursorType === "text") {
        svgHtml = `<svg class="__ag_cursor_svg" width="16" height="24" viewBox="0 0 16 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M4 2H12M8 2V22M4 22H12" stroke="#111111" stroke-width="2" stroke-linecap="round"/><path d="M5 3H11M8 3V21M5 21H11" stroke="#FFFFFF" stroke-width="0.8" stroke-linecap="round"/></svg>`;
      } else {
        svgHtml = `<svg class="__ag_cursor_svg" width="22" height="24" viewBox="0 0 22 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M1.5 1V19.8L5.9 15.6L9.1 22.8L12 21.5L8.8 14.3H15.1L1.5 1Z" fill="#FFFFFF" stroke="#181818" stroke-width="1.5" stroke-linejoin="round"/></svg>`;
      }

      cur.innerHTML = svgHtml;
      cur.style.transform = `translate(${x + offsetX}px, ${y + offsetY}px)`;
    } catch (e) {}

    const el = document.elementFromPoint(x, y);
    if (el) {
      const lastEl = window.__ag_last_hovered_el;
      if (lastEl && lastEl !== el) {
        const outOpts = { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y };
        try {
          lastEl.dispatchEvent(new MouseEvent("mouseout", outOpts));
          lastEl.dispatchEvent(new MouseEvent("mouseleave", outOpts));
          lastEl.dispatchEvent(new PointerEvent("pointerout", outOpts));
          lastEl.dispatchEvent(new PointerEvent("pointerleave", outOpts));
        } catch (e) {}
      }
      window.__ag_last_hovered_el = el;

      const opts = { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y };
      el.dispatchEvent(new PointerEvent("pointerover", opts));
      el.dispatchEvent(new PointerEvent("pointerenter", opts));
      el.dispatchEvent(new MouseEvent("mouseover", opts));
      el.dispatchEvent(new MouseEvent("mouseenter", opts));
      el.dispatchEvent(new PointerEvent("pointermove", opts));
      el.dispatchEvent(new MouseEvent("mousemove", opts));
      return { success: true, x, y, tag: el.tagName, id: el.id, text: (el.innerText || el.value || "").substring(0, 50) };
    }
    return { success: true, x, y };
  },

  getInteractiveElements: () => {
    const selector = "button, a, input, select, textarea, [role='button'], [role='menuitem'], [role='treeitem'], [role='tab'], [onclick], .btn, [tabindex], fluent-button, fluent-text-field, fluent-search, fluent-anchor, fluent-select, fluent-checkbox, fluent-switch, fluent-radio, fluent-tree-item, fluent-tab, [id='MenuButton'], [id='SettingsButton'], svg[style*='cursor: pointer'], svg[style*='cursor:pointer']";
    const els = Array.from(document.querySelectorAll(selector));
    const results = [];
    els.forEach((el) => {
      const r = el.getBoundingClientRect();
      const visible = el.checkVisibility ? el.checkVisibility({ checkVisibilityCSS: true, checkOpacity: true }) : (r.width > 0 && r.height > 0);
      if (visible && r.width > 0 && r.height > 0) {
        let text = (el.innerText || el.value || el.title || el.placeholder || el.getAttribute("aria-label") || el.getAttribute("placeholder") || "").trim().replace(/\s+/g, " ");
        if (!text && el.shadowRoot) {
          const inner = el.shadowRoot.querySelector("input, textarea, button, [aria-label]");
          if (inner) {
            text = (inner.value || inner.placeholder || inner.getAttribute("aria-label") || inner.innerText || "").trim().replace(/\s+/g, " ");
          }
        }
        if (!text && el.querySelector("svg title")) {
          text = el.querySelector("svg title").textContent.trim();
        }
        if (text || el.id) {
          results.push({
            tag: el.tagName.toLowerCase(),
            id: el.id || "",
            text: text.substring(0, 50),
            role: el.getAttribute("role") || "",
            x: Math.round(r.x + r.width / 2),
            y: Math.round(r.y + r.height / 2),
            w: Math.round(r.width),
            h: Math.round(r.height)
          });
        }
      }
    });
    return { success: true, count: results.length, elements: results };
  },

  clickAt: (x, y) => {
    try {
      let cur = document.getElementById("__ag_cursor");
      if (cur) {
        cur.classList.add("__ag_cursor_pressed");
        setTimeout(() => cur.classList.remove("__ag_cursor_pressed"), 120);
      }
      const rip = document.createElement("div");
      rip.className = "__ag_cursor_ripple";
      rip.style.left = x + "px";
      rip.style.top = y + "px";
      (document.body || document.documentElement).appendChild(rip);
      setTimeout(() => rip.remove(), 380);
    } catch (e) {}

    const el = document.elementFromPoint(x, y);
    if (!el) return { success: false, error: `No element at point (${x}, ${y})` };
    try { el.focus(); } catch (e) {}

    const opts = { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y };
    el.dispatchEvent(new PointerEvent("pointerdown", opts));
    el.dispatchEvent(new MouseEvent("mousedown", opts));
    el.dispatchEvent(new PointerEvent("pointerup", opts));
    el.dispatchEvent(new MouseEvent("mouseup", opts));
    el.dispatchEvent(new MouseEvent("click", opts));

    return {
      success: true,
      tag: el.tagName,
      id: el.id,
      className: el.className,
      text: (el.innerText || el.value || "").substring(0, 100),
      x,
      y
    };
  },

  dblclickAt: (x, y) => {
    try {
      const rip = document.createElement("div");
      rip.className = "__ag_cursor_ripple";
      rip.style.left = x + "px";
      rip.style.top = y + "px";
      (document.body || document.documentElement).appendChild(rip);
      setTimeout(() => rip.remove(), 380);
    } catch (e) {}

    const opts = { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y };
    el.dispatchEvent(new MouseEvent("mousedown", opts));
    el.dispatchEvent(new MouseEvent("mouseup", opts));
    el.dispatchEvent(new MouseEvent("click", opts));
    el.dispatchEvent(new MouseEvent("mousedown", opts));
    el.dispatchEvent(new MouseEvent("mouseup", opts));
    el.dispatchEvent(new MouseEvent("click", opts));
    el.dispatchEvent(new MouseEvent("dblclick", opts));

    return {
      success: true,
      tag: el.tagName,
      id: el.id,
      text: (el.innerText || el.value || "").substring(0, 100),
      x,
      y
    };
  },

  clickElement: (selector, text) => {
    let el = null;
    if (selector) {
      el = document.querySelector(selector);
    }
    if (!el && text) {
      const lower = text.toLowerCase().trim();
      const candidates = Array.from(document.querySelectorAll("button, a, input[type='button'], input[type='submit'], [role='button'], label, .btn, span, td, tr, fluent-button, fluent-anchor, fluent-tree-item, fluent-tab, fluent-checkbox, fluent-switch, fluent-radio, [id='MenuButton'], [id='SettingsButton']"));
      el = candidates.find(c => (c.innerText || c.value || c.textContent || "").toLowerCase().trim() === lower) ||
           candidates.find(c => (c.innerText || c.value || c.textContent || "").toLowerCase().includes(lower));
    }
    if (!el) {
      return { success: false, error: `Element not found: selector="${selector}", text="${text}"` };
    }

    try { el.scrollIntoView({ behavior: "instant", block: "center" }); } catch (e) {}
    try { el.focus(); } catch (e) {}

    const r = el.getBoundingClientRect();
    try { if (window._renderCursor) window._renderCursor(Math.round(r.x + r.width / 2), Math.round(r.y + r.height / 2), true); } catch (e) {}

    const mouseOpts = { bubbles: true, cancelable: true, view: window };
    el.dispatchEvent(new MouseEvent("mousedown", mouseOpts));
    el.dispatchEvent(new MouseEvent("mouseup", mouseOpts));
    el.dispatchEvent(new MouseEvent("click", mouseOpts));

    return {
      success: true,
      tag: el.tagName,
      id: el.id,
      text: (el.innerText || el.value || "").substring(0, 100)
    };
  },

  dblclickElement: (selector, text) => {
    let el = null;
    if (selector) {
      el = document.querySelector(selector);
    }
    if (!el && text) {
      const lower = text.toLowerCase().trim();
      const all = Array.from(document.querySelectorAll("tr, div, td, span, button, a"));
      el = all.find(c => (c.innerText || "").trim() === lower) ||
           all.find(c => (c.innerText || "").includes(lower));
    }
    if (!el) {
      return { success: false, error: `Element not found: selector="${selector}", text="${text}"` };
    }

    try { el.scrollIntoView({ behavior: "instant", block: "center" }); } catch (e) {}
    try { el.focus(); } catch (e) {}

    const mouseOpts = { bubbles: true, cancelable: true, view: window };
    el.dispatchEvent(new MouseEvent("mousedown", mouseOpts));
    el.dispatchEvent(new MouseEvent("mouseup", mouseOpts));
    el.dispatchEvent(new MouseEvent("click", mouseOpts));
    el.dispatchEvent(new MouseEvent("mousedown", mouseOpts));
    el.dispatchEvent(new MouseEvent("mouseup", mouseOpts));
    el.dispatchEvent(new MouseEvent("click", mouseOpts));
    el.dispatchEvent(new MouseEvent("dblclick", mouseOpts));

    return {
      success: true,
      tag: el.tagName,
      id: el.id,
      text: (el.innerText || "").substring(0, 100)
    };
  },

  openFileInManager: (fileId) => {
    const rows = Array.from(document.querySelectorAll('tr[role="row"]'));
    const targetRow = rows.find(r => {
      const idEl = r.querySelector('[name="fileid"]');
      return idEl && idEl.innerText.trim() === String(fileId);
    }) || rows.find(r => Array.from(r.querySelectorAll('td')).some(td => td.innerText.trim() === String(fileId)));
    if (!targetRow) {
      return { success: false, error: `File row with ID ${fileId} not found in file list` };
    }

    const cell = targetRow.querySelector('td:nth-child(5)') || targetRow.querySelector('[name="fileid"]') || targetRow;
    try { cell.scrollIntoView({ behavior: "instant", block: "center" }); } catch (e) {}

    const mouseOpts = { bubbles: true, cancelable: true, view: window };
    cell.dispatchEvent(new MouseEvent("mousedown", mouseOpts));
    cell.dispatchEvent(new MouseEvent("mouseup", mouseOpts));
    cell.dispatchEvent(new MouseEvent("click", mouseOpts));
    cell.dispatchEvent(new MouseEvent("mousedown", mouseOpts));
    cell.dispatchEvent(new MouseEvent("mouseup", mouseOpts));
    cell.dispatchEvent(new MouseEvent("click", mouseOpts));
    cell.dispatchEvent(new MouseEvent("dblclick", mouseOpts));

    return {
      success: true,
      fileId,
      rowText: targetRow.innerText.replace(/\s+/g, " ").trim().substring(0, 100)
    };
  },

  typeText: (selector, text, clear) => {
    let el = null;
    if (selector) {
      el = document.querySelector(selector);
    }
    if (!el) {
      if (document.activeElement && (document.activeElement.tagName === "INPUT" || document.activeElement.tagName === "TEXTAREA" || document.activeElement.isContentEditable || document.activeElement.tagName.startsWith("FLUENT-"))) {
        el = document.activeElement;
      }
    }
    if (!el) {
      return { success: false, error: `Input element not found: selector="${selector}"` };
    }

    try { el.scrollIntoView({ behavior: "instant", block: "center" }); } catch (e) {}
    try { el.focus(); } catch (e) {}

    const targetInput = el.shadowRoot ? (el.shadowRoot.querySelector("input, textarea") || el) : el;

    if (clear) {
      el.value = "";
      if (targetInput !== el) targetInput.value = "";
    }
    const val = (clear ? "" : (targetInput.value || el.value || "")) + text;
    el.value = val;
    if (targetInput !== el) targetInput.value = val;
    if (el.setAttribute) el.setAttribute("current-value", val);

    targetInput.dispatchEvent(new Event("input", { bubbles: true }));
    targetInput.dispatchEvent(new Event("change", { bubbles: true }));
    if (targetInput !== el) {
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    }

    return {
      success: true,
      tag: el.tagName,
      id: el.id,
      name: el.name || el.getAttribute("name") || "",
      value: val
    };
  },

  pressKey: (key) => {
    const el = document.activeElement || document.body;
    const opts = { key, code: key, bubbles: true, cancelable: true, view: window };
    el.dispatchEvent(new KeyboardEvent("keydown", opts));
    el.dispatchEvent(new KeyboardEvent("keypress", opts));
    el.dispatchEvent(new KeyboardEvent("keyup", opts));

    if (key === "Enter" && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName.startsWith("FLUENT-"))) {
      el.dispatchEvent(new Event("change", { bubbles: true }));
      const form = el.closest("form");
      if (form) {
        if (form.requestSubmit) form.requestSubmit();
        else form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      }
    }
    return { success: true, key, target: el.tagName };
  },

  scrollPage: (x, y) => {
    window.scrollBy(x, y);
    return { success: true, scrollX: window.scrollX, scrollY: window.scrollY };
  },

  getSnapshot: () => {
    const inputs = Array.from(document.querySelectorAll("input, select, textarea, fluent-text-field, fluent-search, fluent-select, fluent-checkbox")).map(el => {
      const inner = el.shadowRoot ? el.shadowRoot.querySelector("input, textarea") : null;
      const type = el.getAttribute("type") || (inner && inner.type) || el.type || "";
      const val = el.value || (inner && inner.value) || "";
      return {
        tag: el.tagName.toLowerCase(),
        type: type,
        id: el.id || "",
        name: el.name || el.getAttribute("name") || "",
        value: type === "password" ? "••••••" : val,
        placeholder: el.placeholder || el.getAttribute("placeholder") || (inner && inner.placeholder) || "",
        label: (el.labels && el.labels[0] ? el.labels[0].innerText : "") || (document.querySelector(`label[for="${el.id}"]`)?.innerText || ""),
        disabled: el.disabled || false,
        visible: el.checkVisibility
          ? el.checkVisibility({ checkVisibilityCSS: true, checkOpacity: true })
          : el.offsetParent !== null
      };
    }).filter(i => i.visible);

    const buttons = Array.from(document.querySelectorAll("button, input[type='button'], input[type='submit'], [role='button'], a.btn, fluent-button, fluent-anchor")).map(el => ({
      tag: el.tagName.toLowerCase(),
      id: el.id || "",
      text: (el.innerText || el.value || el.textContent || "").trim(),
      role: el.getAttribute("role") || "",
      disabled: el.disabled || false,
      visible: el.checkVisibility
        ? el.checkVisibility({ checkVisibilityCSS: true, checkOpacity: true })
        : el.offsetParent !== null
    })).filter(b => b.visible && b.text);

    return {
      title: document.title,
      url: window.location.href,
      readyState: document.readyState,
      headings: Array.from(document.querySelectorAll("h1, h2, h3")).map(h => h.innerText.trim()).filter(Boolean),
      inputs,
      buttons
    };
  },

  resolveTarget: (query) => {
    if (!query) return { found: false, error: "Empty target query" };
    if (typeof query === "object" && query.x !== undefined && query.y !== undefined) {
      return { found: true, x: Number(query.x), y: Number(query.y) };
    }

    const q = String(query).trim();
    const qLower = q.toLowerCase();

    function queryAllDeep(root, selector) {
      let nodes = [];
      try { nodes = Array.from(root.querySelectorAll(selector)); } catch(e) {}
      try {
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
        let n;
        while ((n = walker.nextNode())) {
          if (n.shadowRoot) {
            nodes = nodes.concat(queryAllDeep(n.shadowRoot, selector));
          }
        }
      } catch(e) {}
      return nodes;
    }

    let el = null;
    // 1. Direct CSS selector if query has selector syntax
    if (/^[#\.\[:]/.test(q) || q.includes(">") || q.includes(" ") || q.includes("[")) {
      try {
        el = document.querySelector(q);
        if (!el) {
          const deep = queryAllDeep(document, q);
          if (deep.length > 0) el = deep[0];
        }
      } catch (e) {}
    }

    // 2. Semantic and text search across interactive and candidate elements
    if (!el) {
      const allEls = queryAllDeep(document, "button, a, input, select, textarea, [role], label, tr, td, th, li, span, div, p, h1, h2, h3, h4, [onclick], fluent-button, fluent-text-field, fluent-anchor, fluent-checkbox, fluent-radio, fluent-tree-item, fluent-tab, [id='MenuButton'], [id='SettingsButton']");

      // Strategy A: Exact text / value / label match
      el = allEls.find(c => {
        const txt = (c.innerText || c.value || c.getAttribute("aria-label") || c.getAttribute("placeholder") || c.title || "").trim().toLowerCase();
        return txt === qLower;
      });

      // Strategy B: Label match
      if (!el) {
        const labels = queryAllDeep(document, "label");
        const matchedLabel = labels.find(l => (l.innerText || "").trim().toLowerCase() === qLower || (l.innerText || "").toLowerCase().includes(qLower));
        if (matchedLabel) {
          if (matchedLabel.htmlFor) el = document.getElementById(matchedLabel.htmlFor);
          if (!el) el = matchedLabel.querySelector("input, select, textarea");
          if (!el) el = matchedLabel;
        }
      }

      // Strategy C: Substring match on actionable elements
      if (!el) {
        el = allEls.find(c => {
          const isActionable = c.matches("button, a, [role='button'], [role='menuitem'], [role='tab'], [role='treeitem'], input, select, textarea, fluent-button, fluent-tree-item");
          if (!isActionable) return false;
          const txt = (c.innerText || c.value || c.getAttribute("aria-label") || c.getAttribute("placeholder") || "").trim().toLowerCase();
          return txt.includes(qLower);
        });
      }

      // Strategy D: Substring match anywhere
      if (!el) {
        el = allEls.find(c => {
          const txt = (c.innerText || c.value || c.getAttribute("aria-label") || c.getAttribute("placeholder") || "").trim().toLowerCase();
          return txt.includes(qLower);
        });
      }
    }

    if (!el) return { found: false, error: `Target not found: "${q}"` };

    try {
      el.scrollIntoView({ behavior: "instant", block: "center", inline: "center" });
    } catch (e) {}

    let r = el.getBoundingClientRect();
    if ((r.width === 0 || r.height === 0) && el.firstElementChild) {
      r = el.firstElementChild.getBoundingClientRect();
    }
    const maxW = window.innerWidth || 1920;
    const maxH = window.innerHeight || 1080;
    const rawX = Math.round(r.x + r.width / 2);
    const rawY = Math.round(r.y + r.height / 2);
    const x = Math.max(0, Math.min(maxW - 1, rawX));
    const y = Math.max(0, Math.min(maxH - 1, rawY));

    return {
      found: true,
      x,
      y,
      width: Math.round(r.width),
      height: Math.round(r.height),
      tag: el.tagName.toLowerCase(),
      id: el.id || "",
      text: (el.innerText || el.value || "").trim().substring(0, 60)
    };
  },

  evalCode: (code) => {
    try {
      const result = eval(code);
      return { success: true, result };
    } catch (e) {
      return { success: false, error: e.toString() };
    }
  }
};

// --- CDP Native Input Engine (chrome.debugger) ---
const attachedTabs = new Set();

function isDebuggerAttached(tabId) {
  return new Promise((resolve) => {
    try {
      chrome.debugger.getTargets((targets) => {
        if (chrome.runtime.lastError || !targets) return resolve(false);
        const t = targets.find(target => target.tabId === Number(tabId));
        resolve(Boolean(t && t.attached));
      });
    } catch (e) {
      resolve(false);
    }
  });
}

async function ensureDebugger(tabId) {
  const attached = await isDebuggerAttached(tabId);
  if (attached) {
    attachedTabs.add(tabId);
    return true;
  }
  return new Promise((resolve) => {
    chrome.debugger.attach({ tabId }, "1.3", () => {
      if (chrome.runtime.lastError) {
        const msg = (chrome.runtime.lastError.message || "").toLowerCase();
        if (msg.includes("already attached")) {
          attachedTabs.add(tabId);
          return resolve(true);
        }
        attachedTabs.delete(tabId);
        log(`CDP Debugger attach failed for tab ${tabId}: ${msg}`);
        return resolve(false);
      }
      attachedTabs.add(tabId);
      log(`CDP Debugger attached to tab ${tabId}`);
      resolve(true);
    });
  });
}

chrome.debugger.onDetach.addListener((source, reason) => {
  if (source && source.tabId) {
    attachedTabs.delete(source.tabId);
    log(`CDP Debugger detached from tab ${source.tabId}: ${reason}`);
  }
});

chrome.tabs.onRemoved.addListener((tabId) => {
  attachedTabs.delete(tabId);
});

async function cdpSend(tabId, method, params = {}) {
  const sendOnce = () => {
    return new Promise((resolve, reject) => {
      chrome.debugger.sendCommand({ tabId }, method, params, (result) => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
        } else {
          resolve(result || {});
        }
      });
    });
  };

  try {
    if (!attachedTabs.has(tabId)) {
      await ensureDebugger(tabId);
    }
    return await sendOnce();
  } catch (err) {
    if (err.message && err.message.includes("not attached")) {
      attachedTabs.delete(tabId);
      const reattached = await ensureDebugger(tabId);
      if (reattached) {
        return await sendOnce();
      }
    }
    throw err;
  }
}

// Native Hardware Mouse Movements & Actions
async function nativeMove(tabId, x, y) {
  await cdpSend(tabId, "Input.dispatchMouseEvent", {
    type: "mouseMoved",
    x,
    y
  });
  // Also sync visual cursor overlay
  execInTab(tabId, PageActions.moveAt, [x, y]).catch(() => {});
}

async function nativeClick(tabId, x, y, button = "left", clickCount = 1) {
  const cx = Math.round(Number(x));
  const cy = Math.round(Number(y));
  const btnMask = button === "right" ? 2 : (button === "middle" ? 4 : 1);
  await cdpSend(tabId, "Input.dispatchMouseEvent", {
    type: "mouseMoved",
    x: cx,
    y: cy
  });
  await cdpSend(tabId, "Input.dispatchMouseEvent", {
    type: "mousePressed",
    x: cx,
    y: cy,
    button,
    buttons: btnMask,
    clickCount
  });
  await new Promise(r => setTimeout(r, 40));
  await cdpSend(tabId, "Input.dispatchMouseEvent", {
    type: "mouseReleased",
    x: cx,
    y: cy,
    button,
    buttons: 0,
    clickCount
  });
  // Visual ripple & click animation in page
  execInTab(tabId, (px, py) => {
    try {
      if (window._renderCursor) window._renderCursor(px, py, true);
    } catch (e) {}
  }, [cx, cy]).catch(() => {});
}

async function nativeDrag(tabId, fromX, fromY, toX, toY, steps = 12) {
  const fX = Math.round(Number(fromX));
  const fY = Math.round(Number(fromY));
  const tX = Math.round(Number(toX));
  const tY = Math.round(Number(toY));
  await cdpSend(tabId, "Input.dispatchMouseEvent", {
    type: "mouseMoved",
    x: fX,
    y: fY
  });
  await cdpSend(tabId, "Input.dispatchMouseEvent", {
    type: "mousePressed",
    x: fX,
    y: fY,
    button: "left",
    buttons: 1,
    clickCount: 1
  });
  await new Promise(r => setTimeout(r, 50));

  for (let i = 1; i <= steps; i++) {
    const cx = Math.round(fX + (tX - fX) * (i / steps));
    const cy = Math.round(fY + (tY - fY) * (i / steps));
    await cdpSend(tabId, "Input.dispatchMouseEvent", {
      type: "mouseMoved",
      x: cx,
      y: cy,
      button: "left",
      buttons: 1
    });
    execInTab(tabId, PageActions.moveAt, [cx, cy]).catch(() => {});
    await new Promise(r => setTimeout(r, 20));
  }

  await cdpSend(tabId, "Input.dispatchMouseEvent", {
    type: "mouseReleased",
    x: tX,
    y: tY,
    button: "left",
    buttons: 0,
    clickCount: 1
  });
}

async function nativeScroll(tabId, x, y, deltaX, deltaY) {
  await cdpSend(tabId, "Input.dispatchMouseEvent", {
    type: "mouseWheel",
    x: Math.round(Number(x)),
    y: Math.round(Number(y)),
    deltaX: Number(deltaX || 0),
    deltaY: Number(deltaY || 0)
  });
}

const KEY_CODES = {
  Enter: 13, Tab: 9, Escape: 27, Backspace: 8, Space: 32,
  ArrowLeft: 37, ArrowUp: 38, ArrowRight: 39, ArrowDown: 40,
  Delete: 46, Home: 36, End: 35, PageUp: 33, PageDown: 34
};

async function nativeKey(tabId, keyStr) {
  let modifiers = 0;
  let key = String(keyStr || "");
  if (key.includes("+")) {
    const parts = key.split("+");
    key = parts.pop();
    for (const mod of parts) {
      const m = mod.toLowerCase();
      if (m === "ctrl" || m === "control") modifiers |= 2;
      else if (m === "alt") modifiers |= 1;
      else if (m === "shift") modifiers |= 4;
      else if (m === "meta" || m === "cmd" || m === "win") modifiers |= 8;
    }
  }

  const vk = KEY_CODES[key] || (key.length === 1 ? key.toUpperCase().charCodeAt(0) : 0);
  await cdpSend(tabId, "Input.dispatchKeyEvent", {
    type: "rawKeyDown",
    key,
    code: key,
    modifiers,
    windowsVirtualKeyCode: vk,
    nativeVirtualKeyCode: vk
  });
  if (key.length === 1 || key === "Enter") {
    const txt = key === "Enter" ? "\r" : key;
    await cdpSend(tabId, "Input.dispatchKeyEvent", {
      type: "char",
      text: txt,
      unmodifiedText: txt,
      modifiers
    });
  }
  await cdpSend(tabId, "Input.dispatchKeyEvent", {
    type: "keyUp",
    key,
    code: key,
    modifiers,
    windowsVirtualKeyCode: vk,
    nativeVirtualKeyCode: vk
  });
}

async function resolveTargetWithWait(tabId, target, timeoutMs = 5000) {
  if (typeof target === "object" && target.x !== undefined && target.y !== undefined) {
    return { found: true, x: Number(target.x), y: Number(target.y) };
  }
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const res = await execInTab(tabId, PageActions.resolveTarget, [target]);
    if (res && res.found) {
      return res;
    }
    await new Promise(r => setTimeout(r, 100));
  }
  return { found: false, error: `Target not found within ${timeoutMs}ms: "${target}"` };
}

async function postResult(id, result) {
  try {
    await fetch(`${BRIDGE_URL}/result`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id, result })
    });
  } catch (e) {
    log(`Failed to post result for ${id}: ${e.message}`);
  }
}

async function handleCommand(cmd) {
  const action = cmd.action;
  const p = cmd.params || {};
  log(`Executing: ${action} (${JSON.stringify(p)})`);

  try {
    switch (action) {
      case "ping":
        return { success: true, message: "pong", version: "2.0.0" };

      case "reload":
        setTimeout(() => { chrome.runtime.reload(); }, 100);
        return { success: true, message: "Extension reloading..." };

      case "get_active_tab": {
        const tab = await getTargetTab(null);
        if (!tab) return { success: false, error: "No active tab found" };
        return { success: true, tab: { id: tab.id, title: tab.title, url: tab.url, status: tab.status } };
      }

      case "list_tabs":
      case "tabs": {
        const tabs = await chrome.tabs.query({});
        return {
          success: true,
          tabs: tabs.map(t => ({ id: t.id, title: t.title, url: t.url, active: t.active }))
        };
      }

      case "switch_tab": {
        const tabId = Number(p.tabId);
        const tab = await chrome.tabs.update(tabId, { active: true });
        if (tab && tab.windowId) {
          try {
            await chrome.windows.update(tab.windowId, { focused: true });
          } catch (e) {}
        }
        return { success: true, tabId: tab.id };
      }

      case "close_tab": {
        const tab = await getTargetTab(p.tabId);
        if (!tab) return { success: false, error: "No active tab" };
        await chrome.tabs.remove(tab.id);
        return { success: true, closedTabId: tab.id };
      }

      case "nav": {
        let tab = await getTargetTab(p.tabId);
        const url = p.url;
        if (!tab) {
          tab = await chrome.tabs.create({ url });
        } else {
          const pending = waitForTabLoad(tab.id);
          await chrome.tabs.update(tab.id, { url });
          const ok = await pending;
          const t = await chrome.tabs.get(tab.id);
          if (!ok) return { success: false, error: `Navigation to ${url} timed out`, url: t.url };
          return { success: true, title: t.title, url: t.url };
        }
        const loaded = await waitForTabLoad(tab.id);
        const updatedTab = await chrome.tabs.get(tab.id);
        if (!loaded) return { success: false, error: `Navigation to ${url} timed out`, url: updatedTab.url };
        return { success: true, title: updatedTab.title, url: updatedTab.url };
      }

      case "screenshot": {
        const tab = await getTargetTab(p.tabId);
        if (!tab) return { success: false, error: "No tab to capture" };
        if (!tab.active) {
          await chrome.tabs.update(tab.id, { active: true });
          await new Promise(r => setTimeout(r, 100));
        }
        const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: "png" });
        return { success: true, dataUrl, tabId: tab.id, title: tab.title, url: tab.url };
      }

      case "click": {
        const tab = await getTargetTab(p.tabId);
        if (!tab) return { success: false, error: "No active tab" };
        let x = p.x, y = p.y, targetInfo = {};
        if (x === undefined || y === undefined || x === null || y === null) {
          const target = p.target || p.selector || p.text;
          if (!target) return { success: false, error: "click requires target, selector, text, or coordinates" };
          const r = await resolveTargetWithWait(tab.id, target, p.timeout || 5000);
          if (!r || !r.found) {
            return await execInTab(tab.id, PageActions.clickElement, [p.selector, p.text]);
          }
          x = r.x;
          y = r.y;
          targetInfo = r;
        }
        const hasDbg = await ensureDebugger(tab.id);
        if (hasDbg) {
          await nativeClick(tab.id, Number(x), Number(y), p.button || "left", 1);
          return { success: true, x: Number(x), y: Number(y), native: true, ...targetInfo };
        }
        return await execInTab(tab.id, PageActions.clickAt, [Number(x), Number(y)]);
      }

      case "dblclick": {
        const tab = await getTargetTab(p.tabId);
        if (!tab) return { success: false, error: "No active tab" };
        let x = p.x, y = p.y, targetInfo = {};
        if (x === undefined || y === undefined || x === null || y === null) {
          const target = p.target || p.selector || p.text;
          if (!target) return { success: false, error: "dblclick requires target, selector, text, or coordinates" };
          const r = await resolveTargetWithWait(tab.id, target, p.timeout || 5000);
          if (!r || !r.found) {
            return await execInTab(tab.id, PageActions.dblclickElement, [p.selector, p.text]);
          }
          x = r.x;
          y = r.y;
          targetInfo = r;
        }
        const hasDbg = await ensureDebugger(tab.id);
        if (hasDbg) {
          await nativeClick(tab.id, Number(x), Number(y), "left", 1);
          await new Promise(res => setTimeout(res, 50));
          await nativeClick(tab.id, Number(x), Number(y), "left", 2);
          return { success: true, x: Number(x), y: Number(y), native: true, ...targetInfo };
        }
        return await execInTab(tab.id, PageActions.dblclickAt, [Number(x), Number(y)]);
      }

      case "rightclick": {
        const tab = await getTargetTab(p.tabId);
        if (!tab) return { success: false, error: "No active tab" };
        let x = p.x, y = p.y, targetInfo = {};
        if (x === undefined || y === undefined || x === null || y === null) {
          const target = p.target || p.selector || p.text;
          if (!target) return { success: false, error: "rightclick requires target, selector, text, or coordinates" };
          const r = await resolveTargetWithWait(tab.id, target, p.timeout || 5000);
          if (!r || !r.found) return { success: false, error: r ? r.error : `Target not found: ${target}` };
          x = r.x;
          y = r.y;
          targetInfo = r;
        }
        const hasDbg = await ensureDebugger(tab.id);
        if (hasDbg) {
          await nativeClick(tab.id, Number(x), Number(y), "right", 1);
          return { success: true, x: Number(x), y: Number(y), native: true, ...targetInfo };
        }
        return await execInTab(tab.id, (cx, cy) => {
          const el = document.elementFromPoint(cx, cy);
          if (!el) return { success: false, error: "No element at coordinates" };
          const opts = { bubbles: true, cancelable: true, view: window, clientX: cx, clientY: cy, button: 2 };
          el.dispatchEvent(new MouseEvent("contextmenu", opts));
          return { success: true, tag: el.tagName, id: el.id };
        }, [Number(x), Number(y)]);
      }

      case "move":
      case "hover": {
        const tab = await getTargetTab(p.tabId);
        if (!tab) return { success: false, error: "No active tab" };
        let x = p.x, y = p.y, targetInfo = {};
        if (x === undefined || y === undefined || x === null || y === null) {
          const target = p.target || p.selector || p.text;
          if (!target) return { success: false, error: "hover requires target, selector, text, or coordinates" };
          const r = await resolveTargetWithWait(tab.id, target, p.timeout || 5000);
          if (!r || !r.found) return { success: false, error: r ? r.error : `Target not found: ${target}` };
          x = r.x;
          y = r.y;
          targetInfo = r;
        }
        const hasDbg = await ensureDebugger(tab.id);
        if (hasDbg) {
          await nativeMove(tab.id, Number(x), Number(y));
          if (p.duration) {
            await new Promise(res => setTimeout(res, Number(p.duration)));
          }
          return { success: true, x: Number(x), y: Number(y), native: true, ...targetInfo };
        }
        return await execInTab(tab.id, PageActions.moveAt, [Number(x), Number(y)]);
      }

      case "drag": {
        const tab = await getTargetTab(p.tabId);
        if (!tab) return { success: false, error: "No active tab" };
        let fromX = p.fromX, fromY = p.fromY;
        if (fromX === undefined || fromY === undefined || fromX === null || fromY === null) {
          const rFrom = await resolveTargetWithWait(tab.id, p.from || p.source, p.timeout || 5000);
          if (!rFrom || !rFrom.found) return { success: false, error: `Drag source not found: ${p.from || p.source}` };
          fromX = rFrom.x;
          fromY = rFrom.y;
        }
        let toX = p.toX, toY = p.toY;
        if (toX === undefined || toY === undefined || toX === null || toY === null) {
          const rTo = await resolveTargetWithWait(tab.id, p.to || p.target, p.timeout || 5000);
          if (!rTo || !rTo.found) return { success: false, error: `Drag target not found: ${p.to || p.target}` };
          toX = rTo.x;
          toY = rTo.y;
        }
        const hasDbg = await ensureDebugger(tab.id);
        if (hasDbg) {
          await nativeDrag(tab.id, Number(fromX), Number(fromY), Number(toX), Number(toY), Number(p.steps || 12));
          return { success: true, fromX: Number(fromX), fromY: Number(fromY), toX: Number(toX), toY: Number(toY), native: true };
        }
        return { success: false, error: "Native drag requires debugger permission" };
      }

      case "interactive":
      case "elements": {
        const tab = await getTargetTab(p.tabId);
        if (!tab) return { success: false, error: "No active tab" };
        return await execInTab(tab.id, PageActions.getInteractiveElements, []);
      }

      case "wait_for": {
        const tab = await getTargetTab(p.tabId);
        if (!tab) return { success: false, error: "No active tab" };
        const r = await resolveTargetWithWait(tab.id, p.target || p.selector || p.text, p.timeout || 5000);
        if (r && r.found) return { success: true, ...r };
        return { success: false, error: r ? r.error : "Target not found" };
      }

      case "type":
      case "fill": {
        const tab = await getTargetTab(p.tabId);
        if (!tab) return { success: false, error: "No active tab" };
        const target = p.target || p.selector;
        const text = p.text !== undefined ? String(p.text) : "";
        let x = p.x, y = p.y, targetInfo = {};
        if ((x === undefined || y === undefined || x === null || y === null) && target) {
          const r = await resolveTargetWithWait(tab.id, target, p.timeout || 5000);
          if (r && r.found) {
            x = r.x;
            y = r.y;
            targetInfo = r;
          }
        }
        if (x !== undefined && y !== undefined) {
          try {
            const hasDbg = await ensureDebugger(tab.id);
            if (hasDbg) {
              await nativeClick(tab.id, Number(x), Number(y), "left", 1);
              await new Promise(res => setTimeout(res, 50));
              await execInTab(tab.id, (cx, cy, shouldClear) => {
                let el = document.elementFromPoint(cx, cy);
                if (el && el.tagName === "LABEL") {
                  if (el.htmlFor) el = document.getElementById(el.htmlFor) || el;
                  else el = el.querySelector("input, textarea") || el;
                }
                if (!el || (el.tagName !== "INPUT" && el.tagName !== "TEXTAREA" && !el.isContentEditable && !el.tagName.startsWith("FLUENT-"))) {
                  if (document.activeElement && (document.activeElement.tagName === "INPUT" || document.activeElement.tagName === "TEXTAREA" || document.activeElement.tagName.startsWith("FLUENT-"))) {
                    el = document.activeElement;
                  }
                }
                if (el) {
                  const targetInput = el.shadowRoot ? (el.shadowRoot.querySelector("input, textarea") || el) : el;
                  targetInput.focus();
                  if (shouldClear) {
                    if (targetInput.select) targetInput.select();
                    targetInput.value = "";
                    if (el !== targetInput) el.value = "";
                  }
                }
              }, [Number(x), Number(y), p.clear !== false]);

              await cdpSend(tab.id, "Input.insertText", { text });

              await execInTab(tab.id, (cx, cy, tVal) => {
                let el = document.elementFromPoint(cx, cy);
                if (el && el.tagName === "LABEL") {
                  if (el.htmlFor) el = document.getElementById(el.htmlFor) || el;
                  else el = el.querySelector("input, textarea") || el;
                }
                if (!el || (el.tagName !== "INPUT" && el.tagName !== "TEXTAREA" && !el.tagName.startsWith("FLUENT-"))) {
                  if (document.activeElement) el = document.activeElement;
                }
                if (el) {
                  const targetInput = el.shadowRoot ? (el.shadowRoot.querySelector("input, textarea") || el) : el;
                  if (targetInput.value !== tVal) {
                    targetInput.value = tVal;
                    if (el !== targetInput) el.value = tVal;
                  }
                  targetInput.dispatchEvent(new Event("input", { bubbles: true }));
                  targetInput.dispatchEvent(new Event("change", { bubbles: true }));
                  if (el !== targetInput) {
                    el.dispatchEvent(new Event("input", { bubbles: true }));
                    el.dispatchEvent(new Event("change", { bubbles: true }));
                  }
                }
              }, [Number(x), Number(y), text]);
              return { success: true, text, native: true, ...targetInfo };
            }
          } catch (e) {
            log(`Native fill failed (${e.message}), falling back to synthetic DOM`);
          }
        }
        return await execInTab(tab.id, PageActions.typeText, [p.selector, text, p.clear !== false]);
      }

      case "key": {
        const tab = await getTargetTab(p.tabId);
        if (!tab) return { success: false, error: "No active tab" };
        const hasDbg = await ensureDebugger(tab.id);
        if (hasDbg) {
          await nativeKey(tab.id, p.key);
          return { success: true, key: p.key, native: true };
        }
        return await execInTab(tab.id, PageActions.pressKey, [p.key]);
      }

      case "scroll": {
        const tab = await getTargetTab(p.tabId);
        if (!tab) return { success: false, error: "No active tab" };
        const hasDbg = await ensureDebugger(tab.id);
        if (hasDbg) {
          await nativeScroll(tab.id, 500, 300, Number(p.x || 0), Number(p.y || 300));
          return { success: true, scrollX: p.x || 0, scrollY: p.y || 300, native: true };
        }
        return await execInTab(tab.id, PageActions.scrollPage, [Number(p.x || 0), Number(p.y || 0)]);
      }

      case "open_file": {
        const tab = await getTargetTab(p.tabId);
        if (!tab) return { success: false, error: "No active tab" };
        return await execInTab(tab.id, PageActions.openFileInManager, [p.fileId]);
      }

      case "snapshot": {
        const tab = await getTargetTab(p.tabId);
        if (!tab) return { success: false, error: "No active tab" };
        const snap = await execInTab(tab.id, PageActions.getSnapshot, []);
        if (!snap || snap.success === false) return snap || { success: false, error: "Snapshot returned nothing" };
        return { success: true, snapshot: snap };
      }

      case "batch": {
        const steps = p.steps || [];
        const results = [];
        for (const step of steps) {
          if (step.action === "sleep" || step.action === "wait") {
            await new Promise(r => setTimeout(r, Number(step.ms || 100)));
            results.push({ action: "sleep", success: true, ms: step.ms });
          } else {
            const stepCmd = { action: step.action, params: { ...step, tabId: step.tabId || p.tabId } };
            const r = await handleCommand(stepCmd);
            results.push(r);
            if (r && r.success === false && step.stopOnError !== false) {
              return { success: false, error: r.error, stoppedAt: step.action, results };
            }
          }
        }
        return { success: true, count: results.length, results };
      }

      case "eval": {
        const tab = await getTargetTab(p.tabId);
        if (!tab) return { success: false, error: "No active tab" };
        return await execInTab(tab.id, PageActions.evalCode, [p.code], "MAIN");
      }

      case "get_text":
      case "text": {
        const tab = await getTargetTab(p.tabId);
        if (!tab) return { success: false, error: "No active tab" };
        const target = p.target || p.selector;
        const r = await resolveTargetWithWait(tab.id, target, p.timeout || 5000);
        if (!r || !r.found) return r || { success: false, error: `Target not found: "${target}"` };
        const textRes = await execInTab(tab.id, (cx, cy) => {
          let el = document.elementFromPoint(cx, cy);
          if (el && el.tagName === "LABEL") {
            if (el.htmlFor) el = document.getElementById(el.htmlFor) || el;
            else el = el.querySelector("input, textarea") || el;
          }
          const val = el ? (el.value || el.innerText || el.textContent || "") : "";
          return { success: true, text: val.trim() };
        }, [r.x, r.y]);
        return { ...r, ...textRes };
      }

      default:
        return { success: false, error: `Unknown action: ${action}` };
    }
  } catch (err) {
    log(`Error in ${action}: ${err.message}`);
    return { success: false, error: err.message };
  }
}

let bridgeWs = null;
let wsReconnectTimer = null;

function connectWebSocket() {
  if (bridgeWs && (bridgeWs.readyState === WebSocket.CONNECTING || bridgeWs.readyState === WebSocket.OPEN)) {
    return;
  }
  try {
    const ws = new WebSocket("ws://127.0.0.1:18999/ws");
    bridgeWs = ws;

    ws.onopen = () => {
      log("WebSocket real-time channel connected to bridge daemon");
      if (wsReconnectTimer) {
        clearTimeout(wsReconnectTimer);
        wsReconnectTimer = null;
      }
    };

    ws.onmessage = async (event) => {
      try {
        const cmd = JSON.parse(event.data);
        if (cmd && cmd.id) {
          let result;
          try {
            result = await handleCommand(cmd);
          } catch (err) {
            result = { success: false, error: err.message };
          }
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ id: cmd.id, result: result || {} }));
          } else {
            await postResult(cmd.id, result);
          }
        }
      } catch (err) {
        log(`WS handle error: ${err.message}`);
      }
    };

    ws.onclose = () => {
      bridgeWs = null;
      scheduleWsReconnect();
    };

    ws.onerror = () => {
      try { ws.close(); } catch (e) {}
    };
  } catch (e) {
    scheduleWsReconnect();
  }
}

function scheduleWsReconnect() {
  if (!wsReconnectTimer) {
    wsReconnectTimer = setTimeout(() => {
      wsReconnectTimer = null;
      connectWebSocket();
    }, 1200);
  }
}

async function pollLoop() {
  if (isPolling) return;
  isPolling = true;
  log("Background service worker pollLoop started");

  while (isPolling) {
    connectWebSocket();

    // If WebSocket is open and active, commands are handled instantly via WS (<1ms).
    if (bridgeWs && bridgeWs.readyState === WebSocket.OPEN) {
      await new Promise(r => setTimeout(r, 2000));
      continue;
    }

    try {
      const response = await fetch(`${BRIDGE_URL}/poll?client=sw`, {
        cache: "no-store"
      });

      if (response.status === 200) {
        const cmd = await response.json();
        if (cmd && cmd.id) {
          let result;
          try {
            result = await handleCommand(cmd);
          } catch (err) {
            result = { success: false, error: err.message };
          }
          await postResult(cmd.id, result);
        }
      } else if (response.status === 204) {
        // Queue empty, loop immediately
      } else {
        await new Promise(r => setTimeout(r, 1500));
      }
    } catch (err) {
      await new Promise(r => setTimeout(r, 1500));
    }
  }
}

// Keepalive from content script or popup
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  connectWebSocket();
  if (msg.type === "KEEPALIVE") {
    if (!isPolling) pollLoop();
    sendResponse({ ok: true, isPolling: true, wsConnected: !!(bridgeWs && bridgeWs.readyState === WebSocket.OPEN) });
    return false;
  }
  if (msg.action === "wake_up") {
    if (!isPolling) pollLoop();
    sendResponse({ ok: true, lastLog, isPolling: true, wsConnected: !!(bridgeWs && bridgeWs.readyState === WebSocket.OPEN) });
    return false;
  }
  return false;
});

// Watchdog alarm fires every 18 seconds (0.3 minutes)
chrome.alarms.create("sw_watchdog", { periodInMinutes: 0.3 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "sw_watchdog") {
    connectWebSocket();
    if (!isPolling) pollLoop();
  }
});

// Start immediately on worker spin-up
connectWebSocket();
pollLoop();