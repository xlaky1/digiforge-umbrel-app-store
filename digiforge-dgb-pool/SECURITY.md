# DigiForge 1.0 security layout

Host/LAN published:
- `12024/tcp` — DigiByte P2P
- `3256/tcp` — SHA256 Stratum

Private backend only:
- `14022/tcp` — DigiByte RPC
- `5432/tcp` — PostgreSQL
- `4000/tcp` — Miningcore API

The dashboard is reached through Umbrel app_proxy. DigiForge does not mount the Docker socket, does not request privileged mode, and disables automatic Miningcore payouts.

Python, PostgreSQL, and Miningcore images are digest-pinned. The DigiByte image is fixed to the verified `v8.26.2` tag but is not yet pinned to a full immutable digest.
