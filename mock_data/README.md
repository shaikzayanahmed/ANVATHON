# FAKE TEST DATA ONLY

This folder is a completely fabricated test corpus. It is not sourced from any
court, is not legal authority, and must never be presented as real case law.

It contains mock judgments for:

- Bombay High Court
- Delhi High Court
- Karnataka High Court (Bengaluru)
- Supreme Court of India

The records intentionally contain opposing holdings for the same fictional
Section 138 question so the Conflict Radar can be tested. Every record uses a
`fake://FAKE_TEST_DATA/` source URI.

Generate or regenerate the files with:

```powershell
.\.venv\Scripts\python.exe mock_data\generate_mock_dataset.py
```

Generated files:

- `data/processed/benchsplit_dataset.jsonl`
- `data/processed/benchsplit_dataset.csv`
- `data/metadata/*.json`
- `data/extracted_text/*.txt`
- `expected_conflicts.json`

The mock corpus is intentionally separate from `database_real_github` and is
not loaded by backend startup.

To create a combined UI test database containing the untouched real database
plus fake fixture records compared against Patna propositions:

```powershell
.\.venv\Scripts\python.exe mock_data\create_mixed_test_database.py
```

This creates `mixed_real_fake_test.db`. Its four inserted relationship labels
are explicitly fixture labels: one `CONFLICT`, two `AGREE`, and one
`DISTINGUISHABLE_ON_FACTS`. They test rendering and navigation only; they do not
assert that the real Patna records legally agree or conflict with fabricated
holdings.
