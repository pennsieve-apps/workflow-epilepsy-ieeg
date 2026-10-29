# Scripts

Demo-data helpers for the epilepsy iEEG workflows. All Apache-2.0. Run from the repository root.

## `fetch-sample-data.sh`

Downloads the demo data from Pennsieve Discover (public, no login) and checks every file's
SHA-256: Discover 530 "Multi-Expert Seizure Annotation" v3 (CC BY 4.0, doi:10.26275/dely-fzwx;
default 6 HUP patients × 4 seizures, ~2.4 GB) into `data/seizures/DATA/`, and Discover 179 "HUP
Interictal iEEG Atlas" v1 (ODC-By, doi:10.26275/lzhy-ox20; `HUP_atlas_final.mat`, 317 MB) into
`data/atlas/`.

```sh
scripts/fetch-sample-data.sh [out-dir] [patients|all]
```

## `seizures-to-labels.py`

Turns the expert annotations of Discover 530 (`data/seizures/DATA/annotations.tsv`) into the
generic `labels.csv` that ieeg-prep reads (`docs/conventions.md`, "Labels on input"), written to
`data/seizures/labels.csv` so that `data/seizures/` (BIDS dataset + labels) is one input.

Per seizure: a recording-level row with `onset_s` = the consensus unequivocal electrographic
onset (`ueo_time_consensus`, median of 3–5 clinicians) in seconds from the clip start,
`stim_induced` (`true`/`false`, from the `stim` column) and `lvfa` (`yes`/`no` → `true`/`false`),
which ieeg-prep copies into `recordings.csv`; and one
row per channel of `ueo_consensus` (`onset=true`) and `sec_consensus` (`spread=true`;
`spread=false` for onset channels not in it). Python 3 standard library only.

```sh
python3 scripts/seizures-to-labels.py [--annotations data/seizures/DATA/annotations.tsv]
    [--bids data/seizures/DATA] [--file-list discover-530-metadata.json] [--out data/seizures/labels.csv]
    [--clip-start exact|floor]
```

What the files show, and what the script therefore does:

- **Clip timing.** A clip `task-<ictal|stim><N>` covers [`approximate_onset` − 120 s,
  `end` + 120 s] in seconds since implant, with N = floor(`approximate_onset`): every local
  clip's `RecordingDuration` equals `end − approximate_onset + 240` s (to 1 ms), and its
  `_events.tsv` puts the approximate onset at exactly 120.0 s. So
  `onset_s = ueo_time_consensus − (approximate_onset − 120)`. The formula
  `ueo_time_consensus − (N − 120)` would put every onset late by the fractional part of
  `approximate_onset` (0.05–0.95 s on the 24 demo clips); `--clip-start floor` gives it anyway.
- **Ids.** `sub-<patient>_ses-postimplant_task-<stim|ictal><N>_run-<run:02d>`. The subject is
  the `patient` column (`CHOP010`); `iEEG_ID` is the iEEG.org file name (`CHOPCCEP_010`,
  `HUP224_phaseII`) and is not used. `run` is the BIDS run (HUP250/HUP257 spontaneous seizures
  are `run-01`, their stimulation seizures `run-00`).
- **Stimulation-induced seizures** are `task-stim<N>`, spontaneous ones `task-ictal<N>`, by the
  `stim` column. Two HUP249 seizures disagree with their file names: 187227 is `Spontaneous` but
  the file is `task-stim187227`, and 439029 is `Stim. Induced` (the high-frequency protocol,
  see `annotations.json`) but the file is `task-ictal439029`. With `--bids` (default) and/or
  `--file-list` (the Discover metadata JSON, all 78 files) the existing file wins and a note is
  printed; without the file list, seizures whose clip is not downloaded get ids from the `stim`
  column. With the Discover file list all 78 annotations map to a file.
- **Empty consensus.** CHOP024's `sec_consensus` is empty (no clinician marked spread
  channels): no spread rows, so spread stays unknown for that clip.
- **Check against `_events.tsv`.** On the 24 demo clips the consensus UEO lies −1.49 to
  +12.18 s from the clinically marked approximate onset (median +1.42 s; |diff| > 5 s for
  HUP224 ictal339135 +7.9 s, HUP238 stim10640 +12.2 s, HUP230 ictal371979 +5.4 s); over all 78
  seizures the median |diff| is 0.80 s. The printout lists each clip with the spread of the
  individual clinicians' times.

## `atlas-to-bids.py`

Converts chosen patients of `data/atlas/HUP_atlas_final.mat` (a MATLAB 5 file, read with
`scipy.io.loadmat`) into BIDS-iEEG under `data/atlas-bids/`: per patient `sub-HUPatlas<NNN>`
(NNN = `patient_no`) one 60 s, 200 Hz recording `task-interictal` (the atlas' `wake_clip`,
already bipolar and filtered 0.5–80 Hz, EDF+ in µV), channels `ch<NNNN>` named after their
column in the atlas, typed SEEG on depth electrodes and ECOG on grids/strips (`depth_elecs`;
SEEG where it is NaN, patient 35), `iEEGReference` bipolar, and
`sub-HUPatlas<NNN>_space-MNI152_electrodes.tsv` with the MNI x/y/z of each bipolar channel,
`soz`, `resected` and `spike_24h` (+ `_coordsystem.json`, `iEEGCoordinateSystem: Other`,
`space-MNI152` in the file name). Needs numpy, scipy and edfio.

Default: 5 patients that have at least one SOZ and one resected channel (57 of the 60 do),
evenly spaced over them in `patient_no` order: 1, 15, 29, 44, 60. `--patients 3,17,42`
overrides, `--n` changes the count.

```sh
python3 scripts/atlas-to-bids.py [--mat data/atlas/HUP_atlas_final.mat] [--out data/atlas-bids]
    [--patients 1,15,29] [--n 5]
```
