"""Build an immutable, compact scientific archive without rerunning experiments.

Only the standard library is required. Existing delivery files are never replaced.
The five frozen scientific implementation files are read, hashed, and not edited.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import sys
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DATA = ["extended_hourly_2019_2025_v1.parquet", "extended_native_2019_2025_v1.parquet"]
MAIN_RUNS = ["development_full_v1", "external_main_v1", "temporal_main_v1",
             "temporal_delay6_v1", "temporal_delay72_v1", "temporal_rho0_v1"]
SELECTION_RUNS = [f"develop_C{i}_v2" for i in range(4)]
POSTHOC_RUNS = ["external_reconstruction_sensitivity_v1", "temporal_reconstruction_sensitivity_v1"]
SUMMARIES = ["paper_analysis_main", "paper_analysis_sensitivity", "paper_analysis_reconstructors"]
SCRIPTS = ["acquire_usgs.py", "acquire_extended.py", "prepare_data.py", "prepare_extended.py",
           "audit_extended_data.py", "derive_extended_eligibility.py", "replay.py", "paper_context.py",
           "paper_metrics.py", "value_sampling.py", "run_value_experiment.py", "freeze_paper.py",
           "summarize_paper.py", "diagnose_sampling.py", "reconstruction_sensitivity.py",
           "verify_paper_results.py", "verify_reconstruction_results.py", "plot_paper.py",
           "build_reproducibility_package.py"]
DOCS = ["FULL_PAPER_PLAN.md", "VALUE_SAMPLING_METHOD.md", "EXTENDED_DATA.md", "DSS_SPEC.md",
        "REFERENCE_LIBRARY.json", "EVIDENCE_AND_POSITIONING.md", "PAPER_CODE_REVIEW.md",
        "FINAL_METHOD_AUDIT.md", "FINAL_NUMERICAL_AUDIT.md", "FINAL_SCIENTIFIC_AUDIT.md"]
TESTS = ["test_paper_metrics.py", "test_reconstruction_sensitivity.py", "test_replay.py", "test_value_sampling.py"]
COMPACT_FILES = ["metrics.csv", "events.csv", "sampling_attempts.csv", "model_audit.json",
                 "run_manifest.json", "independent_verification.json"]
PACKAGES = ["numpy", "pandas", "scipy", "scikit-learn", "requests", "pyarrow", "matplotlib", "joblib"]
EXCLUSIONS = ["original USGS download bodies (immutable raw repository)", "raw article PDFs or full text",
              "cache and trained joblib contexts", "query_trace.parquet", "predictions.parquet",
              "old pilot and smoke outputs", "superseded summary directories", "manuscript and Word artifacts",
              "document-generation code and dependencies", "root README maintained separately"]


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def encode(value) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def inventory(root: Path):
    entries = {}

    def add(relative, category):
        relative = str(relative).replace("\\", "/")
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f"Missing or outside-project source: {relative}")
        if relative in entries:
            raise ValueError(f"Duplicate source: {relative}")
        entries[relative] = {"path": relative, "category": category,
                             "bytes": path.stat().st_size, "sha256": digest(path)}

    for name in DATA:
        add("datasets/" + name, "processed_observations")
    for path in sorted((root / "datasets").glob("*.json")):
        add(path.relative_to(root), "data_provenance")
    add("requirements-pilot.txt", "environment")
    for name in SCRIPTS:
        add("scripts/" + name, "scientific_code")
    for name in TESTS:
        add("tests/" + name, "tests")
    for name in DOCS:
        add("docs/" + name, "method_protocol_sources_and_audits")
    for path in sorted((root / "results/frozen_paper_v1").iterdir()):
        if path.is_file():
            add(path.relative_to(root), "frozen_configuration_and_snapshot")
    for name in MAIN_RUNS + SELECTION_RUNS:
        for filename in COMPACT_FILES:
            add(f"results/paper_runs/{name}/{filename}", "compact_run")
    for name in POSTHOC_RUNS:
        for filename in ["metrics.csv", "events.csv", "run_manifest.json"]:
            add(f"results/paper_runs/{name}/{filename}", "posthoc_fixed_calendar_run")
    # Only station-level final diagnostics are archived; event-level diagnostics
    # are reproducible from the included events/attempts and duplicate those data.
    for filename in ["station_policy_diagnostics.csv", "station_pair_diagnostics.csv", "diagnostic_manifest.json"]:
        add("results/paper_runs/temporal_main_v1/sampling_diagnostics/" + filename, "compact_diagnostics")
    for name in SUMMARIES:
        for path in sorted((root / "results" / name).iterdir()):
            if path.is_file() and path.suffix in {".csv", ".json"}:
                add(path.relative_to(root), "final_summary")
    for pattern in ["extended_data_*.csv", "extended_data_verification_*.json", "extended_eligibility_change_*.json"]:
        for path in sorted((root / "results").glob(pattern)):
            add(path.relative_to(root), "data_checks")
    for filename in ["INDEPENDENT_PAPER_RESULT_ACCEPTANCE.json", "INDEPENDENT_PAPER_SELECTION_CHECK.json",
                     "INDEPENDENT_RECONSTRUCTOR_CHECK.json"]:
        add("results/" + filename, "independent_verification")
    return entries


def freeze_checks(root, entries):
    freeze = read_json(root / "results/frozen_paper_v1/freeze_manifest.json")
    checks = {"selected_config_is_C2": freeze["selected_config"] == "C2",
              "hourly_matches_freeze": entries["datasets/" + DATA[0]]["sha256"] == freeze["data_sha256"]}
    for filename, expected in freeze["code_sha256"].items():
        checks["frozen_code:" + filename] = entries["scripts/" + filename]["sha256"] == expected
    prep = read_json(root / "datasets/extended_preparation_manifest_v1.json")
    for kind, info in prep["output_files"].items():
        filename = next(name for name in DATA if f"_{kind}_" in name)
        checks["prepared_" + kind + "_hash"] = entries["datasets/" + filename]["sha256"] == info["sha256"]
    for run in MAIN_RUNS + SELECTION_RUNS:
        report = read_json(root / f"results/paper_runs/{run}/independent_verification.json")
        checks["archived_verification_PASS:" + run] = report["status"] == "PASS"
    for filename in ["INDEPENDENT_PAPER_RESULT_ACCEPTANCE.json", "INDEPENDENT_PAPER_SELECTION_CHECK.json",
                     "INDEPENDENT_RECONSTRUCTOR_CHECK.json"]:
        checks["archived_check_PASS:" + filename] = read_json(root / "results" / filename)["status"] == "PASS"
    if not all(checks.values()):
        raise ValueError({key: value for key, value in checks.items() if not value})
    return checks


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def reproduction_commands(root):
    """Generate actual CLI arguments from preserved manifests, with fresh outputs."""
    lines = ["# Run from the extracted project root on D:. Requires a scientific Python environment.",
             "# These commands perform NEW runs, potentially with substantial output; not run by the packager.",
             "$ErrorActionPreference = 'Stop'", "$env:PYTHONDONTWRITEBYTECODE = '1'",
             "$env:JOBLIB_TEMP_FOLDER = Join-Path (Get-Location) 'temp'",
             "$env:TEMP = $env:JOBLIB_TEMP_FOLDER", "$env:TMP = $env:JOBLIB_TEMP_FOLDER",
             "New-Item -ItemType Directory -Force -Path $env:JOBLIB_TEMP_FOLDER | Out-Null",
             "if ((Get-Location).Drive.Name -ne 'D') { throw 'Extract and run on D:.' }", ""]
    commands = []
    for name in SELECTION_RUNS + MAIN_RUNS:
        args = read_json(root / f"results/paper_runs/{name}/run_manifest.json")["arguments"]
        cmd = ["python", "-B", "scripts/run_value_experiment.py", "--data", "datasets/" + DATA[0]]
        for key in ["stage", "years", "sites", "seeds", "budgets", "policies", "reconstruction_modes",
                    "config_id", "delay_hours", "noise_adaptation_rate"]:
            value = args[key]
            if value is None:
                continue
            cmd.append("--" + key.replace("_", "-"))
            cmd.extend(str(v) for v in value) if isinstance(value, list) else cmd.append(str(value))
        if args["freeze_manifest"]:
            cmd.extend(["--freeze-manifest", "results/frozen_paper_v1/freeze_manifest.json"])
        newname = name + "_reproduction"
        cmd.extend(["--run-name", newname])
        if args["save_predictions"]:
            cmd.append("--save-predictions")
        command = " ".join(ps_quote(word) if " " in word else word for word in cmd)
        lines.extend([f"# Original: {name}", f"if (Test-Path -LiteralPath 'results/paper_runs/{newname}') {{ throw 'Output exists: {newname}' }}",
                      command, "if ($LASTEXITCODE -ne 0) { throw 'Scientific run failed' }", ""])
        commands.append({"original_run": name, "new_run": newname, "argv": cmd})
    for name in POSTHOC_RUNS:
        parent = "external_main_v1" if name.startswith("external") else "temporal_main_v1"
        cmd = ["python", "-B", "scripts/reconstruction_sensitivity.py", "--parent",
               f"results/paper_runs/{parent}_reproduction", "--output", f"results/paper_runs/{name}_reproduction"]
        lines.extend(["# POSTHOC: fixed realized calendars, not a new closed loop.", " ".join(cmd),
                      "if ($LASTEXITCODE -ne 0) { throw 'Posthoc reconstruction failed' }", ""])
        commands.append({"original_run": name, "argv": cmd, "posthoc": True})
    for name in SUMMARIES:
        manifest = read_json(root / f"results/{name}/summary_manifest.json")
        names = []
        for run in manifest["run_manifests"]:
            args = run["arguments"]
            original = args.get("run_name")
            if original is None:
                original = str(args["output"]).replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
            names.append(original)
        cmd = ["python", "-B", "scripts/summarize_paper.py"]
        cmd.extend("results/paper_runs/" + name + "_reproduction" for name in names)
        cmd.extend(["--output", "results/" + name + "_reproduction"])
        lines.extend([" ".join(cmd), "if ($LASTEXITCODE -ne 0) { throw 'Summary failed' }", ""])
        commands.append({"original_summary": name, "argv": cmd})
    return ("\n".join(lines) + "\n").encode("utf-8"), commands


README = r"""RIVER NUTRIENT ADAPTIVE SAMPLING: COMPACT SCIENTIFIC REPRODUCIBILITY PACKAGE

Scope and interpretation
This package contains the exact processed hourly and native-interval USGS-derived
data, scientific code, tests, frozen selection record and source snapshot, compact
results, final summaries, and existing independent verification records. It is a
scientific archive, not the manuscript or a submission bundle. No experiment was
rerun to build this archive. The dated freeze is an internal record, not a public
preregistration. The spatial extension is held out from policy-configuration
selection; its local historical observations still train its site-specific model.

Included runs
  Selection: develop_C0_v2, develop_C1_v2, develop_C2_v2, develop_C3_v2.
  Main/development: development_full_v1, external_main_v1, temporal_main_v1.
  Sensitivity: temporal_delay6_v1, temporal_delay72_v1, temporal_rho0_v1.
  Post-result: external_reconstruction_sensitivity_v1 and
               temporal_reconstruction_sensitivity_v1.
The post-result analyses reuse the original realized sample calendars. They do
not simulate new closed-loop policies, retune policies, or establish why a label
improved accuracy. Their attempts are stored in the corresponding main parent run.
The frozen setting is C2: H=72 h, state half-life=2160 h, query quantile=0.85.
Recorded factors, seeds, exclusions, and timing are in each run_manifest.json.

Data and provenance
datasets/extended_hourly_2019_2025_v1.parquet and
datasets/extended_native_2019_2025_v1.parquet are the frozen processed inputs.
The native file retains the interval observations used in the reference-load
calculation; it is not the original downloaded response body. Acquisition and
preparation manifests preserve download URLs, retrieval times, original filenames,
raw-response hashes, instrument metadata, processing choices, and output hashes.
Source USGS parameter codes are 99133 (sensor nitrate plus nitrite) and 00060
(discharge). Consult docs/EXTENDED_DATA.md and the preparation manifest for exact
qualifier, instrument, and support restrictions. Missing hours are not filled
into a claimed complete annual reference load.

Original downloaded response bodies and raw article PDFs are NOT included. The
original raw repository is F:/AcademicData/NitrateAdaptiveSampling_20261005/raw;
its filenames in manifests are historical provenance locators, not portable
links inside this ZIP. Code for USGS discovery and retrieval is included, using
https://api.waterdata.usgs.gov/ogcapi/v1/collections and the request URLs recorded
in datasets/*acquisition*.json. Remote records can be revised; downloading again
does NOT promise byte-identical data or the same sample. Frozen processed files
allow result reproduction without a network connection.

Environment and storage
Observed environment: Python 3.12.10 on Windows. requirements-pilot.txt is the
existing scientific dependency lock despite its historical filename. It includes
NumPy, pandas, SciPy, scikit-learn, requests, PyArrow and Matplotlib. joblib is a
scikit-learn dependency; the observed version is recorded in ENVIRONMENT.json.
No GPU, Word runtime, document plugin, or PDF software is needed. Match pinned
versions for the closest numerical reproduction; platform and parallel-library
differences may still affect floating-point output and timings. Package building
and hash verification use only the Python standard library.

Extract into a NEW directory on D:, preserving scripts/, datasets/, docs/, tests/
and results/. Do not merge over an existing project. Keep computation, temporary
files and outputs on D:. Allow several GB for fresh context caches and full traces;
the compact ZIP size is not the disk requirement of a full rerun. For example in
PowerShell, after changing to the extracted root:

  New-Item -ItemType Directory -Force -Path temp | Out-Null
  $env:TEMP = Join-Path (Get-Location) 'temp'
  $env:TMP = $env:TEMP
  $env:JOBLIB_TEMP_FOLDER = $env:TEMP
  $env:PYTHONDONTWRITEBYTECODE = '1'
  python -m venv D:/MLWork/nitrate_reproduction_env
  D:/MLWork/nitrate_reproduction_env/Scripts/Activate.ps1
  python -m pip install --no-cache-dir -r requirements-pilot.txt

Choose a new environment name if it already exists. The original Python binary
may reside on C:; project data, caches, training output and this environment are
placed on D:. Do not edit the five frozen scientific files, because holdout runs
verify their hashes. Acquisition and early data-audit utilities retain original
WORK/RAW constants and historical path assumptions; inspect and change them only
in a separate working copy when relocating or creating a new raw-data version.
There is no single portable top-level path configuration. Preserved manifests
also contain historical absolute paths, which must not be mistaken for files in
the extracted archive. The generated fresh-run commands pass a relative data
path and create new manifests, avoiding edits to the preserved manifests.

Fast local checks and summary reproduction (no new policy experiment)
  python -B -m unittest discover -s tests -v
  python -B scripts/diagnose_sampling.py --self-check
  python -B scripts/build_reproducibility_package.py --verify-archive delivery/reproducibility_archive.zip
The last command applies when the supplied archive is stored at that path; use
its actual path otherwise. It verifies CRCs and all embedded SHA256 payload hashes.
The external package_manifest.json additionally records the final ZIP SHA256.

Recompute the main summary directly from the included compact outputs:
  python -B scripts/summarize_paper.py results/paper_runs/development_full_v1 results/paper_runs/temporal_main_v1 results/paper_runs/external_main_v1 --output results/recheck_main_summary

Compute descriptive diagnostics in a new output directory:
  python -B scripts/diagnose_sampling.py --run-dir results/paper_runs/temporal_main_v1 --output-dir results/recheck_temporal_diagnostics

These commands refuse existing output directories/files where implemented. Use
new names on every rerun and do not pass --overwrite. Summary point estimates and
bootstrap calculations are reproducible from compact metrics. Trace-dependent
diagnostics will be unavailable without regenerating query_trace.parquet; the
archived station diagnostics reflect the original full run. The archive retains
their original manifest, including references to omitted event-level diagnostic
CSVs. Those CSVs can be regenerated from included attempts/events. No p-values or
causal interpretation are supplied for capture/error associations. Event ratios
exclude sites with no events from their denominator; see the method document.

Fresh scientific experiments
REPRODUCTION_COMMANDS.ps1 contains exact actual CLI factors generated from each
preserved run manifest, with fresh *_reproduction run names. Inspect before
execution; it runs selection configurations, six main/sensitivity experiments,
two post-result reconstructions, and three final summaries. Its commands were
checked against the current argument parsers. It is not an additional experiment
performed during packaging. The archived freeze is used for locked runs. The
four selection runs allow the C0-C3 comparison to be inspected; freeze_paper.py
has no CLI output option and refuses an existing frozen_paper_v1 directory. To
rerun that historical selection script, use a separate clean working copy with
the expected selection names and no existing freeze output; preserve this archive.

Individual full-run verification after regeneration, for example:
  python -B scripts/verify_paper_results.py --run results/paper_runs/temporal_main_v1_reproduction --allow-2025 --native-probe --output results/temporal_reproduction_check.json
Use a new --output filename. This verifier itself can overwrite a named report;
never direct it at an existing archived verification JSON. The batch mode also
writes inside run directories, so it is not a read-only check of the archive.

Full versus compact verification
Each preserved independent_verification.json and results/INDEPENDENT_*.json
reports checks performed on the original complete run. Packaging validates those
records' PASS statuses and hashes the records, but does not rerun their scientific
calculations. Predictions, query traces and joblib contexts are intentionally
omitted. Consequently, running the full run verifier on a compact archived run
will fail completeness checks; regenerate a fresh full run first. The posthoc
verifier verify_reconstruction_results.py has no CLI: it expects original run and
summary names, original cached contexts, full parent predictions, and writes a
fixed verification output. It is provenance code, not a portable one-command
check of this compact archive. Adapt its paths in a separate copy for regenerated
runs, preserving the archived source and report. Similarly audit_extended_data.py
requires original raw files and the earlier pilot overlap inputs that are not
included. Plotting uses the fixed final-summary names and writes manuscript/
figures; inspect the script before running it in any existing working tree.

The publication aggregation is the seed mean, then available years within each
site, then an equal-site mean. Some earlier verification reports also contain a
median diagnostic; that field is not the publication estimand. Three final
summary directories are included; superseded summaries and old pilot runs are
excluded. Methods and audits preserve their dates and scopes; the implementation,
freeze and exact final result tables define the executable scientific record.

New raw acquisition (optional; not required for result reproduction)
In a separate workspace, configure WORK to a new D: project and RAW to a new F:
raw directory. Check free space first. Do not point acquisition at archived
manifests whose response files are unavailable: the existing-record reuse logic
expects those files. Use a new clean dataset registry and unique retrieval names.
Actual CLI examples, after updating those path constants:
  python -B scripts/acquire_extended.py --mode discover --workers 3
  python -B scripts/acquire_extended.py --mode download --years 2019 2020 2021 2022 2023 2024 2025 --workers 3 --limit-to-known-nox-span
  python -B scripts/prepare_extended.py --tag reproduction_new --start-year 2019 --end-year 2025
Do not overwrite, move, edit or delete original raw files. Updated online data
constitute a new data version and will not pass the original frozen data hash.

Archive integrity
PACKAGE_CONTENTS.json inside the ZIP lists every other member's byte count and
SHA256. It is excluded from its own recursive hash list by construction. The
external package_manifest.json includes the final ZIP size/hash and validation
results. Hashes detect changes; they are not a cryptographic identity signature.
Rebuilding uses current allowlisted files and fresh metadata and is not expected
to yield the same ZIP byte sequence. The packager refuses existing target files.
No existing source, raw file, frozen scientific code, or scientific result is
modified by packaging. No automated external publication or archival upload occurs.
"""


def validate_archive(path: Path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate ZIP members")
        for name in names:
            relative = PurePosixPath(name)
            if relative.is_absolute() or ".." in relative.parts or "\\" in name:
                raise ValueError("Unsafe ZIP path: " + name)
        bad = archive.testzip()
        if bad is not None:
            raise ValueError("CRC failure: " + bad)
        contents = json.loads(archive.read("PACKAGE_CONTENTS.json"))
        expected = {entry["path"]: entry for entry in contents["files"]}
        if set(names) != set(expected) | {"PACKAGE_CONTENTS.json"}:
            raise ValueError("Archive members differ from embedded inventory")
        total = 0
        for name, entry in expected.items():
            value = hashlib.sha256()
            count = 0
            with archive.open(name) as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    value.update(block)
                    count += len(block)
            if count != entry["bytes"] or value.hexdigest() != entry["sha256"]:
                raise ValueError("Payload hash/size mismatch: " + name)
            total += count
    return {"status": "PASS", "crc": "PASS", "payload_sha256": "PASS", "safe_unique_paths": True,
            "payload_files_verified": len(expected), "zip_members": len(names), "payload_bytes": total,
            "archive_bytes": path.stat().st_size, "archive_sha256": digest(path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "delivery")
    parser.add_argument("--verify-archive", type=Path, help="Read-only CRC and payload SHA256 check; no package creation")
    args = parser.parse_args()
    if args.verify_archive:
        print(json.dumps(validate_archive(args.verify_archive.resolve()), indent=2))
        return
    root = ROOT.resolve()
    output = args.output_dir.resolve()
    if os.name == "nt" and output.drive.upper() != "D:":
        raise ValueError("All package output must be on D:")
    output.mkdir(parents=True, exist_ok=True)
    targets = [output / name for name in ["reproducibility_archive.zip", "README_reproducibility.txt", "package_manifest.json"]]
    if any(path.exists() for path in targets):
        raise FileExistsError("Delivery target exists; choose a new --output-dir. Existing files will not be overwritten.")
    entries = inventory(root)
    checks = freeze_checks(root, entries)
    free = shutil.disk_usage(output).free
    required = sum(entry["bytes"] for entry in entries.values()) * 2 + 64 * 1024 * 1024
    if free < required:
        raise RuntimeError(f"Insufficient D: space: free={free}, conservative_required={required}")
    environment = {"python": platform.python_version(), "platform": platform.platform(), "packages": {},
                   "dependency_lock": "requirements-pilot.txt", "requires_gpu": False}
    for name in PACKAGES:
        try:
            environment["packages"][name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            environment["packages"][name] = None
    command_bytes, command_records = reproduction_commands(root)
    generated = {"README_reproducibility.txt": README.encode("utf-8"),
                 "ENVIRONMENT.json": encode(environment), "REPRODUCTION_COMMANDS.ps1": command_bytes,
                 "REPRODUCTION_COMMANDS.json": encode(command_records)}
    for name, content in generated.items():
        entries[name] = {"path": name, "category": "generated_reproduction_guidance", "bytes": len(content),
                         "sha256": hashlib.sha256(content).hexdigest()}
    contents = {"created_utc": datetime.now(timezone.utc).isoformat(), "scope": "compact scientific reproducibility archive",
                "inventory_excludes_itself": "PACKAGE_CONTENTS.json", "files": sorted(entries.values(), key=lambda x: x["path"]),
                "main_runs": MAIN_RUNS, "selection_runs": SELECTION_RUNS, "posthoc_runs": POSTHOC_RUNS,
                "excluded": EXCLUSIONS, "freeze_and_existing_record_checks": checks, "environment": environment}
    temporary = output / (".reproducibility_" + uuid.uuid4().hex + ".tmp")
    try:
        with zipfile.ZipFile(temporary, mode="x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for name in sorted(entries):
                if name in generated:
                    archive.writestr(name, generated[name])
                else:
                    archive.write(root / name, arcname=name)
            archive.writestr("PACKAGE_CONTENTS.json", encode(contents))
        validation = validate_archive(temporary)
        # Catch concurrent edits without mutating or attempting to repair them.
        for name, entry in entries.items():
            if name not in generated and digest(root / name) != entry["sha256"]:
                raise RuntimeError("Source changed while packaging; retry in a new output directory: " + name)
        if targets[0].exists():
            raise FileExistsError(targets[0])
        temporary.rename(targets[0])
        manifest = {**contents, "archive": {"filename": targets[0].name, "bytes": validation["archive_bytes"],
                                            "sha256": validation["archive_sha256"]},
                    "validation": validation, "source_files_unchanged_after_packaging": True,
                    "free_output_drive_bytes_before_build": free,
                    "category_counts": dict(Counter(entry["category"] for entry in entries.values())),
                    "experiments_run_during_packaging": False}
        with targets[1].open("xb") as handle:
            handle.write(generated["README_reproducibility.txt"])
        with targets[2].open("xb") as handle:
            handle.write(encode(manifest))
        print(json.dumps({"output": str(targets[0]), "validation": validation,
                          "category_counts": manifest["category_counts"], "source_checks": len(checks)}, indent=2))
    finally:
        if temporary.exists():
            temporary.unlink()


if __name__ == "__main__":
    main()
