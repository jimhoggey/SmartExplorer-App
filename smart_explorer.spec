# -*- mode: python ; coding: utf-8 -*-
import sys

from PyInstaller.utils.hooks import collect_data_files

sys.path.insert(0, SPECPATH)  # noqa: F821 (PyInstaller defines SPECPATH)
from version import APP_VERSION  # noqa: E402

NAME = "Smart Explorer"
icon = "assets/icon.ico" if sys.platform == "win32" else "assets/icon.icns"
a = Analysis(["desktop.py"], datas=[("static", "static")] + collect_data_files("imageio_ffmpeg"))
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, exclude_binaries=True, name=NAME, console=False, icon=icon)
coll = COLLECT(exe, a.binaries, a.datas, name=NAME)
if sys.platform == "darwin":
    # Why the app needs each folder, shown in macOS's permission prompts.
    why = "Smart Explorer renames the files you choose there, after you have checked the new names."
    app = BUNDLE(coll, name=NAME + ".app", icon=icon, version=APP_VERSION,
                 bundle_identifier="com.jimhoggey.smartexplorer",
                 info_plist={
                     "CFBundleDisplayName": NAME,
                     "CFBundleShortVersionString": APP_VERSION,
                     "CFBundleVersion": APP_VERSION,
                     "NSHighResolutionCapable": True,
                     "LSApplicationCategoryType": "public.app-category.productivity",
                     "LSMinimumSystemVersion": "13.0",  # the bundled PDF library needs Ventura or later
                     "NSDesktopFolderUsageDescription": why,
                     "NSDocumentsFolderUsageDescription": why,
                     "NSDownloadsFolderUsageDescription": why,
                     "NSRemovableVolumesUsageDescription": why,
                     "NSNetworkVolumesUsageDescription": why,
                 })
