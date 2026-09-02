from pathlib import Path

from energy_nowcast.research.ep_v15.benchmark import freeze_v15


ROOT = Path(__file__).resolve().parent


if __name__ == "__main__":
    manifest = freeze_v15(ROOT)
    print(
        "Frozen E&P V1.5 research benchmark:",
        manifest["manifest_sha256"],
        f"({manifest['verified_files']} files)",
    )
