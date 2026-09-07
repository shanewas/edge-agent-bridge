# Privacy Policy for Antigravity Edge Bridge

**Last updated:** September 7, 2026

Antigravity Edge Bridge ("the Extension") is an open-source browser automation bridge designed for developers running local AI coding assistants. This policy explains how information is handled by the Extension.

---

### 1. Zero Data Collection

- The Extension does **not** collect, store, track, or transmit any personally identifiable information (PII), browsing history, web credentials, cookies, or telemetry.
- No analytics or third-party tracking libraries are included in the Extension.

---

### 2. Localhost-Only Communication

- All communication occurs strictly on your local machine (`localhost` / `127.0.0.1:18999`) between the browser extension and your locally executed Python bridge daemon (`edge-bridge` / `bridge.py`).
- No data is ever transmitted to external servers, cloud services, or third parties.
- The local bridge daemon strictly binds to `127.0.0.1` and rejects remote network traffic.

---

### 3. Purpose of Requested Permissions

The Extension requests only permissions essential to its single purpose — developer browser automation:

- **`debugger`**: Used exclusively to dispatch native Chrome DevTools Protocol (CDP) input events (`Input.dispatchMouseEvent`, `Input.dispatchKeyEvent`, `Input.insertText`) to interact with page elements via physical event simulation.
- **`<all_urls>` & `tabs` / `activeTab`**: Used to locate and interact with the specific browser tabs that you explicitly request your local AI agent to automate.
- **`scripting`**: Used to query interactive DOM elements and render an optional visual cursor indicator on the active tab.
- **`storage`**: Used solely to persist local connection status and the latest log message inside your local browser profile.
- **`alarms`**: Used to periodically check the connection status of the local bridge daemon.

---

### 4. Open Source Transparency

The complete source code of Antigravity Edge Bridge is open source under the MIT License and available for independent public audit:

- **Repository**: https://github.com/shanewas/edge-agent-bridge

---

### 5. Contact

If you have any questions regarding this Privacy Policy, please open an issue on GitHub or contact:

- **Author**: Shanewas Ahmed
- **Email**: shanewasahmed@gmail.com
- **GitHub Issues**: https://github.com/shanewas/edge-agent-bridge/issues
