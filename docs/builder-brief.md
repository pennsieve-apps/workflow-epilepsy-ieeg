# Brief for building an app of the epilepsy iEEG workflows

You are building one or more Pennsieve processor apps, each in its own git repo under
`~/code/pennsieve/<repo>` (remote `git@github.com:pennsieve-apps/<repo>.git`, public). The
apps form two workflows for epilepsy research and clinical evaluation at Penn:

- **1. Interictal Biomarker Mapping (iEEG/SEEG):**
  `ieeg-prep → {ieeg-spikes, ieeg-bandpower → ieeg-normative, ieeg-hfo} → ieeg-report`
- **2. Seizure Onset Localisation (SEEG):**
  `ieeg-prep → seizure-dynasd → {seizure-ei, seizure-fragility} → seizure-consensus
  (fan-in of dynasd, ei, fragility) → ieeg-report`

They must work on data beyond the demo: any BIDS-iEEG dataset, plain EDF/BrainVision/MEF3
recordings, SEEG or ECoG, any sampling rate ≥ 200 Hz, with or without labels.

## Read first

1. `~/code/pennsieve/workflow-epilepsy-ieeg/docs/conventions.md`: the file and port contract
   between apps. Follow it exactly. If something in it is wrong or missing, say so in your
   report instead of silently diverging.
2. A finished Python app to copy layout, tone and level of care from:
   `~/code/pennsieve/processor-fcs-prep` (Python: `processor/`, tests, Makefile,
   `docker-compose.yml`, `dev.env`, README with port table, parameters, runtime section with
   measured memory, `THIRD_PARTY.md`, `CITATION.cff`). An R one: `~/code/pennsieve/processor-cleanet`.
3. The app manifest schema: `~/code/pennsieve/workflow-immune-cytometry/docs/app-manifest.v1.schema.json`.
   Validate `app.yml` against it (`python3 -m venv` + `pip install jsonschema pyyaml` in your
   scratch dir). Do NOT add `application.relations` yet (not deployed).

## Every repo has

`app.yml` (`# yaml-language-server: $schema=https://schemas.pennsieve.io/app-manifest/v1.json`,
`schemaVersion: "1.0"`, `application` with name/description/type processor/tags, `runtime`
cpu/memory/computeTypes/timeoutSeconds, `parameters`, `inputs`, `outputs`). Tags include a
data domain and research fields the Apps tab understands: `ieeg`, `seeg`, `eeg`,
`electrophysiology`, `epilepsy`, `neuroscience`, plus task tags (`spike-detection`,
`quality-control`, `statistics`, `report`, ...).

`Dockerfile` (linux/amd64, pinned base image and package versions, non-interactive, no network
at run time, as small as reasonable; `python:3.12-slim` + pinned pip requirements),
`processor/` code, `tests/` (unit tests on a tiny synthetic fixture, no Docker), `Makefile`
(`test`, `fixture`, `run` = docker compose over a fixture into `data/output/`, `clean`),
`docker-compose.yml`, `dev.env`, `sample-input/README.md` (how to get real input),
`README.md`, `THIRD_PARTY.md` (every bundled component with its licence), `LICENSE`
(Apache-2.0 for our code; if the image links GPL code in-process, say so in THIRD_PARTY.md
and the README), `VERSION` (`0.1.0`), `CITATION.cff` (below), `.gitignore`.

Small, fast steps (consensus, report, normative) declare `computeTypes: [standard, lambda]`
with memory ≤ 3008 MB if they fit, and a `processor/handler.py` Lambda entry like
processor-brain-volumetrics. Heavy ones are `standard` only, sized from your measurement.

## README

What the app does and why, for an epileptologist and for a researcher; port table; parameters
table (defaults, what each does); outputs with columns; runtime (cpu/memory chosen and
**measured** peak memory and wall time on the demo data, saying it was amd64 emulation on an
M-series Mac); limitations (what the method cannot tell you); licences; **Citations**.

## Citations: verified, and in CITATION.cff

Every paper or software you cite: authors, title, journal, year, volume:pages, DOI (and PMID
if it has one). Verify each via `https://api.crossref.org/works/<DOI>` (or DataCite for
Zenodo/software DOIs, `https://api.datacite.org/dois/<DOI>`): title, author list and year must
match. Never cite something you could not verify; cite the software repo URL instead.

`CITATION.cff` (CFF 1.2.0): `type: software`, title = app name, abstract, `repository-code`
`https://github.com/pennsieve-apps/<repo>`, license, keywords, **one entity author**
`- name: Pennsieve (University of Pennsylvania)`, no `version`/`date-released`, and
`references:` for every cited work, with **authors exactly as Crossref/DataCite list them**
(all of them, in order). Validate with `cffconvert --validate`.

Already verified by the coordinator (re-check anyway):

- MNE-Python: Gramfort 2013, Front Neurosci, 10.3389/fnins.2013.00267
- MNE-BIDS: Appelhoff 2019, JOSS, 10.21105/joss.01896; iEEG-BIDS: Holdgraf 2019, Sci Data, 10.1038/s41597-019-0105-7
- Janca 2015, Brain Topogr, 10.1007/s10548-014-0379-1; Barkmeier 2012, Clin Neurophysiol, 10.1016/j.clinph.2011.09.023
- Bernabei 2022, Brain, 10.1093/brain/awab480; Taylor 2022, Brain, 10.1093/brain/awab380; Wang 2023, Epilepsia, 10.1111/epi.17663
- Staba 2002, J Neurophysiol, 10.1152/jn.2002.88.4.1743; Gardner 2007, Clin Neurophysiol, 10.1016/j.clinph.2006.12.019; Cimbálník 2018, J Neurosci Methods, 10.1016/j.jneumeth.2017.08.023; Zelmann 2012, Clin Neurophysiol, 10.1016/j.clinph.2011.06.006
- Bartolomei 2008 (Epileptogenicity Index), Brain, 10.1093/brain/awn111
- Li 2021 (neural fragility), Nat Neurosci, 10.1038/s41593-021-00901-w
- Ojemann 2026 (DynaSD), medRxiv, 10.64898/2026.02.15.26346325 (DataCite/Crossref; check)
- Conrad 2023, Epilepsia, 10.1111/epi.17482; SzCORE: Dan 2024, Epilepsia, 10.1111/epi.18113
- Demo data: Discover 530 doi:10.26275/dely-fzwx (CC BY 4.0); Discover 179 doi:10.26275/lzhy-ox20 (ODC-By)

## Licences (verified by a survey; re-check the LICENSE file of what you bundle)

- MNE-Python, MNE-BIDS: BSD-3-Clause. pymef: Apache-2.0. edfio: Apache-2.0. pyEDFlib: BSD-2-Clause.
- epycom (PyPI 0.3): LICENSE.txt is Apache-2.0 (PyPI metadata says BSD; treat as Apache-2.0).
- DynaSD (github.com/wojemann/DynaSD): MIT. The author (Will Ojemann) confirmed use of the
  code and the released checkpoints. Install from a pinned commit; vendor checkpoints into the
  image from the GitHub release `v0.1.0-checkpoints` at build time (pinned URL + sha256).
- EZFragility (CRAN): GPL-3.0-or-later; EZEI (KarasLabRAVE): GPL-3.0-or-later (reference only:
  the EI step reimplements Bartolomei 2008 in Python).
- jbernabei/iEEG_atlas and Penn CNT repos without a licence: do NOT copy code; reimplement
  from the paper. cnnp-lab/2023Wang_Temporal-stability is CC0-1.0 and may be used as a reference.
- Never use code with no licence, non-commercial, or academic-only terms.

## Test on real data

Demo data (read-only): `~/code/pennsieve/workflow-epilepsy-ieeg/data/seizures/` (BIDS-iEEG,
24 clips, 6 patients, plus `annotations.tsv`) and `data/atlas/HUP_atlas_final.mat`. Upstream
outputs, once other builders produce them, are in `~/code/pennsieve/workflow-epilepsy-ieeg/data/work/<step>/`
(e.g. `data/work/prep/ieeg`). If what you need isn't there yet, write a fixture generator in
`tests/make_fixture.py` that follows the contract (a small synthetic BIDS derivative with a few
channels, a seizure-like burst, spikes) and say so in your report; once `data/work/prep` exists,
re-run on it. Local Docker has 8 GB shared with other builders: test on 2–4 recordings, give
`docker run` a `--memory` limit, measure peak memory (`/sys/fs/cgroup/memory.peak` or
`docker stats`), remove your containers. Build images `--platform linux/amd64`.

## Git

`git init -b main` (if not yet a repo), commit with clear messages ending with
`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`, and add the remote
`git@github.com:pennsieve-apps/<repo>.git`. **Do not push, tag or create releases**: the
coordinator pushes and releases.

## Report back

Short: repo path, commits, ports and parameters as built, what you ran it on and the results
(numbers), measured memory/time, image size, chosen cpu/memory, citations with DOIs and how
you verified them, deviations from conventions.md, open problems.
