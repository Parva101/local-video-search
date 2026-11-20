from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath, PureWindowsPath


@dataclass(frozen=True)
class Settings:
    database_url: str
    media_root: Path
    library_id: str | None = None
    model_cache: Path = Path("/models")
    qwen_base_url: str | None = None
    qwen_api_key: str | None = None
    vision_provider: str = "qwen"
    voyager_api_key: str | None = None
    voyager_base_url: str = "https://openai.rc.asu.edu/v1"
    upload_write_root: Path | None = None
    upload_read_root: Path | None = None
    upload_max_bytes: int = 2 * 1024**3

    def __post_init__(self):
        if self.vision_provider not in {"qwen", "gemma"}:
            raise ValueError("VISION_PROVIDER must be qwen or gemma")
        if self.upload_max_bytes <= 0:
            raise ValueError("UPLOAD_MAX_BYTES must be positive")
        if self.library_id is not None and not (
            PurePosixPath(self.library_id).is_absolute() or PureWindowsPath(self.library_id).is_absolute()
        ):
            raise ValueError("LIBRARY_ID must be the absolute host video directory, matching VIDEO_DIRECTORY")

    @property
    def library_identity(self) -> str:
        return self.library_id or str(self.media_root)

    @classmethod
    def from_env(cls) -> "Settings":
        # No implicit database target: a bad configuration must fail at startup.
        return cls(
            database_url=os.environ["DATABASE_URL"],
            media_root=Path(os.environ["MEDIA_ROOT"]).resolve(strict=True),
            library_id=os.environ.get("LIBRARY_ID"),
            model_cache=Path(os.environ.get("MODEL_CACHE", "/models")),
            qwen_base_url=os.environ.get("QWEN_BASE_URL") or None,
            qwen_api_key=os.environ.get("QWEN_API_KEY") or None,
            vision_provider=os.environ.get("VISION_PROVIDER", "qwen"),
            voyager_api_key=os.environ.get("VOYAGER_API_KEY") or None,
            voyager_base_url=os.environ.get("VOYAGER_BASE_URL", "https://openai.rc.asu.edu/v1"),
            upload_write_root=(Path(os.environ["UPLOAD_WRITE_ROOT"]).resolve(strict=True)
                               if os.environ.get("UPLOAD_WRITE_ROOT") else None),
            upload_read_root=(Path(os.environ["UPLOAD_READ_ROOT"]).resolve(strict=True)
                              if os.environ.get("UPLOAD_READ_ROOT") else None),
            upload_max_bytes=int(os.environ.get("UPLOAD_MAX_BYTES", str(2 * 1024**3))),
        )

