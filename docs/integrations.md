# Integrations and repository map

Thingdex is designed as one component in a multi-repository system. Each
repository should own and publish its detailed documentation. The main system
repository can then provide a short architecture overview and link to these
canonical sites.

## Repository responsibilities

| Repository | Responsibility | Relationship to Thingdex |
| --- | --- | --- |
| [Thingdex Home Inventory](https://github.com/Hartmannlight/Thingdex-Home-Inventory) | System topology, deployment, operator entry point | Runs Thingdex with its dependencies and links all component docs |
| [ThingdexUI](https://github.com/Hartmannlight/ThingdexUI) | Day-to-day browser interface | Calls the Thingdex API |
| [thingdex-sdk](https://github.com/Hartmannlight/thingdex-sdk) | Generated TypeScript API client | Consumes this repository's `openapi.json` |
| [PrintHub-ZPL-II](https://github.com/Hartmannlight/PrintHub-ZPL-ll) | Templates, rendering, persistent print jobs and printer gateway | Optional integration; receives idempotent label jobs |
| [LabelArchitect / PrintHub Studio](https://github.com/Hartmannlight/LabelArchitect) | Template library, desktop designer, mobile quick print, printer and job UI | Standalone PrintHub frontend; Thingdex does not depend on it at runtime |
| [LabelGallery](https://github.com/Hartmannlight/LabelGallery) | Legacy template/operator UI | Superseded by PrintHub Studio and not part of the default topology |
| [ZebraTamer](https://github.com/Hartmannlight/ZebraTamer) | Local-network printer discovery, status and standardized ZPL job handoff | Used by PrintHub, never called by Thingdex |

## OpenAPI and SDK

The committed `openapi.json` is the cross-repository contract. CI checks that
it matches the FastAPI application. SDK generation should depend on a tagged or
committed contract rather than scraping a mutable running environment.

When the contract changes:

1. update and test Thingdex;
2. regenerate and commit `openapi.json`;
3. regenerate `thingdex-sdk`;
4. update UI consumers;
5. link compatible versions in release notes where necessary.

## Product boundary

Thingdex and PrintHub are independently deployable products. Thingdex owns
inventory data and optional label automation rules. It never owns template
layouts, ZPL, printer configuration or device status. PrintHub owns all of
those concerns and remains useful without Thingdex through its mobile quick
print UI and API.

Thingdex starts and saves inventory when PrintHub is absent. A failed label job
is reported as a failed side effect after the inventory transaction and never
rolls the inventory record back.

## Automatic label flow

Label support is optional and disabled by default. When enabled:

1. an administrator creates one `label_profile` for an item type or location
   kind, selecting a PrintHub template and printer once;
2. Thingdex validates the template's typed variables against the item schema
   and optional explicit bindings;
3. an operator creates an item or location without selecting any printing
   options;
4. Thingdex commits the inventory record first, resolves the matching enabled
   profile and fills the template variables;
5. Thingdex creates a persistent PrintHub job with an idempotency key based on
   the new entity ID;
6. PrintHub renders the saved template and hands ZPL to ZebraTamer or a legacy
   raw-9100 printer;
7. PrintHub keeps the job status and error. Failed jobs can be retried from
   PrintHub Studio without creating the inventory object again.

The old `item_types.label_template_id` and per-location metadata remain as a
compatibility fallback for manual reprints during migration. New automation
should use `/v1/label-profiles`.

```text
ThingdexUI -> Thingdex -> PrintHub API -> ZebraTamer -> Zebra printer
     |           |             |
 inventory   label profile   template + durable job
```

The template language, editor behavior, printer configuration, and rendering
details belong to their label repositories. Thingdex documents only its IDs,
variables, errors, and HTTP boundary.

## Cross-documentation convention

Until every repository publishes a static documentation site, link to its
repository root. Once a site exists, the main repository should link directly
to that stable docs URL. Component docs may cross-link to another component for
context but must not duplicate its operational or API reference.
