from energy_nowcast.research.ep_v13.benchmark import freeze_v13
from equity_platform.paths import PROJECT_ROOT


if __name__ == "__main__":
    manifest = freeze_v13(PROJECT_ROOT)
    print(
        f"Frozen {manifest['name']} with {manifest['verified_files']} verified files "
        f"({manifest['manifest_sha256']})."
    )
