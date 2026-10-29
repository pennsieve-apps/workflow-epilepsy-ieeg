#!/usr/bin/env python3
# Copyright 2026 University of Pennsylvania. Licensed under the Apache License, Version 2.0.
"""
Turns chosen patients of the HUP Interictal iEEG Atlas (Pennsieve Discover 179,
HUP_atlas_final.mat; ODC-By, doi:10.26275/lzhy-ox20; Bernabei, Sinha et al., Brain 2022,
doi:10.1093/brain/awab480) into a small BIDS-iEEG dataset that ieeg-prep can read.

HUP_atlas_final.mat is a MATLAB 5 file (read with scipy.io.loadmat), one column per bipolar
channel of all 60 patients: wake_clip (12000 samples = 60 s at 200 Hz × 3431 channels, already
filtered 0.5-80 Hz, µV), mni_coords (MNI x/y/z, mm), patient_no, soz_ch, resected_ch,
spike_24h (spikes in 24 h), depth_elecs (1 = depth electrode, 0 = grid/strip).

Per patient P (3-digit patient_no):
  sub-HUPatlasP/ieeg/sub-HUPatlasP_task-interictal_ieeg.edf      60 s, 200 Hz, EDF+, µV
  sub-HUPatlasP/ieeg/sub-HUPatlasP_task-interictal_ieeg.json     iEEGReference bipolar, 0.5-80 Hz
  sub-HUPatlasP/ieeg/sub-HUPatlasP_task-interictal_channels.tsv  ch<NNNN> (atlas column), SEEG/ECOG
  sub-HUPatlasP/ieeg/sub-HUPatlasP_space-MNI152_electrodes.tsv   x, y, z, soz, resected, spike_24h
  sub-HUPatlasP/ieeg/sub-HUPatlasP_space-MNI152_coordsystem.json
plus dataset_description.json, participants.tsv and README.

Channels are named ch<NNNN> after their column in the atlas (1-based, 4 digits): the atlas
holds bipolar channels without contact names. They are typed SEEG on depth electrodes and
ECOG on grids/strips (depth_elecs; SEEG where it is NaN,
which is the case for patient 35); the channel's MNI coordinate is that of the bipolar pair.

Default patients: 5 that have at least one SOZ and one resected channel, evenly spaced over
the eligible patients in patient_no order (deterministic). --patients 3,17,42 overrides.

Usage: scripts/atlas-to-bids.py [--mat data/atlas/HUP_atlas_final.mat] [--out data/atlas-bids]
       [--patients 1,2,3] [--n 5]
Needs numpy, scipy and edfio.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import scipy.io as sio
from edfio import Edf, EdfSignal

SFREQ = 200.0


def write_tsv(path: Path, header: list[str], rows: list[list]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mat", default="data/atlas/HUP_atlas_final.mat")
    ap.add_argument("--out", default="data/atlas-bids")
    ap.add_argument("--patients", help="comma-separated patient_no values (default: chosen as described)")
    ap.add_argument("--n", type=int, default=5, help="number of patients chosen by default")
    a = ap.parse_args()

    m = sio.loadmat(a.mat)
    clip = m["wake_clip"]                          # samples × channels
    pno = np.ravel(m["patient_no"]).astype(int)
    soz = np.ravel(m["soz_ch"]).astype(int)
    res = np.ravel(m["resected_ch"]).astype(int)
    spk = np.ravel(m["spike_24h"]).astype(int)
    depth_raw = np.ravel(m["depth_elecs"]).astype(float)
    depth = np.where(np.isnan(depth_raw), 1, depth_raw).astype(int)  # unknown (patient 35): SEEG
    xyz = np.asarray(m["mni_coords"], dtype=float)
    if clip.shape[1] != len(pno):
        sys.exit(f"wake_clip has {clip.shape[1]} channels but patient_no {len(pno)}")

    eligible = [int(p) for p in sorted(set(pno)) if soz[pno == p].any() and res[pno == p].any()]
    if a.patients:
        chosen = [int(x) for x in a.patients.split(",") if x.strip()]
        unknown = [p for p in chosen if p not in set(pno)]
        if unknown:
            sys.exit(f"unknown patient_no: {unknown}")
    else:
        idx = np.unique(np.round(np.linspace(0, len(eligible) - 1, min(a.n, len(eligible)))).astype(int))
        chosen = [eligible[int(i)] for i in idx]
    print(f"{len(set(pno))} patients, {len(eligible)} with SOZ and resected channels; chosen: {chosen}")

    out = Path(a.out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    with open(out / "dataset_description.json", "w") as fh:
        json.dump({
            "Name": "HUP Interictal iEEG Atlas (subset, BIDS conversion)",
            "BIDSVersion": "1.10.0", "DatasetType": "raw", "License": "ODC-By-1.0",
            "Authors": ["Bernabei JM", "Litt B"],
            "HowToAcknowledge": "Bernabei JM, Sinha N, et al. Normative intracranial EEG maps epileptogenic tissues "
                                "in focal epilepsy. Brain 2022. doi:10.1093/brain/awab480",
            "DatasetDOI": "doi:10.26275/lzhy-ox20",
            "GeneratedBy": [{"Name": "atlas-to-bids.py",
                             "CodeURL": "https://github.com/pennsieve-apps/workflow-epilepsy-ieeg"}],
        }, fh, indent=2)
    (out / "README").write_text(
        "Patients of the HUP Interictal iEEG Atlas (Pennsieve Discover 179, doi:10.26275/lzhy-ox20, ODC-By) "
        "converted to BIDS-iEEG by scripts/atlas-to-bids.py. Each recording is the atlas' 60 s wake clip "
        "(200 Hz, bipolar, filtered 0.5-80 Hz). Channel ch<NNNN> is column NNNN of HUP_atlas_final.mat.\n")
    parts = []
    for p in chosen:
        sel = np.flatnonzero(pno == p)
        sub = f"HUPatlas{p:03d}"
        d = out / f"sub-{sub}" / "ieeg"
        d.mkdir(parents=True)
        stem = f"sub-{sub}_task-interictal"
        names = [f"ch{i + 1:04d}" for i in sel]
        types = ["SEEG" if depth[i] else "ECOG" for i in sel]
        signals = []
        for i, n in zip(sel, names):
            x = np.nan_to_num(clip[:, i].astype(float))
            lim = max(float(np.max(np.abs(x))) * 1.1, 1.0)
            lim = float(np.ceil(lim))
            signals.append(EdfSignal(x, SFREQ, label=n, physical_dimension="uV", physical_range=(-lim, lim),
                                     digital_range=(-32767, 32767), prefiltering="HP:0.5Hz LP:80Hz",
                                     transducer_type="SEEG" if depth[i] else "ECOG"))
        Edf(signals, data_record_duration=1.0).write(d / f"{stem}_ieeg.edf")
        with open(d / f"{stem}_ieeg.json", "w") as fh:
            json.dump({
                "TaskName": "interictal", "TaskDescription": "awake interictal clip (atlas wake_clip)",
                "SamplingFrequency": SFREQ, "PowerLineFrequency": 60, "RecordingDuration": clip.shape[0] / SFREQ,
                "RecordingType": "continuous", "iEEGReference": "bipolar (neighbouring contacts)",
                "SoftwareFilters": {"Bandpass": {"LowCutoff": 0.5, "HighCutoff": 80}},
                "SEEGChannelCount": types.count("SEEG"), "ECOGChannelCount": types.count("ECOG"),
                "InstitutionName": "Hospital of the University of Pennsylvania",
            }, fh, indent=2)
        write_tsv(d / f"{stem}_channels.tsv",
                  ["name", "type", "units", "low_cutoff", "high_cutoff", "sampling_frequency", "status",
                   "status_description"],
                  [[n, t, "µV", 0.5, 80, SFREQ, "good", "n/a"] for n, t in zip(names, types)])
        write_tsv(d / f"sub-{sub}_space-MNI152_electrodes.tsv",
                  ["name", "x", "y", "z", "size", "soz", "resected", "spike_24h"],
                  [[n, f"{xyz[i, 0]:.4f}", f"{xyz[i, 1]:.4f}", f"{xyz[i, 2]:.4f}", "n/a",
                    "true" if soz[i] else "false", "true" if res[i] else "false", int(spk[i])]
                   for i, n in zip(sel, names)])
        with open(d / f"sub-{sub}_space-MNI152_coordsystem.json", "w") as fh:
            json.dump({"iEEGCoordinateSystem": "Other", "iEEGCoordinateUnits": "mm",
                       "iEEGCoordinateSystemDescription": "MNI152 coordinates of each bipolar channel as given in "
                                                          "the HUP atlas (mni_coords)"}, fh, indent=2)
        parts.append([f"sub-{sub}", p, len(sel), int(soz[sel].sum()), int(res[sel].sum())])
        print(f"sub-{sub}: {len(sel)} channels ({types.count('SEEG')} SEEG, {types.count('ECOG')} ECOG), "
              f"{int(soz[sel].sum())} SOZ, {int(res[sel].sum())} resected")
    write_tsv(out / "participants.tsv", ["participant_id", "patient_no", "n_channels", "n_soz", "n_resected"], parts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
