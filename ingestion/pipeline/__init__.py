"""Contract ingestion pipeline: extract, clean, chunk, embed, index.

One library, two callers (ADR-0017): the batch script on a laptop and the
Event Grid triggered Azure Function. Neither caller holds pipeline logic.
"""
