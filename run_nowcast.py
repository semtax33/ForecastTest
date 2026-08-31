from __future__ import annotations

import argparse
from pathlib import Path

from energy_nowcast.benchmark import verify_frozen_benchmark
from energy_nowcast.config import ProjectPaths, load_config
from energy_nowcast.output.report import build_report
from energy_nowcast.pipeline import run_pipeline, write_pipeline_result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the modular energy revenue nowcast")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/v3_3_1.json"),
        help="Versioned model configuration",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (default: output/v<version>)",
    )
    parser.add_argument(
        "--verify-benchmark-only",
        action="store_true",
        help="Verify frozen V3.3 artifacts and exit",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = ProjectPaths()
    manifest = verify_frozen_benchmark(paths)
    if args.verify_benchmark_only:
        print(f"Verified: {manifest['name']} ({manifest['git_commit']})")
        return 0
    config = load_config(args.config)
    output_dir = (args.output_dir or paths.output / f"v{config.version.replace('.', '_')}").resolve()
    result = run_pipeline(config, paths)
    written = write_pipeline_result(result, output_dir)
    written.append(build_report(result, output_dir))
    print(f"V{config.version} complete: {output_dir}")
    print(f"Wrote {len(written)} artifacts")
    print(result.metrics.round(3).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
