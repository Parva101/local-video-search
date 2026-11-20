from dataclasses import replace

import pytest

from video_search import analysis
from video_search.config import Settings
from video_search.vlm import DEFAULT_SPEC, GEMMA_SPEC, VLMError


def test_provider_spec_is_explicit_and_does_not_require_endpoint(tmp_path):
    qwen = Settings("unused", tmp_path)
    gemma = replace(qwen, vision_provider="gemma")
    assert analysis.description_spec() == analysis.description_spec(qwen)
    assert analysis.description_spec(qwen)["model_id"] == DEFAULT_SPEC["model_id"]
    assert analysis.description_spec(gemma)["model_id"] == GEMMA_SPEC["model_id"]
    assert analysis.description_spec(gemma)["revision"] == "hosted-unpinned"
    assert analysis.description_spec(gemma) != analysis.description_spec(qwen)
    with pytest.raises(VLMError):
        analysis.client(gemma)


def test_hosted_and_upload_settings_from_env(tmp_path):
    # Pass an isolated environment without mutating the test process environment.
    import os
    import subprocess
    import sys

    environment = {**os.environ, "DATABASE_URL": "unused", "MEDIA_ROOT": str(tmp_path),
                   "VISION_PROVIDER": "gemma", "VOYAGER_API_KEY": "test-key",
                   "VOYAGER_BASE_URL": "http://127.0.0.1:1/v1", "UPLOAD_WRITE_ROOT": str(tmp_path),
                   "UPLOAD_READ_ROOT": str(tmp_path),
                   "UPLOAD_MAX_BYTES": "2048"}
    subprocess.run([sys.executable, "-c",
                    "from video_search.config import Settings; from video_search import analysis; "
                    "s=Settings.from_env(); assert s.vision_provider=='gemma'; "
                    "assert s.voyager_api_key=='test-key'; assert s.upload_max_bytes==2048; "
                    "assert s.upload_write_root==s.media_root; "
                    "assert s.upload_read_root==s.media_root; "
                    "c=analysis.client(s); assert c.timeout==600; "
                    "assert c.endpoint=='http://127.0.0.1:1/v1/chat/completions'"],
                   env=environment, check=True, capture_output=True, timeout=15)


def test_invalid_provider_and_upload_limit_fail(tmp_path):
    with pytest.raises(ValueError, match="VISION_PROVIDER"):
        Settings("unused", tmp_path, vision_provider="auto")
    with pytest.raises(ValueError, match="UPLOAD_MAX_BYTES"):
        Settings("unused", tmp_path, upload_max_bytes=0)
