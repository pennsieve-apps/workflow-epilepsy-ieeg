# Conventions shared by the epilepsy iEEG apps

Every app in the two workflows (Interictal Biomarker Mapping, Seizure Onset Localisation)
follows this contract, so any step's output can be linked to any other step's input without
glue, and every step also runs on data that never came from the demo datasets.

## Runtime contract (Pennsieve processors)

- Read from `$INPUT_DIR`, write to `$OUTPUT_DIR`. Parameters arrive as environment variables
  named as in `app.yml`. Never write elsewhere except `/tmp`. No network at run time.
- One output port: it is the whole `$OUTPUT_DIR`. Two or more outputs: each is written to
  `$OUTPUT_DIR/<name>/`.
- Inputs with several ports use `placement: subfolder`: each arrives at `$INPUT_DIR/<name>/`.
  Apps must also work when no links are used (everything merged side by side at the root of
  `$INPUT_DIR`), by finding files by their names anywhere under `$INPUT_DIR` (follow symlinks;
  INPUT_DIR entries are symlinks).
- Several links may feed one input port (fan-in); their entries land side by side and two
  entries with the same name fail the run (compute node data transfer, `handleMerge`). So an
  app whose output can be one of several links into one port writes everything, tables and
  `provenance.json`, under a folder named after itself (or after its `LABEL` parameter when it
  has one and it is set): seizure-dynasd → `OUTPUT_DIR/dynasd/`, seizure-ei → `OUTPUT_DIR/ei/`,
  seizure-fragility → `OUTPUT_DIR/fragility/`, all three linked into seizure-consensus's (and
  ieeg-report's) `methods` port. An app that may run more than once in a workflow writes under
  a folder named by a `LABEL` parameter. Readers therefore find tables by file name anywhere
  under a port, never at a fixed path.
- Port names: lowercase letters, digits and `-` (no underscores).
- Each output folder (the method folder above, when there is one) gets a `provenance.json`: app name + version (from `VERSION`), tool
  versions, parameters, inputs seen (relative paths), timings, per-recording status.
- A recording that fails is logged and skipped; the step fails only when every recording
  failed or no input was found. Non-zero exit code on failure.
- Logs go to stdout, one line per recording with channel counts and timings.
- Memory: process one recording at a time; never load every recording at once. A 1 h,
  128-channel, 1024 Hz recording is ~1.9 GB as float32: chunk per channel or per window when
  a method allows it.
- Reproducible: every random step takes `SEED` (default `42`).
- Parallel workers (`THREADS`, `0` = automatic): count the CPUs the container is given, not
  the host's. Resolve `0` from the cgroup CPU quota (v2 `cpu.max`, v1 `cpu.cfs_quota_us` /
  `cpu.cfs_period_us`), else the CPU affinity, else the CPU count, and cap it so that an
  estimated per-worker footprint fits the cgroup memory limit (`memory.max`). Log the number and
  why, and keep both in `provenance.json`. (`os.cpu_count()` in a 4-vCPU container on a 15-CPU
  host is 15; 15 workers under 3 GB were OOM-killed without a word.) Python apps share
  `processor/resources.py`, the R app `R/resources.R`.

## The data between steps: a BIDS-iEEG derivative

`ieeg-prep` turns whatever it is given into one BIDS-iEEG derivative dataset, and every later
step reads that (and also accepts a plain BIDS-iEEG dataset, so steps can be run on their
own). Layout of the `ieeg` output port of `ieeg-prep`:

```
dataset_description.json            (BIDS derivative, GeneratedBy ieeg-prep)
recordings.csv                      (index, below)
sub-<label>/[ses-<label>/]ieeg/
  <stem>_desc-preproc_ieeg.edf      signals after montage + notch, EDF+ (16-bit, per-channel
                                    physical range set from the data; see "Precision")
  <stem>_desc-preproc_ieeg.json     BIDS sidecar (SamplingFrequency, iEEGReference, PowerLineFrequency, ...)
  <stem>_desc-preproc_channels.tsv  one row per channel kept (columns below)
  <stem>_desc-preproc_events.tsv    events (columns below)
sub-<label>/[ses-<label>/]ieeg/<subject-stem>_desc-preproc_electrodes.tsv   (when coordinates or labels exist;
                                    space in its `space` column: MNI152 for the atlas, native for Discover 530)
```

`<stem>` is the BIDS entity chain of the source recording (`sub-HUP257_ses-postimplant_task-ictal387681_run-01`).
A **recording id** is that stem; it is the key in every table below.

### `recordings.csv`

One row per recording: `recording_id, subject, session, task, run, path` (relative to the port
root), `sfreq, n_channels, n_good, duration_s, montage` (`bipolar` | `car` | `as-recorded`),
`kind` (`ictal` | `interictal` | `unknown`), `onset_s` (expert/clinical seizure onset in
seconds from the recording start, empty if unknown), `baseline_start_s, baseline_end_s`
(interval treated as pre-ictal baseline; empty if none), `source_format` (`bids-edf`, `edf`,
`brainvision`, `mef3`, `fif`, ...). Then any extra recording-level columns of `labels.csv` (see
"Labels on input"), e.g. `stim_induced`, `lvfa` (`true` | `false`; empty = unknown).

### `_channels.tsv`

BIDS columns `name, type` (`SEEG` | `ECOG` | `EEG` | ...), `units, low_cutoff, high_cutoff,
sampling_frequency, status` (`good` | `bad`), `status_description` (why bad), plus:

- `contacts`: the source contacts a channel is made from (`LA01|LA02` for a bipolar pair, the
  name itself otherwise).
- `soz`, `resected`, `onset`, `spread`: labels when known (`true` | `false`; empty = unknown).
  A bipolar channel carries a label when **either** contact has it. `onset`/`spread` are
  per seizure (they belong to a recording); `soz`/`resected` are per subject.
- `x, y, z` and `space` (e.g. `MNI152NLin2009aSym`, `MNI152`) when coordinates are known; a
  bipolar channel sits at the midpoint of its contacts. `roi` when an atlas region is known.

### `_events.tsv`

BIDS `onset, duration, trial_type` plus `source`. `trial_type` values used here:
`seizure` (the annotated seizure, onset = expert/clinical onset), `baseline` (pre-ictal
baseline interval), `artifact`, and detections written back by later steps are **not** put
here (they go to the step's own tables).

### Labels on input

`ieeg-prep` reads labels from BIDS sidecars (extra `_channels.tsv` / `_electrodes.tsv`
columns named as above, `_events.tsv` `seizure` rows) and from an optional `labels.csv`
anywhere in its input with columns `subject, recording_id` (empty = every recording of the
subject), `channel` (a contact name), and any of `soz, resected, onset, spread`, plus
recording-level rows (`channel` empty) carrying `onset_s`. Any other column filled on a
recording-level row is carried into `recordings.csv` as a column of the same name (lower-cased,
value as written; empty for recordings without one; a name ieeg-prep computes itself, such as
`kind`, is ignored with a warning). The seizure flags use this: `stim_induced`
(stimulation-induced vs spontaneous) and `lvfa` (low-voltage fast activity at onset), both
`true` | `false`, which seizure-consensus splits its scores by. The demo script writes the
expert consensus of the Multi-Expert Seizure Annotation dataset in this form, flags included;
other datasets can do the same.

### Precision

EDF stores 16-bit integers per channel with a physical min/max. `ieeg-prep` sets each
channel's range from its own data (robust max of |x| × 1.1, at least ±1 µV), so quantisation
is far below the noise floor of iEEG (≥ 0.05 µV steps on a ±1.5 mV channel). Amplitudes are
in µV in the files (BIDS units column `µV`).

## Tables written by the analysis steps

All CSV, UTF-8, header row, `.` decimal, long format keyed by `recording_id` and `channel`
(the `_channels.tsv` name, e.g. `LA01-LA02`). Times are seconds from the recording start.
Each step also writes its parameters into `provenance.json`.

| Step | Files |
|---|---|
| ieeg-spikes | `spikes.csv` (recording_id, channel, time_s, amplitude_uv, detector), `spike_rates.csv` (recording_id, channel, n_spikes, minutes, rate_per_min, detector) |
| ieeg-bandpower | `bandpower.csv` (recording_id, channel, band, abs_power, rel_power) with bands delta 1–4, theta 4–8, alpha 8–13, beta 13–30, gamma 30–80 Hz (Bernabei 2022), plus `broadband` |
| ieeg-hfo | `hfo.csv` (recording_id, channel, start_s, end_s, band ripple/fast_ripple, detector), `hfo_rates.csv`; writes an empty table with `skipped` status when sfreq < 1000 Hz |
| ieeg-normative | `abnormality.csv` (recording_id, channel, band, z, abs_z, region, n_reference) and `channel_abnormality.csv` (recording_id, channel, max_abs_z, region, n_reference) |
| seizure-dynasd | `dynasd/seizure_onsets.csv` (recording_id, onset_s, method) and `dynasd/channel_onsets.csv` (recording_id, channel, onset_s, recruited, score, method) |
| seizure-ei | `ei/ei.csv` (recording_id, channel, ei, detection_s, ratio_peak) |
| seizure-fragility | `fragility/fragility.csv` (recording_id, channel, fragility_pre, fragility_post, rank) |
| seizure-consensus | `onset_zone.csv` (recording_id, channel, score per method, rank, in_onset_zone), `scores.csv` (recording_id, method, metric, value) against the expert labels when known |

## Ports

| App | Inputs | Outputs |
|---|---|---|
| ieeg-prep | `ieeg` (anything readable; subfolder) | `ieeg` (the derivative), `qc` (qc.csv, plots) |
| ieeg-spikes / ieeg-bandpower / ieeg-hfo | `ieeg` | the step's tables (one output) |
| ieeg-normative | `features` (bandpower tables), `reference` (the normative atlas), `ieeg` (for labels/coordinates) | `abnormality` |
| seizure-dynasd | `ieeg` | `onsets` (content under `dynasd/`) |
| seizure-ei / seizure-fragility | `ieeg`, `onsets` (optional; their own onset estimate otherwise) | the step's table (under `ei/` / `fragility/`) |
| seizure-consensus | `ieeg`, `methods` (fan-in of the method outputs: `dynasd/`, `ei/`, `fragility/` side by side) | `onset-zone` |
| ieeg-report | `ieeg`, `qc`, and any of `spikes, bandpower, hfo, abnormality, onsets, methods, onset-zone` (all optional, subfolder) | `report` (index.html + figures), `tables` |

Fan-in ports are seizure-consensus `methods` and ieeg-report `methods`; only the three method
apps link into them, so only they write under a folder named after themselves. ieeg-spikes,
ieeg-hfo, ieeg-bandpower and ieeg-normative each feed a port of their own (ieeg-report
`spikes`, `hfo`, `bandpower`, `abnormality`; ieeg-normative `features`), one link per port, and
write at the root of `OUTPUT_DIR` (ieeg-spikes and ieeg-hfo under `<LABEL>/` when `LABEL` is
set, for a second run with other settings). A new port that takes several of their outputs
would need the same folder rule.

## Demo data

`data/` (gitignored), from `scripts/fetch-sample-data.sh`:

- `data/seizures/`: Pennsieve Discover 530 v3, "Multi-Expert Seizure Annotation" (Ojemann W,
  Zhou D, Armstrong C, Sinha N, Litt B, Conrad E; doi:10.26275/dely-fzwx; CC BY 4.0). BIDS-iEEG
  SEEG, EDF, 1024 Hz, ~118 channels, clips with 120 s before the clinically marked onset.
  `annotations.tsv`: per seizure the 3–5 clinicians' unequivocal electrographic onset (UEO)
  times and channels, the consensus (`ueo_time_consensus`, `ueo_consensus`, `sec_consensus`),
  stimulation-induced or spontaneous, and low-voltage fast activity (`lvfa`). Times are seconds
  since implant; a clip (`task-ictal<N>` spontaneous, `task-stim<N>` stimulation-induced) starts
  at `approximate_onset` − 120 s (its events.tsv puts the approximate onset at 120.0 s), so
  `onset_s = ueo_time_consensus − approximate_onset + 120`. The subject is the `patient` column.
  The annotation files are under `data/seizures/DATA/`; `scripts/seizures-to-labels.py` writes
  `data/seizures/labels.csv`. Default subset: HUP224, HUP230,
  HUP235, HUP238, HUP250, HUP257, four seizures each.
- `data/atlas/`: Pennsieve Discover 179 v1, "HUP Interictal iEEG Atlas" (Bernabei J, Litt B;
  doi:10.26275/lzhy-ox20; ODC-By). `HUP_atlas_final.mat`: `wake_clip` (12000 samples = 60 s at
  200 Hz × 3431 bipolar channels, 0.5–80 Hz), `mni_coords`, `patient_no`, `resected_ch`,
  `soz_ch`, `spike_24h`. Paper: Bernabei JM, Sinha N, et al. Normative intracranial EEG maps
  epileptogenic tissues in focal epilepsy. Brain 2022. doi:10.1093/brain/awab480.

For local tests use a few recordings and short windows unless measuring memory and time;
Docker on the dev Mac has 8 GB and is shared.
