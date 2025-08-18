# Blender ACES Manager

Blender add-on to install and switch between Blender’s default color management and ACES (Academy Color Encoding System). It can restart Blender after switching, validates the active OCIO configuration, and keeps backups of previous settings.

## Features

- Install an ACES OCIO configuration from official or community sources, or a custom ZIP URL
- Switch between ACES and Blender default color management
- Optional auto‑restart after switching
- Validate the current OCIO configuration
- Back up the previous override and, when possible, Blender’s default config
- Show installation progress and allow cancel
- Works with Blender 3.0 and newer (including 4.x)

## Compatibility

- Blender 3.0+
- Prefers OCIO v2 configurations. Known incompatible configs (e.g., XYZ role/name conflicts) are blocked.

## Installation

### From a release ZIP
1. Download the add-on ZIP from this repository’s Releases.
2. In Blender: Edit > Preferences > Add-ons > Install..., select the ZIP.
3. Enable “System: Blender ACES Manager”.

### From source
1. Clone or download this repository.
2. Zip the `blender_aces_manager` folder (the ZIP should contain that folder at the top level).
3. Install the ZIP in Blender (Edit > Preferences > Add-ons > Install...).

## Usage

Panel location: Properties > Render Properties > ACES Switcher.

- Install ACES: downloads and installs an ACES OCIO config (progress is shown; you can cancel).
- Switch to ACES: applies the installed ACES config. Blender can restart automatically.
- Switch to Default: returns to Blender’s default color management.
- Validate Current Config: quick check of the active OCIO file.

### Preferences
- Auto-Restart Blender: restart after switching (default on).
- Custom ACES Repo (Zip): optional URL to a ZIP that contains a `config.ocio`.

## Notes

- The add-on sets Blender’s OCIO config override. On Windows, it may set or clear a per-user `OCIO` environment variable so restarts inherit the setting.
- When switching, the add-on stores backups under your Blender configuration directory.

## Troubleshooting

- Installation fails: check your network; try a custom URL; ensure Blender can write to its config directory.
- Changes not applied: restart Blender; check the OCIO path shown in the panel; review the console for errors.
- Slow or stuck download: wait for large downloads, or cancel and retry.

## Contributing

Issues and pull requests are welcome. For larger changes, open an issue first to discuss the approach.

## License

MIT License. See `LICENSE`.

## Changelog

### 1.0.1
- Initial public release.
- ACES installation and switching.
- Blender 3.x and 4.x support.
- Auto-restart option.
- Basic configuration validation.
