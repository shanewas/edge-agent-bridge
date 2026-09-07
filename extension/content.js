// Antigravity Edge Bridge - Content Script Keepalive
// Sole purpose: ping background service worker periodically to keep it awake/restart if idle.
// NO command execution or polling happens here.

(function () {
  window._renderCursor = function (x, y, isClick) {
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
            position: fixed !important;
            pointer-events: none !important;
            z-index: 2147483647 !important;
            top: 0 !important;
            left: 0 !important;
            will-change: transform !important;
            transition: transform 0.08s cubic-bezier(0.2, 0, 0.2, 1) !important;
            filter: drop-shadow(0 2px 4px rgba(0,0,0,0.35)) drop-shadow(0 1px 2px rgba(0,0,0,0.25)) !important;
          }
          .__ag_cursor_svg {
            display: block !important;
            transform-origin: 0 0 !important;
            transition: transform 0.06s ease !important;
          }
          .__ag_cursor_pressed .__ag_cursor_svg {
            transform: scale(0.92) translate(1px, 1px) !important;
          }
          .__ag_cursor_ripple {
            position: fixed !important;
            pointer-events: none !important;
            z-index: 2147483646 !important;
            width: 24px !important;
            height: 24px !important;
            border-radius: 50% !important;
            border: 2px solid rgba(0, 120, 212, 0.85) !important;
            background: rgba(0, 120, 212, 0.15) !important;
            animation: __ag_click_pulse 0.35s cubic-bezier(0.1, 0.8, 0.3, 1) forwards !important;
          }
        `;
        (document.head || document.documentElement).appendChild(style);
      }

      let cur = document.getElementById("__ag_cursor");
      if (!cur) {
        cur = document.createElement("div");
        cur.id = "__ag_cursor";
        cur.className = "__ag_cursor_wrap";
        (document.body || document.documentElement).appendChild(cur);
      }

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
        svgHtml = `<svg class="__ag_cursor_svg" width="22" height="26" viewBox="0 0 22 26" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M6.5 1.5C6.5 0.67 5.83 0 5 0C4.17 0 3.5 0.67 3.5 1.5V11.5L2.3 10.3C1.7 9.7 0.8 9.7 0.2 10.3C-0.3 10.8 -0.3 11.7 0.2 12.3L4.5 16.6C5.9 18 7.8 18.5 9.8 18.5H11.5C14.5 18.5 17 16 17 13V7.5C17 6.67 16.33 6 15.5 6C14.67 6 14 6.67 14 7.5V8.5C14 7.67 13.33 7 12.5 7C11.67 7 11 7.67 11 8.5V7C11 6.17 10.33 5.5 9.5 5.5C8.67 5.5 8 6.17 8 7V1.5C8 0.67 7.33 0 6.5 0" transform="translate(1, 1)" fill="#FFFFFF" stroke="#1A1A1A" stroke-width="1.3" stroke-linejoin="round"/>
        </svg>`;
      } else if (cursorType === "text") {
        svgHtml = `<svg class="__ag_cursor_svg" width="16" height="24" viewBox="0 0 16 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M4 2H12M8 2V22M4 22H12" stroke="#111111" stroke-width="2" stroke-linecap="round"/>
          <path d="M5 3H11M8 3V21M5 21H11" stroke="#FFFFFF" stroke-width="0.8" stroke-linecap="round"/>
        </svg>`;
      } else {
        svgHtml = `<svg class="__ag_cursor_svg" width="22" height="24" viewBox="0 0 22 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M1.5 1V19.8L5.9 15.6L9.1 22.8L12 21.5L8.8 14.3H15.1L1.5 1Z" fill="#FFFFFF" stroke="#181818" stroke-width="1.5" stroke-linejoin="round"/>
        </svg>`;
      }

      cur.innerHTML = svgHtml;
      cur.style.transform = `translate(${x + offsetX}px, ${y + offsetY}px)`;

      if (isClick) {
        cur.classList.add("__ag_cursor_pressed");
        setTimeout(() => cur.classList.remove("__ag_cursor_pressed"), 120);

        const rip = document.createElement("div");
        rip.className = "__ag_cursor_ripple";
        rip.style.left = x + "px";
        rip.style.top = y + "px";
        (document.body || document.documentElement).appendChild(rip);
        setTimeout(() => rip.remove(), 380);
      }
    } catch (e) {}
  };

  if (window.__antigravityKeepaliveInitialized) return;
  window.__antigravityKeepaliveInitialized = true;

  function pingSW() {
    try {
      if (chrome.runtime && chrome.runtime.sendMessage) {
        chrome.runtime.sendMessage({ type: "KEEPALIVE" }).catch(() => {});
      }
    } catch (e) {}
  }

  // Ping immediately
  pingSW();

  // Ping every 10 seconds
  setInterval(pingSW, 10000);
})();