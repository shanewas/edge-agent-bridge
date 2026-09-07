#!/usr/bin/env python3
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import socket
import sys
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from edge import EdgeClient, ensure_bridge_running, send_cmd

class TestEdgeBridgeV120(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        self_running = ensure_bridge_running()
        assert self_running, 'Bridge daemon must be running'
        cls.client = EdgeClient()

    def test_01_rest_api_status(self):
        req = urllib.request.urlopen('http://127.0.0.1:18999/api/status', timeout=5)
        self.assertEqual(req.status, 200)
        data = json.loads(req.read().decode('utf-8'))
        self.assertTrue(data.get('bridge_running'))
        self.assertIn('extension_connected', data)

    def test_02_rest_api_tabs(self):
        req = urllib.request.urlopen('http://127.0.0.1:18999/api/tabs', timeout=10)
        self.assertEqual(req.status, 200)
        data = json.loads(req.read().decode('utf-8'))
        self.assertTrue(data.get('success'))
        self.assertIsInstance(data.get('tabs'), list)

    def test_03_rest_api_eval_success(self):
        body = json.dumps({'code': '100 + 42'}).encode('utf-8')
        req = urllib.request.Request(
            'http://127.0.0.1:18999/api/eval',
            data=body,
            headers={'Content-Type': 'application/json'}
        )
        res = urllib.request.urlopen(req, timeout=10)
        self.assertEqual(res.status, 200)
        data = json.loads(res.read().decode('utf-8'))
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('result'), 142)

    def test_04_security_api_eval_browser_rejection(self):
        body = json.dumps({'code': 'window.location.href'}).encode('utf-8')
        req = urllib.request.Request(
            'http://127.0.0.1:18999/api/eval',
            data=body,
            headers={
                'Content-Type': 'application/json',
                'Origin': 'https://malicious-website.example.com'
            }
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 403)

    def test_05_security_api_eval_sec_fetch_rejection(self):
        body = json.dumps({'code': '1'}).encode('utf-8')
        req = urllib.request.Request(
            'http://127.0.0.1:18999/api/eval',
            data=body,
            headers={
                'Content-Type': 'application/json',
                'Sec-Fetch-Site': 'cross-site'
            }
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 403)

    def test_06_wait_for_eval_success(self):
        self.client.eval('window.__test_flag = false')
        self.client.eval('setTimeout(() => { window.__test_flag = true; }, 300)')
        res = self.client.wait_for_eval('window.__test_flag === true', timeout=4.0)
        self.assertTrue(res.get('success'))
        self.assertEqual(res.get('result'), True)
        self.client.eval('delete window.__test_flag')

    def test_07_wait_for_eval_timeout(self):
        res = self.client.wait_for_eval('window.__never_exists === true', timeout=0.8)
        self.assertFalse(res.get('success'))
        self.assertIn('Condition not met', res.get('error'))

    def test_08_check_radio_element(self):
        setup_code = (
            '(() => { '
            'let c = document.getElementById("test-v120-fixture"); '
            'if (!c) { '
            '  c = document.createElement("div"); '
            '  c.id = "test-v120-fixture"; '
            '  c.innerHTML = \'<input id="rad-v120" type="radio" name="v120" value="alpha">\'; '
            '  document.body.appendChild(c); '
            '} '
            'document.getElementById("rad-v120").checked = false; '
            'return true; '
            '})()'
        )
        self.client.eval(setup_code)
        res = self.client.check_radio(selector='#rad-v120')
        self.assertTrue(res.get('success'), f"check_radio failed: {res}")
        status = self.client.eval('document.getElementById("rad-v120").checked')
        self.assertEqual(status.get('result'), True)
        self.client.eval('document.getElementById("test-v120-fixture").remove()')

    def test_09_log_rotation_configured(self):
        import bridge
        handlers = bridge.logger.handlers
        rotating = any(isinstance(h, RotatingFileHandler) for h in handlers)
        self.assertTrue(rotating, 'Bridge logger must have RotatingFileHandler configured')

if __name__ == '__main__':
    unittest.main()
