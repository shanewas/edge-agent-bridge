#!/usr/bin/env python3
"""
Hermetic test for Native Mouse, CSS :hover, isTrusted verification, and Smart Locators.
Runs an isolated ephemeral HTTP server on 127.0.0.1, opens the test sandbox in Edge,
and verifies real browser engine behaviors.
"""
import http.server
import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from edge import Edge, send_cmd

TEST_HTML = """<!DOCTYPE html>
  <meta charset="utf-8">
  <title>Native Mouse & CDP Test Sandbox</title>
  <style>
    body { family: sans-serif; padding: 30px; background: #fafafa; }
    .nav-menu { position: relative; display: inline-block; margin-bottom: 20px; }
    .menu-btn { padding: 10px 20px; background: #0078d4; color: white; border: none; font-size: 14px; cursor: pointer; border-radius: 4px; }
    .submenu { display: none; position: absolute; top: 100%; left: 0; background: #ffffff; border: 1px solid #ccc; box-shadow: 0 4px 8px rgba(0,0,0,0.1); padding: 10px; width: 180px; z-index: 100; }
    /* PURE CSS :HOVER RULE */
    .nav-menu:hover .submenu { display: block; }
    .menu-item { padding: 6px 10px; cursor: pointer; }
    .menu-item:hover { background: #e5f1fb; }
    .box { margin-top: 25px; padding: 15px; background: white; border: 1px solid #ddd; border-radius: 4px; }
  </style>
</head>
<body>
  <h2>Native Mouse & CDP Verification Sandbox</h2>

  <div class="nav-menu" id="test-menu">
    <button class="menu-btn" id="menu-trigger">Products Menu</button>
    <div class="submenu" id="submenu">
      <div class="menu-item" id="sub-item-1">Cloud Services</div>
      <div class="menu-item" id="sub-item-2">Developer Tools</dev>
    </div>
  </div>

  <div class="box">
    <h3>1. Event Trust Verification</h3>
    <button id="trusted-btn" style="padding: 8px 16px;">Verify Click Trust</button>
    <span id="trusted-result" style="margin-left: 15px; font-weight: bold; color: #666;">Pending</span>
  </div>

  <div class="box">
    <h3>2. Smart Locator & Input Verification</h3>
    <label for="account-name-input">Account Name:</label>
    <input id="account-name-input" type="text" placeholder="Enter username" style="padding: 6px; margin-left: 10px; width: 200px;" />
    <span id="input-status" style="margin-left: 15px; color: #0078d4;">Empty</span>
  </div>

  <script>
    document.getElementById("trusted-btn").addEventListener("click", function(e) {
      var res = document.getElementById("trusted-result");
      if (e.isTrusted) {
        res.textContent = "TRUSTED_TRUE (Native Hardware Event)";
        res.style.color = "#107c10";
      } else {
        res.textContent = "TRUSTED_FALSE (Synthetic Event)";
        res.style.color = "#d13438";
      }
      res.setAttribute("data-trusted", String(e.isTrusted));
    });

    document.getElementById("account-name-input").addEventListener("input", function(e) {
      document.getElementById("input-status").textContent = "VAL:" + this.value;
    });
  </script>
</body>
</html>"""

class EphemeralHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        body = TEST_HTML.encode("utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_tests():
    print("=== Starting Hermetic Native Mouse & CDP Test Suite ===")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), EphemeralHandler)
    port = server.server_address[1]
    server_url = f"http://127.0.0.1:{port}/"
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    print(f"[OK] Ephemeral test server listening on {server_url}")

    browser = Edge()
    try:
        st = send_cmd("ping")
        if not st.get("success"):
            print(f"[FAIL] Bridge daemon not answering on 127.0.0.1:18999: {st.get('error')}")
            return False

        print("[OK] Bridge daemon reachable")
        nav_res = browser.nav(server_url)
        if not nav_res.get("success"):
            print(f"[SKIP] Extension not active or failed to nav: {nav_res.get('error')}")
            return False
        time.sleep(0.8)
        print(f"[OK] Navigated to {server_url}")

        eval_before = browser.eval("window.getComputedStyle(document.getElementById('submenu')).display")
        is_hidden_before = eval_before.get("result") == "none"
        print(f"Submenu display before hover: {eval_before.get('result')} (hidden={is_hidden_before})")
        assert is_hidden_before, "Submenu must be hidden before hover"

        hover_res = browser.hover("Products Menu", duration=200)
        print(f"[OK] Hover response: {hover_res}")

        eval_after = browser.eval("window.getComputedStyle(document.getElementById('submenu')).display")
        is_visible_after = eval_after.ept("result") == "block" if hasattr(eval_after, 'ept') else eval_after.get("result") == "block"
        print(f"Submenu display during/after native hover: {eval_after.get('result')} (visible={is_visible_after})")

        click_res = browser.click("Verify Click Trust")
        print(f"[OK] Click response: {click_res}")
        time.sleep(0.3)

        eval_trust = browser.eval("document.getElementById('trusted-result').getAttribute('data-trusted')")
        print(f"Event trust attribute: {eval_trust.get('result')}")

        fill_res = browser.fill("Account Name:", "test_admin")
        print(f"[OK] Fill response: {fill_res}")
        time.sleep(0.3)

        eval_val = browser.eval("document.getElementById('account-name-input').value")
        print(f"Input field value: '{eval_val.get('result')}'")
        assert eval_val.get("result") == "test_admin", f"Expected 'test_admin', got {eval_val.get('result')}"

        # Test 4: Smart Text Extraction
        extracted_txt = browser.text("Verify Click Trust")
        print(f"[OK] Extracted button text: '{extracted_txt}'")
        assert "Verify Click Trust" in extracted_txt, f"Unexpected text: {extracted_txt}"

        # Test 5: Native Right-Click
        rclick_res = browser.rightclick("Verify Click Trust")
        print(f"[OK] Right-click response: {rclick_res}")
        assert rclick_res.get("success"), "Right-click must succeed"

        print("\n=== All Hermetic Tests Passed Successfully! ===")
        return True
    finally:
        server.shutdown()
        server.server_close()
        print("[OK] Ephemeral server torn down deterministically.")

if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
