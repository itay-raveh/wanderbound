import sys

from cx_Freeze import Executable, setup

# 1. Dynamic Logic: Handle pyproj data path (Required for geopandas/maps)
# This cannot be done in pyproject.toml
try:
    import pyproj

    PYPROJ_DATADIR = pyproj.datadir.get_data_dir()
except ImportError:
    PYPROJ_DATADIR = None

# 2. Build Options
# We explicitly list packages that cx_Freeze might miss or that need their full context.
packages = [
    "os",
    "sys",
    "asyncio",
    "nicegui",
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.lifespan",
    "uvicorn.protocols",
    "rich",
    "geopy",
    "geopandas",
    "shapely",
    "jinja2",
    "PIL",  # pillow
    "tkinter",
    "cv2",  # opencv-python
]

include_files = [("static", "static"), (".env", ".env")]

if PYPROJ_DATADIR:
    include_files.append((PYPROJ_DATADIR, "share/proj"))

build_exe_options = {
    "packages": packages,
    "excludes": [],
    "include_files": include_files,
    "include_msvcr": True,
    "optimize": 2,
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
        ),
        Executable(
            "src/app/gui.py",
            target_name="polarsteps-album-generator",
            icon="static/favicon.ico",
            shortcut_name="Polarsteps Album Generator",
            shortcut_dir="DesktopFolder",
        ),
    ],
)
