# Contributing

Contributions are welcome.

## Before opening a pull request

1. Open an issue describing the proposed change or bug.
2. Keep changes focused on MeshMonitor compatibility and emergency-communications workflows.
3. Preserve the strict separation between LIVE and EXERCISE modes.
4. Do not allow inbound mesh traffic to enable LIVE mode.
5. Do not allow simulated injects to run while LIVE.
6. Keep the runtime Python standard-library only unless a dependency is clearly justified.
7. Test changes with representative MeshMonitor environment variables.
8. Do not include credentials, private node databases, real emergency traffic, or sensitive operational data in commits.

## Pull requests

Include:
- A concise description of the change
- Whether it affects LIVE mode, EXERCISE mode, or both
- How it was tested
- Any MeshMonitor configuration changes required
- Compatibility notes for existing `SET` users when applicable
