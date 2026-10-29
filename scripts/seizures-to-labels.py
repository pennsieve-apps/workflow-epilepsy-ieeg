#!/usr/bin/env python3
# Copyright 2026 University of Pennsylvania. Licensed under the Apache License, Version 2.0.
"""
Turns the expert annotations of Pennsieve Discover 530 "Multi-Expert Seizure Annotation"
(annotations.tsv; CC BY 4.0, doi:10.26275/dely-fzwx) into the generic labels.csv that
ieeg-prep reads (docs/conventions.md, "Labels on input").

Per seizure:
  - a recording-level row: onset_s = the consensus unequivocal electrographic onset
    (ueo_time_consensus, the median of the 3-5 clinicians) in seconds from the clip start;
  - one row per channel in ueo_consensus (onset=true) or sec_consensus (spread=true).

Clip timing. A clip task-<ictal|stim><N> covers [approximate_onset - 120 s, end + 120 s] in
seconds since implant, with N = floor(approximate_onset): every clip's RecordingDuration equals
end - approximate_onset + 240 s and its _events.tsv puts the approximate onset at exactly
120 s. So onset_s = ueo_time_consensus - (approximate_onset - 120), not
ueo_time_consensus - (N - 120), which would be late by the fractional part of
approximate_onset (0.05-0.95 s). --clip-start floor gives the N - 120 variant.

Recording ids: sub-<patient>_ses-postimplant_task-<stim|ictal><N>_run-<run, 2 digits>. The
subject is the `patient` column (CHOP010), not iEEG_ID (the iEEG.org file name,
CHOPCCEP_010 / HUP224_phaseII). Stimulation-induced seizures are task-stim<N>, spontaneous
ones task-ictal<N>; where the dataset's file names disagree with the `stim` column (HUP249),
the existing file wins when --bids or --file-list says which exists.

Usage:
  scripts/seizures-to-labels.py [--annotations data/seizures/DATA/annotations.tsv]
      [--bids data/seizures/DATA] [--file-list metadata.json] [--out data/seizures/labels.csv]
      [--clip-start exact|floor]
"""
from __future__ import annotations

import argparse
import ast
import csv
import json
import math
import statistics
import sys
from pathlib import Path


def parse_list(s: str):
    s = (s or "").strip()
    if not s or s.lower() in ("n/a", "nan"):
        return []
    try:
        v = ast.literal_eval(s)
    except (ValueError, SyntaxError):
        return []
    return v if isinstance(v, list) else [v]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--annotations", default="data/seizures/DATA/annotations.tsv")
    ap.add_argument("--bids", default="data/seizures/DATA", help="BIDS root, to match ids to files and check timing")
    ap.add_argument("--file-list", help="Discover metadata JSON (files[].path) listing every file of the dataset")
    ap.add_argument("--out", default="data/seizures/labels.csv")
    ap.add_argument("--clip-start", choices=("exact", "floor"), default="exact",
                    help="exact: clip starts at approximate_onset - 120 s (what the files show); floor: N - 120 s")
    a = ap.parse_args()

    rows = list(csv.DictReader(open(a.annotations, encoding="utf-8-sig"), delimiter="\t"))
    bids = Path(a.bids) if a.bids and Path(a.bids).is_dir() else None
    known: set[str] = set()
    if a.file_list:
        for f in json.load(open(a.file_list))["files"]:
            name = f["path"].split("/")[-1]
            if name.endswith("_ieeg.edf"):
                known.add(name[: -len("_ieeg.edf")])
    if bids:
        known |= {p.name[: -len("_ieeg.edf")] for p in bids.glob("sub-*/ses-*/ieeg/*_ieeg.edf")}

    out: list[dict] = []
    report: list[str] = []
    problems: list[str] = []
    not_local: list[str] = []
    diffs: list[float] = []
    for r in rows:
        patient = r["patient"].strip()
        try:
            approx = float(r["approximate_onset"])
            ueo = float(r["ueo_time_consensus"])
        except ValueError:
            problems.append(f"{patient} {r.get('approximate_onset')}: no approximate_onset/ueo_time_consensus; skipped")
            continue
        n = math.floor(approx)
        run = int(float(r.get("run") or 0))
        stim = r["stim"].strip().lower().startswith("stim")
        tried = []
        stem = None
        for kind in (("stim", "ictal") if stim else ("ictal", "stim")):
            for rr in dict.fromkeys((run, 0, 1)):
                s = f"sub-{patient}_ses-postimplant_task-{kind}{n}_run-{rr:02d}"
                tried.append(s)
                if not known or s in known:
                    stem = s
                    break
            if stem:
                break
        if stem is None:  # not in the local copy: name it from the stim column
            stem = tried[0]
            not_local.append(stem)
        if known and (("_task-stim" in stem) != stim):
            problems.append(f"{stem}: the annotation says {'stimulation-induced' if stim else 'spontaneous'} "
                            f"({r['stim']}) but the file is named task-{'stim' if '_task-stim' in stem else 'ictal'}; "
                            "matched by onset time")
        start = (approx - 120.0) if a.clip_start == "exact" else (n - 120.0)
        onset_s = ueo - start
        clin = [float(x) for x in parse_list(r.get("ueo_time", "")) if x not in (None, "")]
        spread = (max(clin) - min(clin)) if clin else float("nan")
        diffs.append(onset_s - 120.0)
        # check against the files when they are here
        chk = ""
        if bids:
            ev = next(bids.glob(f"sub-{patient}/ses-*/ieeg/{stem}_events.tsv"), None)
            js = next(bids.glob(f"sub-{patient}/ses-*/ieeg/{stem}_ieeg.json"), None)
            if ev and js:
                e = list(csv.DictReader(open(ev, encoding="utf-8-sig"), delimiter="\t"))
                ev_on = float(e[0]["onset"]) if e else float("nan")
                dur = float(json.load(open(js))["RecordingDuration"])
                expect = float(r["end"]) - approx + 240.0
                chk = f" events.tsv onset {ev_on:g} s; duration {dur:.3f} s vs end-approx+240 {expect:.3f} s"
        report.append(f"{stem}: onset_s {onset_s:8.3f} (UEO {onset_s - 120:+7.3f} s from the approximate onset; "
                      f"clinicians span {spread:.2f} s){chk}")
        out.append({"subject": patient, "recording_id": stem, "channel": "", "soz": "", "resected": "",
                    "onset": "", "spread": "", "onset_s": f"{onset_s:.4f}"})
        onset_ch = [str(c) for c in parse_list(r.get("ueo_consensus", ""))]
        sec_ch = [str(c) for c in parse_list(r.get("sec_consensus", ""))]
        for ch in dict.fromkeys(onset_ch + sec_ch):
            out.append({"subject": patient, "recording_id": stem, "channel": ch, "soz": "", "resected": "",
                        "onset": "true" if ch in onset_ch else "",
                        "spread": "true" if ch in sec_ch else ("" if not sec_ch else "false"),
                        "onset_s": ""})
        if not onset_ch:
            problems.append(f"{stem}: empty ueo_consensus; onset channels unknown")
        if not sec_ch:
            problems.append(f"{stem}: empty sec_consensus; spread unknown")

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["subject", "recording_id", "channel", "soz", "resected", "onset", "spread",
                                           "onset_s"], lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    for line in report:
        print(line)
    for p in problems:
        print("NOTE:", p)
    if not_local:
        print(f"NOTE: {len(not_local)} seizure(s) have no file in --bids/--file-list; ids built from the stim "
              "column (pass --file-list with the Discover metadata to check them all)")
    n_rec = sum(1 for o in out if not o["channel"])
    if diffs:
        ad = [abs(d) for d in diffs]
        print(f"{n_rec} seizure(s) of {len(rows)} annotation row(s) -> {a.out} ({len(out)} rows). "
              f"UEO minus approximate onset: median {statistics.median(diffs):+.2f} s, "
              f"median |diff| {statistics.median(ad):.2f} s, max |diff| {max(ad):.2f} s")
    return 0 if out else 1


if __name__ == "__main__":
    sys.exit(main())
