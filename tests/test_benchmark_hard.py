#!/usr/bin/env python3
"""
Hard Benchmark and Stress Test Suite for edge-agent-bridge.
Hermetically exercises the Edge Extension, Local Bridge Daemon, and Python API.

Benchmark Gates:
  BM-01: WebSocket Latency & RTT Percentiles (200 calls)
  BM-02: Action Batching Throughput vs Sequential Speedup
  BM-03: CDP Native Hardware Click Burst (100 clicks, isTrusted check)
  BM-04: High-Speed Typing Integrity (Unicode, Symbols, Japanese)
  BM-05: Multi-tier CSS :hover Cascade (Pure CSS Blink Compositor test)
  BM-06: CDP Native Mouse Drag & Drop
  BM-07: Massive DOM Scanner Stress (3,000 nodes, elements() timing)
  BM-08: Viewport Screenshot & Base64 Decode Throughput (5 iterations)
  BM-09: Tab Lifecycle & Connection Resilience
"""
import base64
import http.server
import json
import os
import sys
import threading
import time
from pathlib import Path

# Ensure root package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from edge import Edge, EdgeClient, send_cmd, ensure_bridge_running

BENCHMARK_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Edge Bridge Hard Benchmark Arena</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 20px; background: #0f172a; color: #f8fafc; }
    h1, h2, h3 { margin-top: 0; color: #38bdf8; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 20px; }
    .card { background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 15px; }
    button { background: #2563eb; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-weight: bold; }
    button:hover { background: #1d4ed8; }
    button:active { background: #1e40af; }
    input[type="text"] { width: 90%; padding: 8px; border-radius: 4px; border: 1px solid #475569; background: #0f172a; color: white; }
    .metric { font-size: 20px; font-weight: bold; color: #4ade80; margin-left: 10px; }
    
    /* Cascading CSS :hover Menu */
    .menu-root { position: relative; display: inline-block; }
    .menu-sub1 { display: none; position: absolute; top: 100%; left: 0; background: #334155; border: 1px solid #64748b; border-radius: 4px; padding: 5px; width: 160px; z-index: 100; }
    .menu-sub2 { display: none; position: absolute; top: 0; left: 100%; background: #475569; border: 1px solid #64748b; border-radius: 4px; padding: 5px; width: 160px; z-index: 101; }
    .menu-item { padding: 6px 10px; cursor: pointer; border-radius: 2px; }
    .menu-item:hover { background: #0284c7; }
    
    /* PURE CSS RULES: No JS needed for dropdown cascade */
    .menu-root:hover > .menu-sub1 { display: block !important; }
    .menu-item-nested:hover > .menu-sub2 { display: block !important; }

    /* Drag and Drop Arena */
    .drag-container { display: flex; gap: 20px; align-items: center; }
    .drag-box { width: 120px; height: 70px; display: flex; align-items: center; justify-content: center; border-radius: 6px; font-weight: bold; }
    #drag-src { background: #e11d48; cursor: grab; user-select: none; }
    #drag-tgt { background: #059669; border: 2px dashed #34d399; }
    #drag-tgt.drag-over { background: #10b981; border-color: #fff; }
  </style>
</head>
<body>
  <h1>Edge Bridge Hard Benchmark Arena</h1>
  
  <div class="grid">
    <!-- Card 1: Click Burst Arena -->
    <div class="card" id="card-click">
      <h3>1. Native Click Burst & isTrusted</h3>
      <button id="bm-click-btn">Click Me Rapidly</button>
      <div style="margin-top: 10px;">
        Clicks: <span id="click-count" class="metric">0</span> |
        Trusted: <span id="trusted-count" class="metric">0</span>
      </div>
    </div>

    <!-- Card 2: High Speed Typing & Unicode -->
    <div class="card" id="card-type">
      <h3>2. Fast Typing & Character Integrity</h3>
      <label for="bm-type-input">Input Target:</label>
      <input type="text" id="bm-type-input" placeholder="Awaiting native typing..." autocomplete="off" />
      <div style="margin-top: 10px;">
        Length: <span id="type-len" class="metric">0</span> |
        Hash: <span id="type-hash" class="metric">none</span>
      </div>
    </div>

    <!-- Card 3: Multi-tier CSS :hover Dropdown -->
    <div class="card" id="card-hover">
      <h3>3. Multi-tier CSS :hover Cascade</h3>
      <div class="menu-root" id="menu-root">
        <button id="hover-root-btn">Dropdown Level 1</button>
        <div class="menu-sub1" id="menu-sub1">
          <div class="menu-item">Option A</div>
          <div class="menu-item menu-item-nested" id="hover-nested-item">
            Option B (Nested) &gt;
            <div class="menu-sub2" id="menu-sub2">
              <div class="menu-item" id="hover-target-final">Deep Target C</div>
            </div>
          </div>
        </div>
      </div>
      <div style="margin-top: 15px;">
        Deep Item Clicked: <span id="hover-click-result" class="metric">NO</span>
      </div>
    </div>

    <!-- Card 4: Native Drag & Drop -->
    <div class="card" id="card-drag">
      <h3>4. Native Mouse Drag & Drop</h3>
      <div class="drag-container">
        <div id="drag-src" class="drag-box" draggable="true">DRAG ME</div>
        <div id="drag-tgt" class="drag-box" data-dropped="false">DROP ZONE</div>
      </div>
      <div style="margin-top: 10px;">
        Drop Result: <span id="drag-result" class="metric">Pending</span>
      </div>
    </div>
  </div>

  <!-- Card 5: Massive DOM Stress Arena (3,000 elements) -->
  <div class="card" id="card-dom">
    <h3>5. Massive DOM Stress Arena (3,000 Elements)</h3>
    <div id="dom-status">Generating 3,000 elements...</div>
    <div id="dom-container" style="max-height: 150px; overflow-y: auto; display: flex; flex-wrap: wrap; gap: 4px; padding: 8px; border: 1px solid #475569; margin-top: 10px;">
    </div>
  </div>

  <script>
    // 1. Click listeners
    let clickCnt = 0;
    let trustedCnt = 0;
    const clickBtn = document.getElementById("bm-click-btn");
    clickBtn.addEventListener("click", function(e) {
      clickCnt++;
      if (e.isTrusted) trustedCnt++;
      document.getElementById("click-count").textContent = clickCnt;
      document.getElementById("trusted-count").textContent = trustedCnt;
    });

    // 2. Typing listeners
    const typeInp = document.getElementById("bm-type-input");
    typeInp.addEventListener("input", function() {
      document.getElementById("type-len").textContent = this.value.length;
      let hash = 0;
      for (let i = 0; i < this.value.length; i++) {
        hash = ((hash << 5) - hash) + this.value.charCodeAt(i);
        hash |= 0;
      }
      document.getElementById("type-hash").textContent = hash;
    });

    // 3. Hover target click
    document.getElementById("hover-target-final").addEventListener("click", function() {
      document.getElementById("hover-click-result").textContent = "YES_NATIVE_HOVER_SUCCESS";
    });

    // 4. Drag & drop listeners
    const dragSrc = document.getElementById("drag-src");
    const dragTgt = document.getElementById("drag-tgt");
    dragSrc.addEventListener("dragstart", function(e) {
      e.dataTransfer.setData("text/plain", "DRAG_PAYLOAD_OK");
    });
    dragTgt.addEventListener("dragover", function(e) {
      e.preventDefault();
      dragTgt.classList.add("drag-over");
    });
    dragTgt.addEventListener("dragleave", function(e) {
      dragTgt.classList.remove("drag-over");
    });
    dragTgt.addEventListener("drop", function(e) {
      e.preventDefault();
      dragTgt.classList.remove("drag-over");
      dragTgt.setAttribute("data-dropped", "true");
      document.getElementById("drag-result").textContent = "DROPPED_SUCCESSFULLY";
    });

    // 5. Massive DOM generator (3,000 nodes: mix of buttons, links, inputs, and styled spans)
    const domCont = document.getElementById("dom-container");
    const frag = document.createDocumentFragment();
    for (let i = 1; i <= 3000; i++) {
      const mod = i % 4;
      let el;
      if (mod === 0) {
        el = document.createElement("button");
        el.id = "btn-dom-" + i;
        el.textContent = "Btn " + i;
        el.style.fontSize = "10px";
        el.style.padding = "2px 4px";
      } else if (mod === 1) {
        el = document.createElement("input");
        el.id = "inp-dom-" + i;
        el.type = "text";
        el.value = "Val " + i;
        el.style.width = "40px";
        el.style.fontSize = "10px";
      } else if (mod === 2) {
        el = document.createElement("a");
        el.id = "link-dom-" + i;
        el.href = "#" + i;
        el.textContent = "Lnk " + i;
        el.style.fontSize = "10px";
        el.style.color = "#93c5fd";
      } else {
        el = document.createElement("span");
        el.id = "span-dom-" + i;
        el.textContent = "#" + i;
        el.style.fontSize = "10px";
        el.style.color = "#64748b";
      }
      frag.appendChild(el);
    }
    domCont.appendChild(frag);
    document.getElementById("dom-status").textContent = "3,000 elements loaded and ready.";
    window.__domReady = true;
  </script>
</body>
</html>
"""

class EphemeralBenchmarkHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        host = self.headers.get("Host", "")
        if not (host.startswith("127.0.0.1:") or host.startswith("localhost:")):
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"Forbidden: Invalid Host header")
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        body = BENCHMARK_HTML.encode("utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_benchmark():
    print("================================================================")
    print("  HARD BENCHMARK & STRESS SUITE: edge-agent-bridge")
    print("================================================================")
    
    if not ensure_bridge_running():
        print("[ERROR] Failed to start or verify bridge daemon on 127.0.0.1:18999")
        return False

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), EphemeralBenchmarkHandler)
    port = server.server_address[1]
    server_url = f"http://127.0.0.1:{port}/"
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    print(f"[OK] Ephemeral Benchmark Server running on {server_url}")

    browser = Edge()
    results = {}

    try:
        print(f"\n[INIT] Navigating active tab to benchmark arena: {server_url} ...")
        nav_res = browser.nav(server_url)
        if not nav_res.get("success"):
            print(f"[ERROR] Failed to navigate: {nav_res.get('error')}")
            return False
        
        ready = False
        for _ in range(30):
            time.sleep(0.2)
            check = browser.eval("window.__domReady === true")
            if check.get("result") is True:
                ready = True
                break
        if not ready:
            print("[ERROR] Benchmark page did not finish DOM initialization within 6s")
            return False
        print("[OK] Benchmark arena loaded with 3,000 DOM elements and event handlers.")

        # -------------------------------------------------------------
        # BM-01: WebSocket Latency & RTT Percentiles (200 calls)
        # -------------------------------------------------------------
        print("\n----------------------------------------------------------------")
        print("  BM-01: WebSocket Latency & RTT Percentiles (200 calls)")
        print("----------------------------------------------------------------")
        latencies = []
        client = EdgeClient()
        for i in range(200):
            t0 = time.perf_counter()
            r = client.send("ping")
            dt = (time.perf_counter() - t0) * 1000
            if r.get("success"):
                latencies.append(dt)
        
        latencies.sort()
        p50 = latencies[len(latencies) // 2]
        p90 = latencies[int(len(latencies) * 0.90)]
        p95 = latencies[int(len(latencies) * 0.95)]
        p99 = latencies[int(len(latencies) * 0.99)]
        avg = sum(latencies) / len(latencies)
        min_l = min(latencies)
        max_l = max(latencies)
        pass_01 = (p50 < 20.0 and len(latencies) == 200)
        results["BM-01"] = {
            "name": "WebSocket RTT (200 calls)",
            "pass": pass_01,
            "min": f"{min_l:.2f}ms",
            "p50": f"{p50:.2f}ms",
            "p95": f"{p95:.2f}ms",
            "p99": f"{p99:.2f}ms",
            "avg": f"{avg:.2f}ms"
        }
        print(f"  [RESULT] Count={len(latencies)} | Min={min_l:.2f}ms | P50={p50:.2f}ms | P95={p95:.2f}ms | P99={p99:.2f}ms | Avg={avg:.2f}ms")
        print(f"  [{'PASS' if pass_01 else 'FAIL'}] WebSocket latency gate (Target: P50 < 20ms)")

        # -------------------------------------------------------------
        # BM-02: Action Batching Throughput vs Sequential Roundtrips
        # -------------------------------------------------------------
        print("\n----------------------------------------------------------------")
        print("  BM-02: Action Batching vs Sequential Roundtrips (50 actions)")
        print("----------------------------------------------------------------")
        t0 = time.perf_counter()
        for i in range(50):
            browser.eval(f"window.__seq_cnt = {i + 1}")
        seq_time = (time.perf_counter() - t0) * 1000

        batch_steps = [{"action": "eval", "code": f"window.__batch_cnt = {i + 1}"} for i in range(50)]
        t0 = time.perf_counter()
        batch_res = send_cmd("batch", {"steps": batch_steps})
        batch_time = (time.perf_counter() - t0) * 1000
        
        speedup = seq_time / max(batch_time, 0.01)
        pass_02 = (batch_res.get("success") is True and speedup >= 3.0)
        results["BM-02"] = {
            "name": "Batching Speedup (50 ops)",
            "pass": pass_02,
            "sequential": f"{seq_time:.1f}ms",
            "batched": f"{batch_time:.1f}ms",
            "speedup": f"{speedup:.1f}x"
        }
        print(f"  [RESULT] Sequential: {seq_time:.1f}ms ({50 / (seq_time / 1000):.1f} ops/s)")
        print(f"  [RESULT] Batched:    {batch_time:.1f}ms ({50 / (batch_time / 1000):.1f} ops/s)")
        print(f"  [RESULT] Speedup Factor: {speedup:.1f}x")
        print(f"  [{'PASS' if pass_02 else 'FAIL'}] Batching efficiency gate (Target: >= 3.0x speedup)")

        # -------------------------------------------------------------
        # BM-03: CDP Native Hardware Click Burst (100 clicks, isTrusted check)
        # -------------------------------------------------------------
        print("\n----------------------------------------------------------------")
        print("  BM-03: CDP Native Click Burst (100 rapid clicks, isTrusted)")
        print("----------------------------------------------------------------")
        browser.eval("clickCnt = 0; trustedCnt = 0; document.getElementById('click-count').textContent = '0'; document.getElementById('trusted-count').textContent = '0';")
        
        btn_coords = browser.eval("""(() => {
          const r = document.getElementById('bm-click-btn').getBoundingClientRect();
          return { x: Math.round(r.left + r.width/2), y: Math.round(r.top + r.height/2) };
        })()""").get("result", {})
        bx, by = btn_coords.get("x", 100), btn_coords.get("y", 100)

        t0 = time.perf_counter()
        for _ in range(100):
            send_cmd("click", {"x": bx, "y": by})
        burst_time = (time.perf_counter() - t0) * 1000
        time.sleep(0.5)

        click_res = browser.eval("""({
          clicks: parseInt(document.getElementById('click-count').textContent) || 0,
          trusted: parseInt(document.getElementById('trusted-count').textContent) || 0
        })""").get("result", {})
        
        total_clicks = click_res.get("clicks", 0)
        trusted_clicks = click_res.get("trusted", 0)
        trust_pct = (trusted_clicks / max(total_clicks, 1)) * 100
        pass_03 = (total_clicks == 100 and trusted_clicks == 100)
        results["BM-03"] = {
            "name": "Click Burst (100 clicks)",
            "pass": pass_03,
            "total_clicks": total_clicks,
            "trusted_clicks": trusted_clicks,
            "trust_pct": f"{trust_pct:.1f}%",
            "time": f"{burst_time:.1f}ms",
            "rate": f"{100 / (burst_time / 1000):.1f} clicks/sec"
        }
        print(f"  [RESULT] Registered: {total_clicks}/100 clicks | Trusted: {trusted_clicks}/100 ({trust_pct:.1f}%)")
        print(f"  [RESULT] Elapsed: {burst_time:.1f}ms ({100 / (burst_time / 1000):.1f} clicks/sec)")
        print(f"  [{'PASS' if pass_03 else 'FAIL'}] Click burst & trust gate (Target: 100% isTrusted, 0 dropped)")

        # -------------------------------------------------------------
        # BM-04: High-Speed Typing Integrity (Unicode, Symbols, Japanese)
        # -------------------------------------------------------------
        print("\n----------------------------------------------------------------")
        print("  BM-04: Fast Typing Integrity (Unicode, Symbols, Japanese)")
        print("----------------------------------------------------------------")
        test_payload = "EdgeAgent 日本語入力テスト 12345 !@#$%^&*()_+-=[]{}|;':,./<>? 🚀"
        t0 = time.perf_counter()
        fill_res = browser.fill("#bm-type-input", test_payload, clear=True)
        type_time = (time.perf_counter() - t0) * 1000
        time.sleep(0.3)

        typed_val = browser.eval("document.getElementById('bm-type-input').value").get("result", "")
        match_ok = (typed_val == test_payload)
        pass_04 = (fill_res.get("success") is True and match_ok)
        results["BM-04"] = {
            "name": "Typing Integrity (Unicode/JP)",
            "pass": pass_04,
            "expected_len": len(test_payload),
            "actual_len": len(typed_val),
            "exact_match": match_ok,
            "time": f"{type_time:.1f}ms"
        }
        print(f"  [RESULT] Target length: {len(test_payload)} chars | Actual: {len(typed_val)} chars")
        print(f"  [RESULT] Exact match: {match_ok} | Time: {type_time:.1f}ms")
        if not match_ok:
            print(f"    Expected: {test_payload!r}")
            print(f"    Received: {typed_val!r}")
        print(f"  [{'PASS' if pass_04 else 'FAIL'}] Typing integrity gate (Target: 100% exact byte match)")

        # -------------------------------------------------------------
        # BM-05: Multi-tier CSS :hover Cascade (Pure CSS Dropdown)
        # -------------------------------------------------------------
        print("\n----------------------------------------------------------------")
        print("  BM-05: Multi-tier CSS :hover Cascade (Pure CSS Blink Compositor)")
        print("----------------------------------------------------------------")
        pre_hover = browser.eval("""({
          sub1: window.getComputedStyle(document.getElementById('menu-sub1')).display,
          sub2: window.getComputedStyle(document.getElementById('menu-sub2')).display
        })""").get("result", {})
        
        browser.hover("#hover-root-btn", duration=250)
        state1 = browser.eval("window.getComputedStyle(document.getElementById('menu-sub1')).display").get("result")

        browser.hover("#hover-nested-item", duration=250)
        state2 = browser.eval("window.getComputedStyle(document.getElementById('menu-sub2')).display").get("result")

        browser.click("#hover-target-final")
        time.sleep(0.3)
        hover_click = browser.eval("document.getElementById('hover-click-result').textContent").get("result")

        pass_05 = (pre_hover.get("sub1") == "none" and state1 == "block" and state2 == "block" and "YES" in str(hover_click))
        results["BM-05"] = {
            "name": "CSS :hover Cascade",
            "pass": pass_05,
            "sub1_initial": pre_hover.get("sub1"),
            "sub1_hovered": state1,
            "sub2_hovered": state2,
            "target_clicked": hover_click
        }
        print(f"  [RESULT] Sub1 Initial: {pre_hover.get('sub1')} -> Hovered: {state1}")
        print(f"  [RESULT] Sub2 Hovered: {state2} -> Final Target Clicked: {hover_click}")
        print(f"  [{'PASS' if pass_05 else 'FAIL'}] CSS :hover cascade gate (Target: pure CSS Blink hover)")

        # -------------------------------------------------------------
        # BM-06: CDP Native Mouse Drag & Drop
        # -------------------------------------------------------------
        print("\n----------------------------------------------------------------")
        print("  BM-06: CDP Native Mouse Drag & Drop")
        print("----------------------------------------------------------------")
        src_coords = browser.eval("""(() => {
          const r = document.getElementById('drag-src').getBoundingClientRect();
          return { x: Math.round(r.left + r.width/2), y: Math.round(r.top + r.height/2) };
        })()""").get("result", {})
        tgt_coords = browser.eval("""(() => {
          const r = document.getElementById('drag-tgt').getBoundingClientRect();
          return { x: Math.round(r.left + r.width/2), y: Math.round(r.top + r.height/2) };
        })()""").get("result", {})

        t0 = time.perf_counter()
        drag_res = browser.drag(
            (src_coords.get("x", 100), src_coords.get("y", 100)),
            (tgt_coords.get("x", 300), tgt_coords.get("y", 100)),
            steps=15
        )
        drag_time = (time.perf_counter() - t0) * 1000
        time.sleep(0.3)

        dropped = browser.eval("document.getElementById('drag-tgt').getAttribute('data-dropped')").get("result")
        pass_06 = (drag_res.get("success") is True and dropped == "true")
        results["BM-06"] = {
            "name": "CDP Drag & Drop",
            "pass": pass_06,
            "dropped_attr": dropped,
            "time": f"{drag_time:.1f}ms"
        }
        print(f"  [RESULT] Drag from ({src_coords.get('x')}, {src_coords.get('y')}) to ({tgt_coords.get('x')}, {tgt_coords.get('y')})")
        print(f"  [RESULT] Drop result: {dropped} | Time: {drag_time:.1f}ms")
        print(f"  [{'PASS' if pass_06 else 'FAIL'}] Drag & Drop gate (Target: CDP mouse simulation)")

        # -------------------------------------------------------------
        # BM-07: Massive DOM Scanner Stress (3,000 Elements)
        # -------------------------------------------------------------
        print("\n----------------------------------------------------------------")
        print("  BM-07: Massive DOM Scanner Stress (3,000 Nodes)")
        print("----------------------------------------------------------------")
        t0 = time.perf_counter()
        interactive_els = browser.elements()
        scan_time = (time.perf_counter() - t0) * 1000
        
        el_count = len(interactive_els)
        pass_07 = (el_count >= 1500 and scan_time < 350.0)
        results["BM-07"] = {
            "name": "DOM Scanner (3k nodes)",
            "pass": pass_07,
            "elements_found": el_count,
            "scan_time": f"{scan_time:.1f}ms",
            "target": "< 350ms"
        }
        print(f"  [RESULT] Scanned {el_count} interactive elements across 3,000 DOM nodes in {scan_time:.1f}ms")
        print(f"  [{'PASS' if pass_07 else 'FAIL'}] Massive DOM scan gate (Target: >1,500 interactive elements, < 350ms)")

        # -------------------------------------------------------------
        # BM-08: Viewport Screenshot & Base64 Decode Throughput (5 iterations)
        # -------------------------------------------------------------
        print("\n----------------------------------------------------------------")
        print("  BM-08: Viewport Screenshot & Base64 Decode Throughput (5 runs)")
        print("----------------------------------------------------------------")
        shot_times = []
        shot_sizes = []
        for i in range(5):
            t0 = time.perf_counter()
            res = send_cmd("screenshot", {})
            dt = (time.perf_counter() - t0) * 1000
            if res.get("success"):
                durl = res.get("dataUrl", "")
                raw_bytes = base64.b64decode(durl.split(",", 1)[1]) if "," in durl else b""
                shot_times.append(dt)
                shot_sizes.append(len(raw_bytes))
            time.sleep(0.55)  # Respect Chrome MAX_CAPTURE_VISIBLE_TAB_CALLS_PER_SECOND quota
        
        avg_shot_time = sum(shot_times) / len(shot_times) if shot_times else 999.0
        avg_shot_size = sum(shot_sizes) / len(shot_sizes) if shot_sizes else 0
        pass_08 = (len(shot_times) == 5 and avg_shot_time < 300.0 and avg_shot_size > 5000)
        results["BM-08"] = {
            "name": "Screenshot Throughput (5 runs)",
            "pass": pass_08,
            "avg_time": f"{avg_shot_time:.1f}ms",
            "avg_size_kb": f"{avg_shot_size / 1024:.1f} KB",
            "iterations": len(shot_times)
        }
        print(f"  [RESULT] 5 captures completed: Avg Time={avg_shot_time:.1f}ms | Avg PNG Size={avg_shot_size/1024:.1f} KB")
        print(f"  [{'PASS' if pass_08 else 'FAIL'}] Screenshot throughput gate (Target: < 300ms per capture)")

        # -------------------------------------------------------------
        # BM-09: Tab Lifecycle & Connection Resilience
        # -------------------------------------------------------------
        print("\n----------------------------------------------------------------")
        print("  BM-09: Tab Query & Active Tab Lifecycle")
        print("----------------------------------------------------------------")
        t0 = time.perf_counter()
        tabs_res = send_cmd("tabs", {})
        tab_time = (time.perf_counter() - t0) * 1000
        tabs_list = tabs_res.get("tabs", [])
        active_tabs = [t for t in tabs_list if t.get("active")]
        
        pass_09 = (tabs_res.get("success") is True and len(active_tabs) >= 1)
        results["BM-09"] = {
            "name": "Tab Query & Lifecycle",
            "pass": pass_09,
            "total_tabs": len(tabs_list),
            "active_tab_found": len(active_tabs) >= 1,
            "query_time": f"{tab_time:.1f}ms"
        }
        print(f"  [RESULT] Discovered {len(tabs_list)} open Edge tabs in {tab_time:.1f}ms (Active Tab ID: {active_tabs[0].get('id') if active_tabs else 'none'})")
        print(f"  [{'PASS' if pass_09 else 'FAIL'}] Tab query & lifecycle gate")

        # -------------------------------------------------------------
        # Final Summary
        # -------------------------------------------------------------
        print("\n================================================================")
        print("  FINAL BENCHMARK SCORECARD")
        print("================================================================")
        all_passed = True
        for k, v in results.items():
            status = "PASS [OK]" if v["pass"] else "FAIL [X]"
            if not v["pass"]:
                all_passed = False
            details = " | ".join(f"{dk}={dv}" for dk, dv in v.items() if dk not in ("name", "pass"))
            print(f"  {k} ({v['name']}): {status} => {details}")

        print("================================================================")
        if all_passed:
            print("  >>> ALL 9 BENCHMARK GATES PASSED WITH FLYING COLORS! <<<")
        else:
            print("  >>> WARNING: ONE OR MORE BENCHMARK GATES FAILED <<<")
        print("================================================================\n")
        return all_passed

    finally:
        print("[CLEANUP] Tearing down ephemeral benchmark server deterministically...")
        server.shutdown()
        server.server_close()
        print("[CLEANUP] Server closed.")


if __name__ == "__main__":
    success = run_benchmark()
    sys.exit(0 if success else 1)
