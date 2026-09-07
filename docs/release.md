# Release

One source of truth for the version: `edge_agent_bridge/__init__.py`. `pyproject.toml` reads it;
`scripts/build_extension.py` writes it into `manifest.json`.

## Automated path

Pushing to `main` runs `.github/workflows/release.yml`. The `gate` job builds the extension zip,
checks the manifest is in sync, runs the hermetic suite, and asks PyPI whether the current version
already exists. Everything downstream is skipped when it does, so an ordinary push costs one test
run and nothing else.

When the version is new, the workflow publishes to PyPI, cuts a GitHub release carrying the wheel,
the sdist and the extension zip, then submits the extension to the Edge Add-ons store. That last
step runs only when a file under `edge_agent_bridge/extension/` changed in the push, because a
store review cycle takes days and a Python-only change doesn't need one. The `force_extension`
input on a manual run submits anyway.

A release is therefore: bump `__version__`, write the `CHANGELOG.md` entry, merge to `main`.

### One-time setup

PyPI uses [trusted publishing](https://docs.pypi.org/trusted-publishers/), so no PyPI token is
stored anywhere. On PyPI, add a trusted publisher for the `edge-agent-bridge` project pointing at
this repository, workflow `release.yml`, environment `release`.

The store needs three repository secrets from **Partner Center > Microsoft Edge > Publish API**.
If that page still shows an access token URL and secrets, click **Enable** first: the v1.1
credentials are a Client ID and an API key.

| Secret | Where it comes from |
| --- | --- |
| `EDGE_ADDONS_CLIENT_ID` | Client ID on the Publish API page |
| `EDGE_ADDONS_API_KEY` | API key on the same page; note the expiry and renew before it lapses |
| `EDGE_ADDONS_PRODUCT_ID` | Product ID GUID on the extension's overview page |

Create a `release` environment in the repository settings and attach the secrets to it. Adding a
required reviewer to that environment puts a manual approval in front of both publishers.

## Manual path

Everything the workflow does also runs by hand:

1. **Green tree.** `python -m pytest -q -m "not e2e"` and `python -u -m pytest -q -m e2e` pass
   locally on Windows; `ci` is green on the branch for all three runners.
2. **Bump.** Edit `__version__` in `edge_agent_bridge/__init__.py`, then run
   `python scripts/build_extension.py` (syncs `manifest.json`, writes
   `dist/edge-agent-bridge-extension-<version>.zip`) and `python scripts/build_extension.py --check`.
3. **Docs.** `CHANGELOG.md` entry. Regenerate the README benchmark numbers from
   `python -u -m pytest tests/e2e/test_benchmark.py -q -s` if they moved.
4. **Build.** `python -m build --sdist --wheel`.
5. **Identity.** `git config user.email` prints `shanewasahmed@gmail.com`.
6. **Tag.** `git commit -m "release: <version>"`, `git tag v<version>`, `git push origin main --tags`.
7. **GitHub release.** `gh release create v<version> dist/*<version>* --title "v<version>" --generate-notes`.
8. **PyPI.** `python -m twine upload dist/*<version>* --disable-progress-bar` (the flag avoids the
   cp932 crash on Windows terminals).
9. **Store.** Export `EDGE_ADDONS_CLIENT_ID`, `EDGE_ADDONS_API_KEY` and `EDGE_ADDONS_PRODUCT_ID`,
   then `python scripts/publish_extension.py dist/edge-agent-bridge-extension-<version>.zip`.
   `--upload-only` stages the draft without sending it for review. Store review takes days; until
   the new version lands, a daemon newer than the installed extension answers new actions with
   `extension_outdated`.
10. **Smoke.** On each OS you can reach: `pip install --upgrade edge-agent-bridge`,
    `edge-bridge daemon restart`, `edge-bridge status`, `edge-bridge --json snapshot` on any page.

Listing text, screenshots and the product name still have to be edited in Partner Center. The API
replaces the package and nothing else.
