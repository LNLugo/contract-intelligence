"""Answering path. Slice 1 (ADR-0019): retrieve -> generate -> validate citations -> route.

Shares identity, retries and settings with the ingestion pipeline (one credential, one
retry policy), so this package imports from ingestion/pipeline."""
import sys
from pathlib import Path

_ingestion = Path(__file__).resolve().parent.parent / "ingestion"
if str(_ingestion) not in sys.path:
    sys.path.insert(0, str(_ingestion))
