#!/usr/bin/env python3
"""Check the committed iig replay cache before a build.

  check_iig_cache.py CACHE

Verifies, without needing the xnu source tree (build.sh stages it later):
  * every manifest entry has both generated files and they hash-match;
  * every header carries the Xcode 15 iig stamp (DriverKit-286).

The per-input source hash check (that each .iig in the actual build tree matches the
cache) runs in the Build step via `xnu-iig-cache.py --verify`, once the tree exists.
"""
import hashlib
import json
import pathlib
import sys


def main(argv):
    if len(argv) != 2:
        sys.exit(__doc__)
    cache = pathlib.Path(argv[1])
    man = json.loads((cache / "manifest.json").read_text())
    bad = []
    for name, e in man.items():
        stem = name[:-4]
        for fn, key in ((stem + ".h", "header_sha256"), (stem + ".iig.cpp", "impl_sha256")):
            p = cache / fn
            if not p.is_file():
                bad.append(f"missing {fn}")
            elif hashlib.sha256(p.read_bytes()).hexdigest() != e[key]:
                bad.append(f"hash mismatch {fn}")
    print(f"cache: {len(man)} inputs, {len(man) * 2 - len(bad)}/{len(man) * 2} files intact")

    stamps = set()
    for name in man:
        p = cache / (name[:-4] + ".h")
        if p.is_file():
            head = p.read_text(errors="replace").split("\n", 1)[0]
            stamps.add(head.split("generated")[0].strip())
    print("stamps:", sorted(stamps))
    if not stamps or not all("DriverKit-286" in s for s in stamps):
        bad.append(f"unexpected iig version: {sorted(stamps)}")

    for b in bad:
        print("ERROR:", b)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
