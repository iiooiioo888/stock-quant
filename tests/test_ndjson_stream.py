"""NDJSON 流式工具測試"""
import pytest

from src.api.ndjson import iter_ndjson_lines, ndjson_stream


@pytest.mark.asyncio
async def test_ndjson_stream_chunks():
    rows = [{"i": i} for i in range(5)]
    parts = []
    async for line in ndjson_stream(rows, chunk_size=2):
        parts.append(line)
    assert len(parts) == 3
    parsed = list(iter_ndjson_lines("".join(parts)))
    flat = [item for chunk in parsed for item in chunk]
    assert flat == rows
