# Changelog

All notable changes to Thingdex are documented here. Versions follow Semantic Versioning.

## Unreleased

### Added

- Typed health response.
- Typed synchronous label-print response containing status, printer, sent byte count, and optional preview.
- CI checks for tests and committed OpenAPI contract drift.
- Database constraints and regression tests for location-root and active-relation invariants.
- Readiness/liveness endpoints and automatic container migrations.
- A versioned Material for MkDocs documentation site.

### Changed

- Label side-effect results now use the same print contract as direct reprints.
- Relation active state changes now require attach/detach workflows.
- Item type schema changes are rejected when they would invalidate existing items.
- Deployment orchestration was moved out of the backend repository.
