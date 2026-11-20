"""Run a private, bounded Charades pilot through the project pipeline."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from video_search.benchmark_run import main


if __name__ == "__main__":
    main()
