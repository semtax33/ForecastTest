from energy_nowcast.research.ep_v174.benchmark import freeze_v174
from equity_platform.paths import PROJECT_ROOT


ROOT = PROJECT_ROOT


if __name__ == "__main__":
    manifest = freeze_v174(ROOT)
    print(
        "Frozen E&P V1.7.4 research benchmark:",
        manifest["manifest_sha256"],
        f"({manifest['verified_files']} files)",
    )
