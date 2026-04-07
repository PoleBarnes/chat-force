# VAULT.md — Test Fixture

This is a stub. See `docs/templates/vault-starter/VAULT.md` for the real
schema used by production harnesses.

The fixture vault exists only so `HarnessLoader` validation passes. Tests
that need to exercise real vault behavior should build their own vault in
`tmp_path` rather than populate this fixture.
