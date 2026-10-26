"""py2app spec for the standalone UnfairPlay.app.

Build on macOS with the unfairplay binary present (the GitHub Actions
workflow in .github/workflows/build-app.yml does exactly this):

    go build -o unfairplay ./cmd/unfairplay
    python setup.py py2app

The bundle ships its own Python interpreter and tkinter; the Go binary
runs as a subprocess exactly as from the terminal.
"""

from setuptools import setup

OPTIONS = {
    "argv_emulation": False,
    "plist": {
        "CFBundleName": "UnfairPlay",
        "CFBundleDisplayName": "UnfairPlay",
        "CFBundleIdentifier": "io.github.ziqzav.unfairplay",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
    },
}

setup(
    name="UnfairPlay",
    app=["mac_gui.py"],
    data_files=[("", ["unfairplay"])],
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)