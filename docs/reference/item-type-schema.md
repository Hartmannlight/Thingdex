# Item type schema

Thingdex uses a small project-specific schema dialect for each item type. It is
stored as JSONB and validated when the type is created or changed.

## Document shape

```json
{
  "fields": {
    "serial": {
      "type": "string",
      "required": true,
      "pattern": "[A-Z0-9-]+",
      "track_history": false,
      "label": "Serial number",
      "order": 10
    },
    "capacity_gb": {
      "type": "integer",
      "min": 1,
      "unit": "GB",
      "track_history": false
    },
    "free_gb": {
      "type": "integer",
      "min": 0,
      "track_history": true
    }
  },
  "allow_additional": false
}
```

`fields` defaults to an empty object. `allow_additional` defaults to `false`.

## Field properties

| Property | Type | Behavior |
| --- | --- | --- |
| `type` | string | Required; one of `string`, `integer`, `number`, `boolean`, `date`, `date-time` |
| `required` | boolean | Requires the property on create and full replacement |
| `default` | matching field value | Added during item creation and full replacement when omitted |
| `enum` | array | Restricts the value to one of the listed values |
| `min` | number | Inclusive numeric lower bound |
| `max` | number | Inclusive numeric upper bound |
| `pattern` | string | Full-match regular expression for strings |
| `track_history` | boolean | Appends an event when an update changes this value |
| `unit` | string | UI hint with no conversion behavior |
| `label` | string | Human-readable UI hint |
| `help` | string | Longer UI guidance |
| `group` | string | UI grouping hint |
| `order` | number | UI sorting hint |

Unknown UI-oriented keys in field definitions are retained. Validation logic
acts only on the properties listed above.

## Partial and full writes

`PATCH /v1/items/{id}/props` validates supplied fields and merges them into the
current object. `PUT /v1/items/{id}/props` validates the full final object,
applies defaults, and replaces the old object.

Item creation is a full validation. Unknown property keys are rejected unless
`allow_additional` is true.

## Compatible schema evolution

Thingdex evaluates a proposed schema against all active items of that type.
Examples of incompatible changes include:

- changing an existing string field to an integer;
- adding a required field that current items do not contain;
- narrowing an enum, range, or pattern beyond stored values;
- disabling additional properties while items contain undeclared keys.

Incompatible updates return `409` and leave the stored schema unchanged. Migrate
item data first using ordinary validated item updates, then retry the schema
change.

## Label templates

Required variables declared by a linked label template must correspond to
required fields in the item schema. `internal_uuid` is supplied by Thingdex and
does not need to be declared as an item property.
