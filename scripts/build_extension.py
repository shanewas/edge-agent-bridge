"""Sync manifest.json to the package version and zip the extension."""
import argparse
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from edge_agent_bridge import __version__  # noqa: E402

EXT = ROOT / "edge_agent_bridge" / "extension"
MANIFEST = EXT / "manifest.json"

# One package serves both stores. The name stays vendor-neutral because "Edge" in a Chrome Web
# Store listing is someone else's trademark, and Chrome rejects a description over 132 characters.
NAME = "Agent Browser Bridge"
DESCRIPTION = ("Let an AI agent drive the browser tabs you already have open, using page snapshots "
               "with stable element refs and trusted input.")
MAX_DESCRIPTION = 132
MAX_NAME = 45


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="exit 1 if manifest version differs; write nothing")
    ap.add_argument("--dist", default=str(ROOT / "dist"))
    ap.add_argument("--ext", default=str(EXT), help="extension directory (tests point this at a copy)")
    args = ap.parse_args()

    ext = Path(args.ext)
    manifest_path = ext / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if args.check:
        if manifest["version"] != __version__:
            print(f"manifest.json {manifest['version']} != package {__version__}", file=sys.stderr)
            return 1
        if len(manifest["description"]) > MAX_DESCRIPTION:
            print(f"description is {len(manifest['description'])} chars, over the {MAX_DESCRIPTION} "
                  "character store limit", file=sys.stderr)
            return 1
        print("manifest in sync")
        return 0

    if len(NAME) > MAX_NAME or len(DESCRIPTION) > MAX_DESCRIPTION:
        print("name or description exceeds the store limits", file=sys.stderr)
        return 1

    manifest["version"] = __version__
    manifest["name"] = NAME
    manifest["description"] = DESCRIPTION
    manifest["action"]["default_title"] = NAME
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    dist = Path(args.dist)
    dist.mkdir(parents=True, exist_ok=True)
    out = dist / f"edge-agent-bridge-extension-{__version__}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(ext.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                z.write(f, f.relative_to(ext).as_posix())
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
