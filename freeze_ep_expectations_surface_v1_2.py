from pathlib import Path

from energy_nowcast.research.ep_v12.benchmark import freeze_v12


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    manifest = freeze_v12(root)
    print(
        f"Frozen {manifest['name']} with {manifest['verified_files']} verified files "
        f"({manifest['manifest_sha256']})."
    )
