#!/usr/bin/env python3
"""
Writes the epilepsy iEEG workflow definitions (workflow/*.json, the body of
POST /compute/workflows/definitions) from the step lists below. Add
"organizationId": "N:organization:..." to the body when posting: without it
the workflow belongs to no workspace and the Workflow Library doesn't list it
(an organization_id query parameter is not enough). Each step's
cpu/memory comes from its app's app.yml runtime (the sibling repo
../processor-<app>), so the definitions follow the apps.

Each step pins the newest release tag at or before the checked-out commit of its app.

Usage: scripts/build-workflows.py
"""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORG = "https://github.com/pennsieve-apps"
COL, ROW = 260, 130  # canvas grid


def runtime(app: str) -> tuple[str, str]:
    path = ROOT.parent / f"processor-{app}" / "app.yml"
    if not path.exists():
        raise SystemExit(f"{path} not found: check out processor-{app} next to this repo")
    text = path.read_text()
    block = re.search(r"^runtime:\n((?:[ #].*\n?)*)", text, re.M).group(1)
    cpu = re.search(r"^\s+cpu:\s*(\d+)", block, re.M).group(1)
    mem = re.search(r"^\s+memory:\s*(\d+)", block, re.M).group(1)
    return cpu, mem


def release_tag(app: str) -> str:
    """The newest release tag at or before the checked-out commit, after refreshing tags from
    origin (local tags can be stale). Commits after it (docs, CITATION.cff) are not released yet."""
    repo = ROOT.parent / f"processor-{app}"
    git = lambda *a: subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True)
    git("fetch", "-q", "--tags", "--force", "origin")
    tag = git("describe", "--tags", "--abbrev=0", "--match", "v*", "HEAD").stdout.strip()
    if not tag:
        raise SystemExit(f"processor-{app}: no release tag at or before HEAD")
    # Several tags can mark one commit (v0.1.0 cut before App Store publishing was on, v0.1.1
    # re-released to build it); describe prefers annotated ones, but the newest is the deployed one.
    commit = git("rev-list", "-n1", tag).stdout.strip()
    same = git("tag", "--points-at", commit, "--list", "v*").stdout.split()
    tag = max(same, key=lambda t: [int(n) for n in re.findall(r"\d+", t)])
    ahead = git("rev-list", "--count", f"{tag}..HEAD").stdout.strip()
    if ahead not in ("", "0"):
        print(f"note: processor-{app} is {ahead} commit(s) past {tag}; the workflow pins {tag}")
    return tag


# Fargate accepts only some cpu/memory pairs (MiB): the least memory each cpu allows. An app
# that asks for less (e.g. 4 vCPU / 4 GiB) has its step rounded up, or the task is refused.
FARGATE_MIN_MEMORY = {256: 512, 512: 1024, 1024: 2048, 2048: 4096, 4096: 8192, 8192: 16384, 16384: 32768}


def fargate_memory(cpu: str, mem: str) -> str:
    floor = FARGATE_MIN_MEMORY.get(int(cpu), 0)
    if int(mem) < floor:
        print(f"note: {cpu} cpu / {mem} MiB is not a Fargate size; using {floor} MiB")
        return str(floor)
    return mem


def step(id_, app, col, row, depends, links=(), params=None):
    cpu, mem = runtime(app)
    mem = fargate_memory(cpu, mem)
    tag = release_tag(app)
    node = {
        "id": id_,
        "type": "processor",
        "sourceUrl": f"{ORG}/processor-{app}",
        "tag": tag,
        "dependsOn": list(depends),
        "position": {"x": 40 + COL * col, "y": 40 + ROW * row},
        "cpu": cpu,
        "memory": mem,
    }
    if links:
        node["inputs"] = [{"from": f, "output": o, "input": i} for f, o, i in links]
    if params:
        node["defaultParams"] = params
    return node


def output(id_, name, step_, out, folder, col, row, default=True):
    o = {"id": id_, "name": name, "from": {"step": step_, "output": out},
         "position": {"x": 40 + COL * col, "y": 40 + ROW * row}}
    if default:
        o["default"] = {"targetType": "Pennsieve Dataset", "params": {"TARGET_FOLDER": folder}}
    return o


IEEG_INPUT = {
    "id": "ieeg",
    "name": "iEEG recordings",
    "description": "Intracranial EEG (SEEG/ECoG): a BIDS-iEEG dataset or EDF, BrainVision, FIF or MEF3 "
                   "recordings, plus an optional labels.csv (SOZ, resected, expert onset channels and times).",
    "position": {"x": 40, "y": 40 + ROW * 2},
}

PREP = lambda col, row: step("prep", "ieeg-prep", col, row, ["ieeg"])


def seizure_onset():
    steps = [
        PREP(1, 2),
        step("dynasd", "seizure-dynasd", 2, 2, ["prep"], [("prep", "ieeg", "ieeg")]),
        step("ei", "seizure-ei", 3, 1, ["prep", "dynasd"], [("prep", "ieeg", "ieeg"), ("dynasd", "onsets", "onsets")]),
        step("fragility", "seizure-fragility", 3, 3, ["prep", "dynasd"], [("prep", "ieeg", "ieeg"), ("dynasd", "onsets", "onsets")]),
        step("consensus", "seizure-consensus", 4, 2, ["prep", "dynasd", "ei", "fragility"],
             [("prep", "ieeg", "ieeg"), ("dynasd", "onsets", "methods"), ("ei", "ei", "methods"),
              ("fragility", "fragility", "methods")]),
        step("report", "ieeg-report", 5, 2, ["prep", "dynasd", "ei", "fragility", "consensus"],
             [("prep", "ieeg", "ieeg"), ("prep", "qc", "qc"), ("dynasd", "onsets", "methods"),
              ("ei", "ei", "methods"), ("fragility", "fragility", "methods"), ("consensus", "onset-zone", "onset-zone")],
             {"REPORT_TITLE": "Seizure Onset Localisation"}),
    ]
    return {
        "name": "Seizure Onset Localisation (iEEG)",
        "summary": "SEEG seizures: DynaSD onset, Epileptogenicity Index, neural fragility, consensus zone, report.",
        "description": (
            "Localises the seizure onset zone in intracranial EEG (SEEG/ECoG) seizure recordings. Prepares the "
            "recordings (bipolar montage, notch, bad channels; BIDS-iEEG, EDF, BrainVision or MEF3), detects the "
            "seizure onset and the channels that start it with DynaSD (Ojemann et al. 2026), computes the "
            "Epileptogenicity Index (Bartolomei et al. 2008) and neural fragility (Li et al. 2021) around that "
            "onset, fuses the three channel rankings into a consensus onset zone, scores every method against "
            "expert labels when they are provided, and writes an HTML report. Research use only."),
        "inputs": [IEEG_INPUT],
        "processors": steps,
        "outputs": [
            output("report_out", "Report", "report", "report", "derivatives/seizure-onset/report", 6, 1),
            output("tables_out", "Tables", "report", "tables", "derivatives/seizure-onset/tables", 6, 2),
            output("zone_out", "Onset zone", "consensus", "onset-zone", "derivatives/seizure-onset/onset-zone", 6, 3),
            output("ieeg_out", "Prepared iEEG", "prep", "ieeg", "", 6, 4, default=False),
        ],
    }


def main():
    out = ROOT / "workflow"
    out.mkdir(exist_ok=True)
    for name, wf in (("seizure-onset-localisation", seizure_onset()),):
        assert len(wf["summary"].encode()) <= 100, (name, len(wf["summary"].encode()))
        (out / f"{name}.json").write_text(json.dumps(wf, indent=2) + "\n")
        print(f"wrote workflow/{name}.json ({len(wf['processors'])} steps)")


if __name__ == "__main__":
    main()
