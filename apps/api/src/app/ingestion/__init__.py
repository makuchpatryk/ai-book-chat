"""PDF ingestion: extract -> detect sections -> chunk -> embed -> persist.

Everything except `pipeline` is pure (no database, no network), so the bulk of
the logic is unit-testable without infrastructure.
"""
