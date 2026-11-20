import os
from pathlib import Path
import subprocess
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo, conninfo_to_dict
import pytest

from video_search import store


@pytest.fixture
def database_url():
    base = os.environ.get("TEST_DATABASE_URL")
    if not base:
        pytest.skip("Set TEST_DATABASE_URL to a dedicated test database; Compose provides one")
    if conninfo_to_dict(base).get("dbname") != "test":
        raise RuntimeError("Integration tests require a database named test")
    schema = "test_" + uuid4().hex
    with psycopg.connect(base) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    url = make_conninfo(base, options=f"-csearch_path={schema},public")
    store.init_db(url)
    try:
        yield url
    finally:
        with psycopg.connect(base) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


@pytest.fixture
def video_file(tmp_path: Path):
    path = tmp_path / "sample.mp4"
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=64x64:r=10:d=2",
        "-c:v", "mpeg4", "-y", str(path),
    ], check=True, capture_output=True, timeout=30)
    return path
