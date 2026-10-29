#!/usr/bin/env bash
# Downloads the demo data for the epilepsy iEEG workflows from Pennsieve Discover (public, no
# login) and checks every file's SHA-256 against the published manifest:
#   - 530 "Multi-Expert Seizure Annotation" v3 (CC BY 4.0, doi:10.26275/dely-fzwx), BIDS-iEEG
#     SEEG seizure clips with multi-expert consensus onset annotations. Default: 6 HUP patients
#     with 4 seizures each (24 clips, ~2.4 GB), plus the dataset-level annotation files.
#   - 179 "HUP Interictal iEEG Atlas" v1 (ODC-By, doi:10.26275/lzhy-ox20), the normative
#     interictal atlas of Bernabei, Sinha et al. (HUP_atlas_final.mat, 317 MB).
#
# Usage: scripts/fetch-sample-data.sh [out-dir] [patients]
#   out-dir   default data
#   patients  default "HUP224 HUP230 HUP235 HUP238 HUP250 HUP257"; "all" for the 29 patients
set -euo pipefail
OUT="${1:-data}"
PATIENTS="${2:-HUP224 HUP230 HUP235 HUP238 HUP250 HUP257}"
mkdir -p "$OUT"
python3 -I - "$OUT" "$PATIENTS" <<'PY'
import base64, hashlib, json, os, sys, urllib.request
out, patients = sys.argv[1], sys.argv[2].split()
API = "https://api.pennsieve.io/discover"

def get(url, body=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return base64.b64encode(h.digest()).decode()

def fetch(dataset, version, prefix, wanted):
    files = get(f"{API}/datasets/{dataset}/versions/{version}/metadata")["files"]
    files = [f for f in files if wanted(f["path"])]
    need = []
    for f in files:
        local = os.path.join(out, prefix, f["path"].split("/", 1)[1])
        f["local"] = local
        if not (os.path.exists(local) and os.path.getsize(local) == f["size"]):
            need.append(f)
    for i in range(0, len(need), 50):
        batch = need[i:i + 50]
        urls = {"/".join(d["path"] + [d["fileName"]]): d["url"] for d in get(f"{API}/datasets/{dataset}/versions/{version}/files/download-manifest",
                                                  {"paths": [f["path"] for f in batch]})["data"]}
        for f in batch:
            os.makedirs(os.path.dirname(f["local"]), exist_ok=True)
            print("fetch", f["path"], f["size"], flush=True)
            urllib.request.urlretrieve(urls[f["path"]], f["local"])
    shas = {f["path"]: f.get("sha256") for f in get(f"{API}/datasets/{dataset}/versions/{version}/metadata")["files"]}
    for f in files:
        want = shas.get(f["path"])
        if want and sha256(f["local"]) != want:
            sys.exit(f"SHA-256 mismatch: {f['path']}")
    print(f"dataset {dataset}: {len(files)} files ok", flush=True)

sel = lambda p: (p.startswith("files/DATA/") and p.count("/") == 2) or any(f"/sub-{x}/" in p for x in patients) or patients == ["all"]
fetch(530, 3, "seizures", lambda p: p.startswith("files/DATA/") and sel(p))
fetch(179, 1, "atlas", lambda p: p.startswith("files/"))
PY
