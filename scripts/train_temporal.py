"""Run isolated feature-based temporal-grounding experiments on an allocated Sol GPU."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from video_search.temporal_training import main


if __name__ == "__main__":
    main()
