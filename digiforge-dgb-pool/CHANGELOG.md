# Changelog

## 1.0.1

- Fixed `web_1` failing during container creation on umbrelOS.
- Removed the nested bind mount of `config/config.default.json` into the read-only `/app` mount.
- Changed the DigiForge web backend to load the default Miningcore configuration from `/data/config.default.json`.
- Kept the 1.0 dashboard, DigiByte node, Miningcore, PostgreSQL, Stratum port, and app-proxy topology unchanged.

## 1.0.0

- Added the production DigiForge dashboard and first-run DGB address setup.
- Added live node, pool and miner status.
- Added automatic Miningcore configuration reload helper.
- Corrected Umbrel app-proxy networking.
- Added DigiForge branding and DigiForge-owned repository/support links.
