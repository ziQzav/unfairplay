# UnfairPlay

UnfairPlay recovers a FairPlay model from an enrolled Mac and uses it to
decrypt personalized iOS IPAs. It is a standalone Go program.

It does not log in to Apple, buy apps, or download IPAs. You can use ipatool or
another downloader for that part.

## Build

```sh
go build -o unfairplay ./cmd/unfairplay
```

## Usage

First, sign in to the native Mac App Store. Install an iPhone or iPad app and
open it once. Download an encrypted IPA with the same Apple Account.

Collect the Mac state and matching IPA:

```sh
sudo ./unfairplay collect \
  --app /Applications/App.app \
  --ipa App.ipa \
  --output App.capture
```

Recover the model and validate it:

```sh
./unfairplay recover \
  --capture App.capture \
  --output App.recovery
```

Decrypt another IPA from the same enrollment:

```sh
./unfairplay decrypt \
  --input AnotherApp.ipa \
  --model App.recovery/fairplay-enrollment.bin
```

Test a model without keeping the decrypted IPA:

```sh
./unfairplay verify \
  --input AnotherApp.ipa \
  --model App.recovery/fairplay-enrollment.bin
```

Use `unfairplay doctor` to check a capture, IPA, or model. Use
`unfairplay profile` to inspect a fairplayd binary.

## Support

Verified profiles: `25G83`, `26A428`/`26A434`, and `26B118` compatibility
mode. Unknown arm64e builds are accepted only if model recovery and full IPA
validation succeed.

macOS arm64 and Linux amd64/arm64 are supported. Windows is compile-tested but
cannot yet enforce the required private-file permissions.

The IPA, installed app, Mac state, hardware identity, and model must belong to
the same enrollment. Account or selector mismatches are rejected.

Keep capture and model files private. Do not share SIDB, SINF, hardware data,
recovery models, or decrypted apps. Decrypted IPAs are analysis files and need
signing before installation.

## macOS GUI

This fork ships a windowed interface (`mac_gui.py`) on top of the CLI: tabs
for **Decrypt**, **Recover**, **Verify**, **Doctor** and **Collect**, a shared
progress log, and input validation that mirrors the CLI's rules (output must
not exist, IPA required, model required). Collect runs through the native
administrator-password dialog.

### Ready-made app

A standalone macOS app (universal, with its own Python) is attached to every
`v*` release as `UnfairPlay-macos.dmg`: open the disk image and double-click
`UnfairPlay.app`. The app is unsigned, so right-click and **Open** on first
launch.

### From source

```sh
go build -o unfairplay ./cmd/unfairplay
python3 mac_gui.py          # tkinter, e.g. the python.org macOS build
```

## Releases

Tags matching `v*` publish binaries and `SHA256SUMS` through GitHub Actions.
Tags such as `v0.2.0-rc.1` create prereleases.

## License

MIT. The DarkPhoenix-derived Go code keeps its Apache-2.0 notice in
`LICENSE-DARKPHOENIX.txt`.
