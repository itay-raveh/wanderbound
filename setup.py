from cx_Freeze import Executable, setup
import tomllib
from pathlib import Path

# 1. Dynamic Logic: Handle pyproj data path (Required for geopandas/maps)
PYPROJ_DATADIR = None
try:
    from pyproj import datadir

    PYPROJ_DATADIR = datadir.get_data_dir()
except ImportError:
    pass


# 2. Dependency Management: Import from pyproject.toml
def get_project_dependencies() -> list[str]:
    """Extract dependencies from pyproject.toml."""
    with Path("pyproject.toml").open("rb") as f:
        data = tomllib.load(f)
    return data.get("project", {}).get("dependencies", [])


def parse_package_name(dep_string: str) -> str:
    """Clean dependency string to get package name."""
    # Remove extras: "pkg[extra]" -> "pkg"
    base = dep_string.split("[")[0]
    # Remove version specifiers: "pkg>1.0" -> "pkg"
    for op in [">", "<", "=", "!", "~"]:
        base = base.split(op)[0]
    return base.strip()


# Map distribution names to import names where they differ
DIST_TO_IMPORT = {
    "opencv-python": "cv2",
    "opencv-python-headless": "cv2",
    "Pillow": "PIL",
    "cx_Freeze": None,  # Exclude build tool
    "more-itertools": "more_itertools",
    "pydantic-settings": "pydantic_settings",
    "persist-cache": "persist_cache",
}

deps = get_project_dependencies()
discovered_packages = []
for dep in deps:
    pkg_name = parse_package_name(dep)
    # Handle mapping
    if pkg_name in DIST_TO_IMPORT:
        mapped = DIST_TO_IMPORT[pkg_name]
        if mapped:
            discovered_packages.append(mapped)
    else:
        discovered_packages.append(pkg_name)

# 3. Build Options
# Manual overrides for submodules or things cx_Freeze misses
force_packages = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.lifespan",
    "uvicorn.protocols",
    # Standard libs are usually auto-detected, but listed here if dynamic import issues arise
    "asyncio",
    "tkinter",
]

packages = list(set(discovered_packages + force_packages))

excludes = [
    "matplotlib",
    "scipy",
    "notebook",
    "ipython",
    "test",
    "unittest",
    "email.test",
    "http.test",
    "pydoc",
    "pdb",
    # Reduce size by excluding build/dev tools and test suites
    "setuptools",
    "distutils",
    "pip",
    "pkg_resources",
    "wheel",
    "pytest",
    "mypy",
    "ruff",
    "pandas.tests",
    "numpy.tests",
]

include_files = [("static", "static"), (".env", ".env")]

if PYPROJ_DATADIR:
    include_files.append((PYPROJ_DATADIR, "share/proj"))

build_exe_options = {
    "packages": packages,
    "excludes": excludes,
    "include_files": include_files,
    "include_msvcr": True,
    "optimize": 2,
    # Speed up startup by zipping all packages (reduces I/O)
    "zip_include_packages": ["*"],
    "zip_exclude_packages": [],
}
upgrade_code = "{3B770287-3932-4752-9596-764720993068}"

setup(
    name="polarsteps-album-generator",
    version="0.1.0",
    description="Generate photo albums from Polarsteps trip data",
    author="Itay Raveh",
    author_email="itay.raveh@proton.me",
    options={
        "build_exe": build_exe_options,
        "bdist_msi": {
            "upgrade_code": upgrade_code,
            "add_to_path": True,
            "initial_target_dir": r"[ProgramFilesFolder]\PolarstepsAlbumGenerator",
            "install_icon": "static/favicon.ico",
        },
    },
    executables=[
        Executable(
            "src/app/gui.py",
            target_name="polarsteps-album-generator",
            icon="static/favicon.ico",
            shortcut_name="Polarsteps Album Generator",
            shortcut_dir="ProgramMenuFolder",
            base="gui",  # "gui" base hides the console window on Windows
        ),
        Executable(
            "src/app/gui.py",
            target_name="polarsteps-album-generator",
            icon="static/favicon.ico",
            shortcut_name="Polarsteps Album Generator",
            shortcut_dir="DesktopFolder",
            base="gui",
        ),
    ],
)
