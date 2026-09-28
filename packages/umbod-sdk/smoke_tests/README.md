# Installed SDK verification

`installed_wheel.py` runs under an isolated environment containing a built SDK wheel. It verifies that imports come from the installed distribution, previews and applies connector initialization in a temporary project, checks compatible and incompatible SDK declarations, and invokes the generated connector's public contract. It leaves dependency resolution and image builds outside the CLI.

The SDK CI job builds and installs the wheel before executing this check. Unit and adapter tests under `tests/` cover registry metadata without requiring a published synchronized release.
