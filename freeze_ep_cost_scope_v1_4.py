from pathlib import Path

from energy_nowcast.research.ep_v14.benchmark import freeze_v14


ROOT = Path(__file__).resolve().parent


if __name__ == "__main__":
    manifest = freeze_v14(ROOT)
    print(
        "Frozen E&P V1.4 research benchmark:",
        manifest["manifest_sha256"],
        f"({manifest['verified_files']} files)",
    )
