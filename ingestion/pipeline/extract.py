"""Document Intelligence prebuilt-layout: submit, then poll (the async pattern).
The result JSON is cached in ADLS so re-chunking never pays for extraction again (ADR-0004, ADR-0015)."""
import base64
import json
import time

from azure.storage.filedatalake import DataLakeServiceClient

from . import http
from .config import SETTINGS as S

_lake = DataLakeServiceClient(S.dfs_endpoint, credential=http._credential)


def extraction_path(doc_id: str) -> str:
    return f"{doc_id}/{S.extraction_version}.json"


def load_cached(doc_id: str) -> dict | None:
    f = _lake.get_file_client(S.extracted_fs, extraction_path(doc_id))
    if not f.exists():
        return None
    return json.loads(f.download_file().readall())


def save_raw(doc_id: str, pdf: bytes, original_name: str) -> str:
    path = f"eval/{doc_id}.pdf"
    f = _lake.get_file_client(S.raw_fs, path)
    f.upload_data(pdf, overwrite=True, metadata={"original_name": _ascii(original_name)})
    return path


def analyze(pdf: bytes, poll_seconds: float = 2.0, timeout_seconds: float = 600) -> dict:
    """Submit the PDF bytes, then poll the operation until it finishes. Returns analyzeResult."""
    url = (f"{S.di_endpoint}/documentintelligence/documentModels/prebuilt-layout:analyze"
           f"?api-version={S.layout_api}")
    submit = http.request("POST", url, http.COGNITIVE_SCOPE, retry_404=False,
                          json={"base64Source": base64.b64encode(pdf).decode()})
    op_url = submit.headers["Operation-Location"]
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        time.sleep(poll_seconds)
        result = http.request("GET", op_url, http.COGNITIVE_SCOPE, retry_404=False).json()
        if result["status"] == "succeeded":
            return result["analyzeResult"]
        if result["status"] not in ("notStarted", "running"):
            raise RuntimeError(f"Extraction failed: {json.dumps(result.get('error'))[:500]}")
    raise TimeoutError(f"Extraction did not finish in {timeout_seconds} s")


def extract(doc_id: str, pdf: bytes, original_name: str) -> tuple[dict, bool]:
    """Return (analyzeResult, was_cached). Pays for extraction only on a cache miss."""
    cached = load_cached(doc_id)
    if cached is not None:
        return cached, True
    save_raw(doc_id, pdf, original_name)
    result = analyze(pdf)
    _lake.get_file_client(S.extracted_fs, extraction_path(doc_id)).upload_data(
        json.dumps(result).encode(), overwrite=True)
    return result, False


def _ascii(s: str) -> str:
    return s.encode("ascii", "ignore").decode()[:250]
