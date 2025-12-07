import pathlib
import json
import pytest
from processor import validate_pdf

PDF_DIR = pathlib.Path(__file__).parent / "examples"
SNAPSHOT_DIR = pathlib.Path(__file__).parent / "snapshots"
SNAPSHOT_DIR.mkdir(exist_ok=True)

def normalize_rule_error(err):
    return {
        "message": err.message,
        "node_id": err.node_id,
        "error_type": str(err.error_type),
        "expected": err.expected,
        "found": err.found,
        "node": err.node.__class__.__name__,
    }

pdf_files = list(PDF_DIR.glob("*.pdf"))
pdf_ids = [p.stem for p in pdf_files]

@pytest.mark.parametrize("pdf_path", pdf_files, ids=pdf_ids)
def test_pdf_validation_snapshot(snapshot, pdf_path):
    data = pdf_path.read_bytes()
    result = validate_pdf(data)

    normalized = [normalize_rule_error(err) for err in result]
    normalized_json = json.dumps(normalized, indent=2, ensure_ascii=False)

    snapshot.assert_match(
        normalized_json,
        snapshot_name=f"{pdf_path.stem}.snapshot",
    )
