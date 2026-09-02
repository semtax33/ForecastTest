from pathlib import Path

from energy_nowcast.research.ep_v13.benchmark import freeze_v13


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    manifest = freeze_v13(root)
    print(
        f"Frozen {manifest['name']} with {manifest['verified_files']} verified files "
        f"({manifest['manifest_sha256']})."
    )
