"""Build the installable extension zip into dist/ (no Blender needed).

Usage: python build.py
Equivalent to: blender --command extension build --source-dir terrain3d_heightmap_exporter --output-dir dist
"""

import pathlib
import re
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent
PKG = ROOT / "terrain3d_heightmap_exporter"


def main():
    manifest = (PKG / "blender_manifest.toml").read_text(encoding="utf-8")
    ext_id = re.search(r'^id\s*=\s*"([^"]+)"', manifest, re.M).group(1)
    version = re.search(r'^version\s*=\s*"([^"]+)"', manifest, re.M).group(1)

    out = ROOT / "dist" / f"{ext_id}-{version}.zip"
    out.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(PKG.rglob("*")):
            rel = path.relative_to(PKG)
            if path.is_dir() or "__pycache__" in rel.parts or rel.parts[0].startswith("."):
                continue
            zf.write(path, rel.as_posix())
    print(f"Built {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
