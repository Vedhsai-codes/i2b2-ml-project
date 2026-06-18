"""Drive an i2b2-ML phenotype model build THROUGH the JSON API.

This is the "through the tool" step the grant paper claims. It does NOT train a
model in-process; it asks the running i2b2-ML stack to do it:

  1. POST /etl/concepts          register the derived ML concept (+ blob with the
                                 positive/negative patient-set names, data/label paths).
  2. POST /etl/job               {"input":{"path": ml_concept_path}, "jobType":"ml"}
                                 -> a PENDING job the jobWatcher picks up -> mlEngine
                                 -> apply_build_model (elastic-net LogisticRegression).
  3. GET  /etl/job               poll until the job is COMPLETED / ERROR.
  4. GET  /etl/concepts          read back concept_blob (serialized_model + metrics).

Prereqs (do these first, e.g. via pipeline/load_and_build.sh):
  * concepts + facts loaded (etl concept load / etl fact load, --mrn-are-patient-numbers)
  * named patient sets created (pipeline/create_patient_sets.py)
  * the jobWatcher daemon running in the i2b2-ml container

Auth: HTTPBasicAuth ``demo\\demo`` / ``Etl@2021`` + header ``X-Project-Name: Demo``
(the project name MUST prefix the user; Swagger fails silently on bad auth).

Usage (from the Mac cockpit, stack on host port 5005):
    python pipeline/run_ml_build.py stroke --base-url http://localhost:5005
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "pipeline" / "config" / "phenotypes.yaml"


def load_config(path: Path = CONFIG_PATH) -> dict:
    with path.open() as fh:
        return yaml.safe_load(fh)


def build_blob(phenotype: str, config: dict) -> dict:
    """Assemble the ML concept blob for ``phenotype`` (patient-set ML path).

    Returned as a dict and sent as a nested JSON object (matching the working
    ``tests/ML/test_ml_mimic_hf.py`` call). NOTE: the ``/etl/concepts`` handler writes
    the blob to a CSV via ``str(dict)`` (Python repr, single quotes) and the engine
    later round-trips it with ``.replace("'", '"')`` — so every blob VALUE must be
    apostrophe-free. All values here (paths, ISO dates, set names, numbers) satisfy that.
    """
    ph = config["phenotypes"][phenotype]
    defaults = config["ml_blob_defaults"]
    blob = dict(defaults)  # copy data_paths/time_buffer/sample_size_limit/seed/period
    blob.update(
        {
            "positive_patient_set": [f"{phenotype}_pos"],
            "negative_patient_set": [f"{phenotype}_neg"],
            "label_paths": [ph["label_path"]],
        }
    )
    return blob


def _session(user: str, password: str, project: str):
    try:
        import requests  # noqa: WPS433 (lazy import for a clear error if missing)
        from requests.auth import HTTPBasicAuth
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "The 'requests' package is required to drive the API. "
            "Install it (pip install requests) or run inside the container."
        ) from exc
    s = requests.Session()
    s.auth = HTTPBasicAuth(user, password)
    s.headers.update({"X-Project-Name": project, "Content-Type": "application/json",
                      "accept": "application/json"})
    return s


def register_concept(session, base_url: str, phenotype: str, config: dict) -> dict:
    """POST /etl/concepts to register the derived ML concept with its blob."""
    ph = config["phenotypes"][phenotype]
    payload = {
        "code": ph["ml_concept_code"],
        "path": ph["ml_concept_path"],
        "type": "assertion",
        "description": ph.get("description", phenotype),
        "blob": build_blob(phenotype, config),
    }
    resp = session.post(f"{base_url}/etl/concepts", data=json.dumps(payload), timeout=60)
    return {"status_code": resp.status_code, "body": resp.text, "payload": payload}


def post_build_job(session, base_url: str, phenotype: str, config: dict) -> dict:
    """POST /etl/job to enqueue the async ml build."""
    ph = config["phenotypes"][phenotype]
    payload = {"input": {"path": ph["ml_concept_path"]}, "jobType": "ml"}
    resp = session.post(f"{base_url}/etl/job", data=json.dumps(payload), timeout=60)
    return {"status_code": resp.status_code, "body": resp.text, "payload": payload}


def _jobs_list(session, base_url: str) -> list[dict]:
    resp = session.get(f"{base_url}/etl/job", timeout=60)
    try:
        data = json.loads(resp.text)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else [data]


def _find_latest_job(jobs: list[dict], ml_concept_path: str) -> dict | None:
    """Pick the most recent ml job whose input path matches our concept path."""
    def jid(j):
        return j.get("id") or j.get("job_id") or j.get("ID") or 0

    candidates = []
    for j in jobs:
        jtype = str(j.get("job_type") or j.get("jobType") or "")
        blob = json.dumps(j).lower()
        if jtype.lower().startswith("ml") and ml_concept_path.lower() in blob:
            candidates.append(j)
    pool = candidates or [j for j in jobs if str(j.get("job_type", "")).lower().startswith("ml")]
    return max(pool, key=jid) if pool else None


def poll_job(session, base_url: str, ml_concept_path: str, timeout_s: int = 1800,
             interval_s: int = 5) -> dict:
    """Poll /etl/job until the matching ml job reaches a terminal status."""
    terminal = {"COMPLETED", "ERROR", "FAILED"}
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        job = _find_latest_job(_jobs_list(session, base_url), ml_concept_path)
        if job is not None:
            last = job
            status = str(job.get("status", "")).upper()
            print(f"  job status: {status or '(unknown)'}")
            if status in terminal:
                return {"terminal": True, "status": status, "job": job}
        time.sleep(interval_s)
    return {"terminal": False, "status": "TIMEOUT", "job": last}


def retrieve_model(session, base_url: str, phenotype: str, config: dict) -> dict:
    """GET /etl/concepts and extract the trained model + metrics from concept_blob."""
    ph = config["phenotypes"][phenotype]
    resp = session.get(
        f"{base_url}/etl/concepts",
        params={"hpath": ph["ml_concept_path"]},
        timeout=60,
    )
    out = {"status_code": resp.status_code, "raw": resp.text}
    try:
        rows = json.loads(resp.text)
        row = rows[0] if isinstance(rows, list) and rows else rows
        blob = row.get("concept_blob") if isinstance(row, dict) else None
        if isinstance(blob, str):
            blob = json.loads(blob)
        if isinstance(blob, dict):
            out["has_serialized_model"] = "serialized_model" in blob
            out["metrics"] = {
                k: blob[k] for k in (
                    "roc_auc", "test_roc_auc", "accuracy", "precision", "recall",
                    "f1", "build_time_sec", "feature_column_codes",
                ) if k in blob
            }
    except (json.JSONDecodeError, KeyError, TypeError, IndexError) as exc:
        out["parse_error"] = str(exc)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phenotype", help="Phenotype key from phenotypes.yaml")
    parser.add_argument("--base-url", default="http://localhost:5005")
    parser.add_argument("--user", default=r"demo\demo")
    parser.add_argument("--password", default="Etl@2021")
    parser.add_argument("--project", default="Demo")
    parser.add_argument("--poll-timeout", type=int, default=1800)
    parser.add_argument("--skip-poll", action="store_true", help="POST only; don't wait")
    args = parser.parse_args(argv)

    config = load_config()
    if args.phenotype not in config["phenotypes"]:
        parser.error(f"unknown phenotype '{args.phenotype}'")
    ml_path = config["phenotypes"][args.phenotype]["ml_concept_path"]
    session = _session(args.user, args.password, args.project)

    print(f"[1/4] Registering ML concept {ml_path} ...")
    reg = register_concept(session, args.base_url, args.phenotype, config)
    print(f"      -> {reg['status_code']}: {reg['body'][:200]}")

    print("[2/4] Posting ml build job ...")
    job = post_build_job(session, args.base_url, args.phenotype, config)
    print(f"      -> {job['status_code']}: {job['body'][:200]}")

    if args.skip_poll:
        print("[3/4] --skip-poll set; not waiting. Check /etl/job manually.")
        return 0

    print("[3/4] Polling job status ...")
    result = poll_job(session, args.base_url, ml_path, timeout_s=args.poll_timeout)
    print(f"      -> terminal={result['terminal']} status={result['status']}")

    print("[4/4] Retrieving model from concept_blob ...")
    model = retrieve_model(session, args.base_url, args.phenotype, config)
    print(f"      -> status={model['status_code']} "
          f"has_model={model.get('has_serialized_model')} metrics={model.get('metrics')}")
    return 0 if result.get("status") == "COMPLETED" else 1


if __name__ == "__main__":
    sys.exit(main())
