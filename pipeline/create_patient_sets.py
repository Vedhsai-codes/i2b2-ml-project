"""Create named i2b2 patient sets (positive / negative) for a phenotype cohort.

The live ``jobType: "ml"`` engine reads cohort membership from the i2b2
``qt_patient_set_collection`` table, resolving a set by NAME through
``qt_query_result_instance.description = 'Patient Set for "<name>"'`` (see
``i2b2_cdi/utils/patient_set.py``). This module materialises two such sets from the
membership CSV produced by ``build_cohort.py``:

    <phenotype>_pos   patient_num in (label == 1)
    <phenotype>_neg   patient_num in (label == 0)

These names go straight into the ML concept blob (``positive_patient_set`` /
``negative_patient_set``).

IMPORTANT: run this INSIDE the i2b2-etl/i2b2-ml container (it needs ``i2b2_cdi`` and a
live CRC DB connection). Facts must be loaded with ``--mrn-are-patient-numbers`` first
so ``patient_num == subject_id``. Mirrors ``tests/ML/test_helper.py:create_patient_set``
but takes an explicit patient_num list instead of a SQL query.

Usage (in container):
    python pipeline/create_patient_sets.py stroke \
        --membership /usr/src/app/pipeline/out/stroke_membership.csv
"""

from __future__ import annotations

import argparse
import csv
import datetime
import sys
from pathlib import Path

_REQUEST_XML = """
<query_definition>
    <query_name>{query_name}</query_name>
    <query_timing>ANY</query_timing>
    <panel>
        <panel_number>1</panel_number>
        <invert>0</invert>
        <panel_timing>ANY</panel_timing>
        <total_item_occurrences>1</total_item_occurrences>
        <item>
            <item_name>{query_name}</item_name>
            <tooltip>{query_name}</tooltip>
            <class>ENC</class>
            <operator>EQ</operator>
        </item>
    </panel>
</query_definition>
"""


def create_named_patient_set(
    query_name: str,
    patient_nums: list[int],
    project_id: str = "demo",
    user_id: str = "demo",
) -> int:
    """Create one named i2b2 patient set from an explicit patient_num list.

    Returns the result_instance_id. Commits on success.
    """
    from i2b2_cdi.config.config import Config
    from i2b2_cdi.database.cdi_database_connections import I2b2crcDataSource
    from loguru import logger

    config = Config().new_config(argv=["project", "add"])
    timestamp = datetime.datetime.now()
    request_xml = _REQUEST_XML.format(query_name=query_name)

    with I2b2crcDataSource(config) as cursor:
        cursor.execute(
            """
            INSERT INTO QT_QUERY_MASTER (name, user_id, group_id, create_date, delete_flag, request_xml)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING query_master_id
            """,
            (query_name, user_id, project_id, timestamp, "N", request_xml),
        )
        query_master_id = cursor.fetchone()[0]

        cursor.execute(
            """
            INSERT INTO QT_QUERY_INSTANCE (query_master_id, user_id, group_id, start_date, end_date, status_type_id)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING query_instance_id
            """,
            (query_master_id, user_id, project_id, timestamp, timestamp, 3),
        )
        query_instance_id = cursor.fetchone()[0]

        cursor.execute(
            """
            INSERT INTO QT_QUERY_RESULT_INSTANCE
                (query_instance_id, result_type_id, set_size, start_date, end_date, status_type_id, description)
            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING result_instance_id
            """,
            (
                query_instance_id,
                1,                      # result_type_id = patient set
                len(patient_nums),
                timestamp,
                timestamp,
                3,                      # status_type_id = Finished
                f'Patient Set for "{query_name}"',
            ),
        )
        result_instance_id = cursor.fetchone()[0]

        for pnum in patient_nums:
            cursor.execute(
                "INSERT INTO QT_PATIENT_SET_COLLECTION (result_instance_id, patient_num) VALUES (%s, %s)",
                (result_instance_id, int(pnum)),
            )
        cursor.connection.commit()
        logger.info(
            "Created patient set '{}' (result_instance_id={}) with {} patients",
            query_name, result_instance_id, len(patient_nums),
        )
    return result_instance_id


def _read_membership(path: Path) -> tuple[list[int], list[int]]:
    """Return (positive_patient_nums, negative_patient_nums) from a membership CSV."""
    pos, neg = [], []
    with path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            pnum = int(r["subject_id"])
            (pos if int(r["label"]) == 1 else neg).append(pnum)
    return pos, neg


def create_for_phenotype(phenotype: str, membership_csv: Path) -> dict:
    """Create <phenotype>_pos and <phenotype>_neg sets from the membership CSV."""
    pos, neg = _read_membership(membership_csv)
    if not pos:
        raise ValueError("no positive patients in membership CSV")
    if not neg:
        raise ValueError("no negative patients in membership CSV")
    pos_name = f"{phenotype}_pos"
    neg_name = f"{phenotype}_neg"
    pos_id = create_named_patient_set(pos_name, pos)
    neg_id = create_named_patient_set(neg_name, neg)
    return {
        "positive_patient_set": pos_name,
        "negative_patient_set": neg_name,
        "positive_result_instance_id": pos_id,
        "negative_result_instance_id": neg_id,
        "n_positive": len(pos),
        "n_negative": len(neg),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phenotype", help="Phenotype key (used to name the sets)")
    parser.add_argument("--membership", required=True, type=Path, help="membership CSV path")
    args = parser.parse_args(argv)

    result = create_for_phenotype(args.phenotype, args.membership)
    print("Created patient sets:")
    for k, v in result.items():
        print(f"  {k}: {v}")
    print(
        "\nReference these names in the ML concept blob:\n"
        f'  "positive_patient_set": ["{result["positive_patient_set"]}"],\n'
        f'  "negative_patient_set": ["{result["negative_patient_set"]}"]'
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
