# Release checklist

One source of truth for the version: `edge_agent_bridge/__init__.py`. `pyproject.toml` reads it;
`scripts/build_extension.py` writes it into `manifest.json`.

1. **Green tree.** `python -m pytest -q -m "not e2e"` and `python -u -m pytest -q -m e2e` pass
   locally on Windows; the `ci` workflow is green on the branch for all three runners.
2. **Bump.** Edit `__version__` in `edge_agent_bridge/__init__.py`. Run
   `python scripts/build_extension.py` (syncs `manifest.json`, writes
   `dist/edge-agent-bridge-extension-<version>.zip`). Run `python scripts/build_extension.py --check`.
3. **Docs.** `CHANGELOG.md` entry; README benchmarks regenerated from
   `python -u -m pytest tests/e2e/test_benchmark.py -q -s` output if numbers are quoted.
4. **Build.** `python -m build --sdist --wheel` → `dist/edge_agent_bridge-<version>.tar.gz` and
   `dist/edge_agent_bridge-<version>-py3-none-any.whl`.
5. **Identity.** `git config user.email` prints `shanewasahmed@gmail.com`.
6. **Commit and tag.** `git commit -m "release: <version>"`, `git tag v<version>`,
   `git push origin main --tags`.
7. **GitHub release.** `gh release create v<version> dist/*<version>* --title "v<version>: <one line>" --notes-file <notes>`
   with all three assets (wheel, sdist, extension zip).
8. **PyPI.** `python -m twine upload dist/*<version>* --disable-progress-bar` (the flag avoids
   the cp932 crash on Windows terminals).
9. **Edge Add-ons store.** Upload the extension zip to the "Edge Agent Bridge" listing; update
   the listing name if it still says the old name. Store review takes days; until it lands, a
   daemon newer than the installed extension answers new actions with `extension_outdated`.
10. **Smoke.** On each OS you can reach: `pip install --upgrade edge-agent-bridge`,
    `edge-bridge daemon restart`, `edge-bridge status`, `edge-bridge --json snapshot` on any page.
