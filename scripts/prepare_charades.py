"""Download only the frozen Charades-STA pilot into private local storage."""

import argparse
import json
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from video_search.benchmark_data import DataError, prepare
from video_search.log import configure_logging


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="Private data directory; never commit its media or labels")
    args = parser.parse_args()
    configure_logging()
    try:
        result = prepare(args.output)
    except DataError as exc:
        logging.getLogger("video_search").error("benchmark_preparation_failed", extra={"fields": {
            "message": str(exc), "details": exc.details,
        }})
        raise
    print(json.dumps(result))


if __name__ == "__main__":
    main()
