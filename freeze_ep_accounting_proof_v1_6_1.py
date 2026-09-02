from pathlib import Path

from energy_nowcast.research.ep_v161.benchmark import freeze_v161


ROOT = Path(__file__).resolve().parent


if __name__ == "__main__":
    manifest = freeze_v161(ROOT)
    print(
        "Frozen E&P V1.6.1 research benchmark:",
        manifest["manifest_sha256"],
        f"({manifest['verified_files']} files, "
        f"{manifest['verified_source_dependencies']} source dependencies)",
    )
