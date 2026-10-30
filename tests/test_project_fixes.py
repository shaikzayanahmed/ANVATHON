import hashlib
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.adjudicator import _majority_vote
from backend.main import _source_uri
from backend.s3_ingest import download_public_s3_object


class ProjectFixTests(unittest.TestCase):
    def test_groq_request_uses_configured_bearer_token(self) -> None:
        import backend.llm_client as llm_client

        response = Mock()
        response.json.return_value = {
            "choices": [{"message": {"content": '{"ok": true}'}}]
        }
        with (
            patch.object(llm_client, "GROQ_API_KEY", "test-token"),
            patch.object(llm_client.httpx, "post", return_value=response) as post,
        ):
            content = llm_client._request_groq("test prompt")

        self.assertEqual(content, '{"ok": true}')
        self.assertEqual(
            post.call_args.kwargs["headers"]["Authorization"],
            "Bearer test-token",
        )

    def test_majority_reason_comes_from_winning_label(self) -> None:
        label, reason, confidence = _majority_vote(
            [
                ("CONFLICT", "The first vote found a conflict."),
                ("AGREE", "The majority found agreement."),
                ("AGREE", "The second agreement vote."),
            ]
        )

        self.assertEqual(label, "AGREE")
        self.assertEqual(reason, "The majority found agreement.")
        self.assertAlmostEqual(confidence, 2 / 3)

    def test_public_s3_download_hashes_in_chunks(self) -> None:
        payload = b"judgment-content" * 100
        client = Mock()

        def download_file(_bucket: str, _key: str, destination: str) -> None:
            Path(destination).write_bytes(payload)

        client.download_file.side_effect = download_file
        with tempfile.TemporaryDirectory() as directory:
            with patch("boto3.client", return_value=client):
                path, digest = download_public_s3_object(
                    "public-bucket", "judgment.pdf", Path(directory) / "judgment.pdf"
                )

            self.assertEqual(path.read_bytes(), payload)
            self.assertEqual(digest, hashlib.sha256(payload).hexdigest())

    def test_local_documents_are_not_presented_as_s3_sources(self) -> None:
        self.assertEqual(
            _source_uri("J-DLHC-NI_ACT_S138", "DEMO123", "s3://fake", "raw/demo.pdf"),
            "demo://synthetic/demo.pdf",
        )
        self.assertEqual(
            _source_uri("random-id", "UPLOAD123", "s3://fake", "inbox/upload.pdf"),
            "local://inbox/upload.pdf",
        )
        self.assertEqual(
            _source_uri("external-id", "CNR123", "s3://real/source.pdf", "raw/source.pdf"),
            "s3://real/source.pdf",
        )

    def test_upload_without_court_is_not_attributed_to_delhi(self) -> None:
        import backend.main as main

        with tempfile.TemporaryDirectory() as directory:
            pdf_path = Path(directory) / "upload.pdf"
            pdf_path.write_bytes(b"%PDF-test")
            connection = sqlite3.connect(":memory:")
            connection.row_factory = sqlite3.Row
            connection.executescript(
                """
                CREATE TABLE courts (
                    id TEXT PRIMARY KEY, name TEXT, short_code TEXT, level TEXT
                );
                CREATE TABLE judgments (
                    id TEXT PRIMARY KEY, court_id TEXT, cnr TEXT, title TEXT,
                    decision_date TEXT, s3_uri TEXT, local_pdf_path TEXT,
                    pdf_sha256 TEXT, has_text_layer INTEGER, n_pages INTEGER
                );
                """
            )

            @contextmanager
            def database_connection():
                yield connection
                connection.commit()

            passage = SimpleNamespace(
                statute_key="NI_ACT_S138",
                page_num=1,
                text="A selected statutory passage.",
                page_char_offset=0,
                page_text="A selected statutory passage.",
            )
            run_events = []
            with (
                patch.object(main, "db_connection", database_connection),
                patch.object(main, "extract_pdf_pages", return_value=["A selected statutory passage."]),
                patch.object(main, "select_passages", return_value=[passage]),
                patch.object(main, "append_run_event", side_effect=lambda *args: run_events.append(args)),
                patch.object(main, "run_extraction", return_value={"final_status": "ACCEPTED"}),
                patch.object(main, "sha256_file", return_value="sha256"),
                patch.object(main, "finish_run") as finish_run,
            ):
                main._ingest_pdf(pdf_path, "upload.pdf", "run-id")

            judgment = connection.execute(
                "SELECT court_id, s3_uri FROM judgments"
            ).fetchone()
            court = connection.execute("SELECT name FROM courts WHERE id='UPLOAD'").fetchone()
            self.assertEqual(judgment["court_id"], "UPLOAD")
            self.assertEqual(judgment["s3_uri"], "local://inbox/upload.pdf")
            self.assertEqual(court["name"], "Uploaded judgment (court unverified)")
            self.assertTrue(any(event[2] == "skipped" for event in run_events))
            finish_run.assert_called_once()
            connection.close()


if __name__ == "__main__":
    unittest.main()
