# Repository Guidelines for Automation and Versioning

- Keep HACS metadata updates manual. When preparing a release, bump the version field in `custom_components/cozylife/manifest.json` explicitly and, if needed, adjust `hacs.json` manually.
- Do **not** introduce workflows or scripts that automatically commit or push version changes on merge. Follow the standard HACS approach of using Git tags or deliberate commits for versioning.
