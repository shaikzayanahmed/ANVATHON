"""Load the fabricated corpus into a separate SQLite database for UI testing."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "mock_benchsplit.db"
SCHEMA_PATH = ROOT.parent / "backend" / "schema.sql"
JSONL_PATH = ROOT / "data" / "processed" / "benchsplit_dataset.jsonl"


def main() -> None:
    records = [json.loads(line) for line in JSONL_PATH.read_text(encoding="utf-8").splitlines()]
    expected = json.loads((ROOT / "expected_conflicts.json").read_text(encoding="utf-8"))
    connection = sqlite3.connect(DB_PATH)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    for table in ("gold_pairs", "pair_labels", "cluster_members", "clusters", "propositions", "judgments", "courts"):
        connection.execute(f"DELETE FROM {table}")

    courts = {
        record["court_id"]: (record["court_id"], record["court"], record["court_id"].replace("_", " "), record["level"] if "level" in record else ("SC" if record["court_id"] == "SCI" else "HC"))
        for record in records
    }
    connection.executemany("INSERT INTO courts (id, name, short_code, level) VALUES (?, ?, ?, ?)", courts.values())

    proposition_ids = {}
    for record in records:
        judgment_id = f"FAKE-J-{record['document_id']}"
        proposition_id = f"FAKE-P-{record['document_id']}"
        proposition_ids[record["document_id"]] = proposition_id
        text_path = ROOT / "data" / "extracted_text" / f"{record['document_id']}.txt"
        text = text_path.read_text(encoding="utf-8")
        connection.execute(
            """INSERT INTO judgments
               (id, court_id, cnr, title, decision_date, s3_uri, local_pdf_path,
                pdf_sha256, has_text_layer, n_pages)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1)""",
            (
                judgment_id,
                record["court_id"],
                record["case_number"],
                record["title"] if "title" in record else record["case_number"],
                record["decision_date"],
                record["source_uri"],
                str(text_path),
                hashlib.sha256(text.encode("utf-8")).hexdigest(),
            ),
        )
        quote = record["decision_evidence"]
        connection.execute(
            """INSERT INTO propositions
               (id, judgment_id, statute_key, question, holding, quote, page,
                char_start, char_end, verify_status, verify_score, retry_count,
                entailment_supported, model_name, prompt_version)
               VALUES (?, ?, 'NI_ACT_S138', ?, ?, ?, 1, ?, ?, 'VERIFIED_EXACT',
                       100.0, 0, 1, 'fake-test-fixture', 'fake-v1')""",
            (
                proposition_id,
                judgment_id,
                record["question"],
                record["holding"],
                quote,
                text.index(quote),
                text.index(quote) + len(quote),
            ),
        )

    cluster_id = "FAKE-CLUSTER-NI-ACT-S138"
    connection.execute(
        "INSERT INTO clusters (id, statute_key, canonical_question, method, threshold) VALUES (?, ?, ?, ?, ?)",
        (cluster_id, "NI_ACT_S138", "Does dispatch alone satisfy Section 138 notice service?", "fake_expected_fixture", 1.0),
    )
    for proposition_id in proposition_ids.values():
        connection.execute("INSERT INTO cluster_members (cluster_id, proposition_id) VALUES (?, ?)", (cluster_id, proposition_id))

    for index, pair in enumerate(expected, start=1):
        connection.execute(
            """INSERT INTO pair_labels
               (id, statute_key, cluster_id, prop_a_id, prop_b_id, candidate_score,
                label, reason, votes_json, confidence, sc_status, sc_prop_id)
               VALUES (?, ?, ?, ?, ?, ?, 'CONFLICT', ?, ?, ?, ?, ?)""",
            (
                f"FAKE-LABEL-{index}",
                pair["statute_key"],
                cluster_id,
                proposition_ids[pair["prop_a"]],
                proposition_ids[pair["prop_b"]],
                1.0,
                pair["reason"],
                json.dumps(["CONFLICT", "CONFLICT", "CONFLICT"]),
                1.0,
                "FAKE_TEST_DATA",
                proposition_ids[pair["prop_b"]] if pair["prop_b"].startswith("FAKE-SC") else None,
            ),
        )
    connection.commit()
    connection.close()
    print(f"Loaded {len(records)} fabricated records into {DB_PATH}")
    print(f"Inserted {len(expected)} fabricated CONFLICT labels")


if __name__ == "__main__":
    main()
