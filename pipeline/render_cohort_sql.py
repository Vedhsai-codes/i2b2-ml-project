"""Render the phenotype-agnostic cohort SQL template into a runnable per-phenotype query.

Reads ``pipeline/config/phenotypes.yaml`` and ``sql/cohort_template.sql``, substitutes
the ``@@PLACEHOLDER@@`` tokens for the requested phenotype, and writes
``sql/cohort_<phenotype>.sql``.

Usage:
    python pipeline/render_cohort_sql.py stroke
    python pipeline/render_cohort_sql.py --all
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "pipeline" / "config" / "phenotypes.yaml"
TEMPLATE_PATH = REPO_ROOT / "sql" / "cohort_template.sql"
SQL_DIR = REPO_ROOT / "sql"


def load_config(path: Path = CONFIG_PATH) -> dict:
    """Load and return the phenotypes config."""
    with path.open() as fh:
        return yaml.safe_load(fh)


def _icd_predicate(icd: dict, *, alias: str = "d") -> str:
    """Build an ``(icd_version/icd_code LIKE ...)`` SQL predicate from an icd dict.

    Args:
        icd: mapping with optional ``icd10`` / ``icd9`` lists of code prefixes.
        alias: table alias for the diagnoses rows (default ``d``).

    Returns:
        A parenthesised SQL boolean expression. ``(1=0)`` if no codes given.
    """
    clauses: list[str] = []
    for version, key in ((10, "icd10"), (9, "icd9")):
        prefixes = icd.get(key) or []
        if not prefixes:
            continue
        likes = " OR ".join(f"{alias}.icd_code LIKE '{p}%'" for p in prefixes)
        clauses.append(f"({alias}.icd_version = {version} AND ({likes}))")
    if not clauses:
        return "(1 = 0)"
    return "(" + " OR ".join(clauses) + ")"


def render(phenotype: str, config: dict | None = None) -> str:
    """Return the rendered SQL string for ``phenotype``."""
    config = config or load_config()
    phenos = config["phenotypes"]
    if phenotype not in phenos:
        raise KeyError(
            f"Unknown phenotype '{phenotype}'. Known: {sorted(phenos)}"
        )
    ph = phenos[phenotype]
    cohort = ph["cohort"]
    max_positives = int(cohort["max_positives"])
    max_controls = max_positives * int(cohort["neg_per_pos"])

    template = TEMPLATE_PATH.read_text()
    substitutions = {
        "@@PHENOTYPE@@": phenotype,
        "@@LABEL_HUMAN@@": ph.get("description", phenotype),
        "@@LABEL_PREDICATE@@": _icd_predicate(ph["label_icd"]),
        "@@NEG_EXCLUDE_PREDICATE@@": _icd_predicate(ph["negative_exclude_icd"]),
        "@@MAX_POSITIVES@@": str(max_positives),
        "@@MAX_CONTROLS@@": str(max_controls),
    }
    rendered = template
    for token, value in substitutions.items():
        rendered = rendered.replace(token, value)

    leftover = [t for t in substitutions if t in rendered]
    if "@@" in rendered:
        raise ValueError(f"Unsubstituted placeholders remain (e.g. {leftover}).")
    return rendered


def write(phenotype: str, config: dict | None = None) -> Path:
    """Render ``phenotype`` and write ``sql/cohort_<phenotype>.sql``."""
    rendered = render(phenotype, config)
    out_path = SQL_DIR / f"cohort_{phenotype}.sql"
    out_path.write_text(rendered)
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phenotype", nargs="?", help="Phenotype key from phenotypes.yaml")
    parser.add_argument("--all", action="store_true", help="Render every phenotype")
    args = parser.parse_args(argv)

    config = load_config()
    if args.all:
        targets = list(config["phenotypes"])
    elif args.phenotype:
        targets = [args.phenotype]
    else:
        parser.error("provide a phenotype name or --all")

    for name in targets:
        path = write(name, config)
        print(f"rendered {name} -> {path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
