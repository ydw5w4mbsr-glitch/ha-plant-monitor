# Plant Monitor Architecture

**Repository:** `ydw5w4mbsr-glitch/ha-plant-monitor`  
**Home Assistant domain:** `plant_monitor`  
**Architecture status:** MVP implementation in progress  
**Last updated:** 2026-07-14

## 1. Purpose

Plant Monitor is a small Home Assistant custom integration for managing plants with soil-moisture sensors entirely through the Home Assistant user interface.

The integration answers one operational question:

> Which plants need watering now?

Each plant has its own moisture sensor and its own watering thresholds. Plant Monitor converts the raw sensor value into a stable watering state with hysteresis, preserves that state across restarts, and exposes entities that can be used in dashboards and normal Home Assistant automations.

The integration is distributed as a public GitHub repository and installed through HACS as a custom repository.

## 2. Design principles

The implementation follows these principles:

1. **UI-first configuration**  
   Plants are created, edited, and deleted through Home Assistant. No YAML configuration is required per plant.

2. **Small MVP**  
   Only functionality required for reliable watering decisions belongs in the first version.

3. **Native Home Assistant concepts**  
   The integration uses Config Entries, Config Subentries, the entity and device registries, translations, storage helpers, and event-driven state listeners.

4. **Stable plant identity**  
   A configured plant is a persistent logical object. Its identity must not depend on the currently assigned physical moisture sensor.

5. **No polling**  
   Sensor changes are handled through Home Assistant state-change events.

6. **No ownership of source sensors**  
   Plant Monitor reads an existing sensor entity but does not duplicate, move, rename, disable, or otherwise modify that entity.

7. **One source of configuration truth**  
   Thresholds are stored only in the plant Config Subentry. They are not separately editable through number entities or YAML.

8. **Fail safely**  
   Temporary sensor failures must not silently clear an existing watering alert.

## 3. MVP scope

Each plant is configurable through the UI with:

- plant name;
- soil-moisture sensor;
- `dry_below`;
- `clear_at`.

The MVP supports:

- adding plants;
- editing plants;
- deleting plants;
- different thresholds per plant;
- hysteresis;
- restoration of the last watering state after restart or reload;
- handling of unavailable, unknown, non-numeric, infinite, and out-of-range sensor values;
- prevention of assigning the same sensor to multiple plants;
- event-driven updates;
- a central overview across all plants;
- normal Home Assistant automations based on exposed entities.

The MVP does not include:

- a custom Lovelace card;
- a plant species database;
- location, pot size, pictures, or notes;
- fertilisation tracking;
- predictions;
- built-in push notifications;
- automatic irrigation;
- an upper “too wet” threshold;
- direct editing of thresholds through entities;
- ownership or relocation of the source sensor entity.

Notifications are created later through ordinary Home Assistant automations.

## 4. Home Assistant integration model

### 4.1 Integration type

The manifest uses:

```json
"integration_type": "hub"
```

Plant Monitor is not modelled as a Home Assistant helper. It owns one central Config Entry, multiple Config Subentries, persistent runtime state, several entities, and logical plant devices.

Using `helper` caused the integration to appear in the Helpers interface, where the required Config Subentry management was not accessible. The `hub` type correctly exposes the integration under **Settings → Devices & services → Integrations**.

### 4.2 Main Config Entry

Plant Monitor allows exactly one main Config Entry:

```json
"single_config_entry": true
```

The main entry represents the Plant Monitor service as a whole. It contains no per-plant configuration.

### 4.3 Plant Config Subentries

Each plant is represented by a native Config Subentry of type:

```text
plant
```

A plant Subentry contains:

```text
title               Plant name
moisture_sensor     Source sensor entity ID
dry_below           Lower threshold
clear_at             Alert-clear threshold
```

The Subentry ID is the stable internal identity of the plant.

This avoids maintaining a custom plant list inside `entry.options` and lets Home Assistant provide native add, edit, and delete operations.

### 4.4 Duplicate source sensors

A moisture sensor can be assigned to only one plant.

The Config Subentry flow checks all existing plant Subentries and rejects a sensor already used by another plant. During reconfiguration, the currently edited Subentry is excluded from this duplicate check.

## 5. Domain model

### 5.1 PlantConfig

`PlantConfig` is immutable runtime configuration derived from a Config Subentry:

```python
@dataclass(frozen=True, slots=True)
class PlantConfig:
    subentry_id: str
    name: str
    moisture_sensor: str
    dry_below: float
    clear_at: float
```

### 5.2 PlantState

`PlantState` contains mutable runtime state:

```python
@dataclass(slots=True)
class PlantState:
    config: PlantConfig
    status: PlantStatus
    watering_needed: bool
    moisture: float | None
```

### 5.3 Status values

The public plant status is one of:

```text
ok
dry
unavailable
invalid
```

Meaning:

- `ok`: the source value is valid and the internal watering state is false;
- `dry`: the source value is valid and the internal watering state is true;
- `unavailable`: the source entity is missing, `unknown`, or `unavailable`;
- `invalid`: the source state exists but is not a valid percentage from 0 through 100.

The public status and the internal watering state are intentionally separate.

## 6. Watering state machine

For a valid moisture value:

```text
moisture < dry_below
    → watering_needed = true

moisture >= clear_at
    → watering_needed = false

dry_below <= moisture < clear_at
    → retain previous watering_needed value
```

This hysteresis prevents the alert from repeatedly switching near one threshold.

Configuration validation requires:

```text
0 <= dry_below < clear_at <= 100
```

### 6.1 Invalid and unavailable values

The following are not accepted as valid moisture measurements:

- missing entity;
- `unknown`;
- `unavailable`;
- non-numeric strings;
- NaN;
- positive or negative infinity;
- values below 0;
- values above 100.

For such values:

- `status` becomes `unavailable` or `invalid`;
- the displayed current moisture becomes `None`;
- the last known `watering_needed` value is retained.

A dry plant therefore remains marked as needing water even if its sensor temporarily fails. The failure is visible through the status entity at the same time.

## 7. Runtime architecture

### 7.1 Manager

`PlantMonitorManager` is the central runtime object.

It is stored as typed runtime data:

```python
ConfigEntry[PlantMonitorManager]
```

and assigned to:

```python
entry.runtime_data
```

The manager owns:

- all `PlantState` objects;
- the mapping from source sensor entity IDs to plants;
- the source-state listener;
- persistence;
- listener callbacks for entities;
- central aggregate calculations.

### 7.2 Event-driven updates

The manager subscribes to source sensor changes with:

```python
async_track_state_change_event
```

There is no polling and no `DataUpdateCoordinator`.

All Plant Monitor entities use:

```python
should_poll = False
```

When a source state changes:

1. the manager validates the value;
2. it applies the hysteresis state machine;
3. it schedules persistence if `watering_needed` changed;
4. it notifies registered entities;
5. the entities write their new Home Assistant state.

### 7.3 Setup and unload

During `async_setup_entry`:

1. plant Subentries are converted into `PlantConfig` objects;
2. `PlantMonitorManager` is created;
3. the manager is assigned to `entry.runtime_data`;
4. an update listener is registered;
5. persisted watering states are restored;
6. source sensor listeners are registered;
7. current source states are evaluated;
8. binary-sensor and sensor platforms are forwarded with `async_forward_entry_setups`.

During `async_unload_entry`:

1. entity platforms are unloaded with `async_unload_platforms`;
2. source listeners are removed;
3. the current watering state is saved;
4. manager listeners are cleared.

### 7.4 Reloads after plant changes

Adding, editing, or deleting a plant changes the main Config Entry through its Subentries.

A single update listener reloads the main Config Entry after such changes. The reconfigure flow updates the Subentry but does not independently request a second reload.

This keeps lifecycle handling in one place and avoids duplicate reload scheduling.

## 8. Persistence

Only the state that cannot always be reconstructed after restart is persisted:

```text
watering_needed by plant subentry ID
```

The storage key is based on the integration domain and main Config Entry ID.

The current moisture and public status are not persisted. They are recalculated from the source entity state during startup.

Persisting by Subentry ID provides stable restoration even if:

- the plant is renamed;
- the source entity is replaced;
- thresholds are edited.

Deleted plant IDs are naturally ignored when stored data is loaded.

## 9. Device model

### 9.1 One logical device per plant

Each plant has its own logical Home Assistant device.

The device identifier is derived from:

```text
config_entry_id + subentry_id
```

This device groups all entities that describe the configured plant.

The plant device is not a claim that the plant itself is electronic hardware. It represents the Plant Monitor service object for that plant.

### 9.2 Source sensor remains independent

The selected source sensor remains attached to its original integration and original device, such as an Ecowitt WH51 device.

Plant Monitor does not:

- move the source entity;
- add the source entity to the plant device;
- remove it from the source device;
- change its entity ID;
- change its registry ownership.

### 9.3 Why Plant Monitor does not attach its entities to the source device

This alternative was considered and rejected.

The plant and the source sensor have different lifecycles:

- a plant may receive a replacement sensor;
- a sensor may later monitor another plant;
- thresholds belong to the plant, not to the sensor hardware;
- the stored watering state belongs to the plant;
- plant entities and automations should retain their identity when hardware changes.

Attaching Plant Monitor entities to the source device would couple plant identity to replaceable hardware and would introduce dependencies on the device-registry behaviour of other integrations.

It would also behave inconsistently for source entities without a device.

### 9.4 Projected moisture entity

The original source sensor cannot simultaneously appear inside the separate plant device without being moved away from its source device.

To make the current reading visible on the plant device, Plant Monitor will expose a read-only projected measurement:

```text
sensor.<plant>_soil_moisture
```

This entity:

- mirrors the validated current source value;
- uses `%`;
- uses the moisture device class;
- uses measurement state class;
- belongs to the logical plant device;
- does not replace or modify the original sensor;
- is unavailable when no valid current value exists.

This duplication is intentional at the entity-display layer. It provides stable plant-centred presentation while preserving correct ownership of the physical source sensor.

## 10. Entity model

### 10.1 Existing central entities

The main Config Entry exposes:

```text
binary_sensor.plant_monitor_watering_needed
sensor.plant_monitor_dry_plants
sensor.plant_monitor_unavailable_sensors
```

Responsibilities:

- central watering-needed binary sensor: true if any plant needs water;
- dry-plants sensor: count of plants whose retained watering state is true;
- unavailable-sensors sensor: count of plants whose source status is unavailable.

Invalid source values are exposed as attributes on the unavailable-sensors aggregate sensor in the current MVP implementation.

### 10.2 Existing per-plant entities

Each plant currently exposes:

```text
binary_sensor.<plant>_watering_needed
sensor.<plant>_status
```

Unique IDs are derived from:

```text
config_entry_id + subentry_id + entity key
```

This keeps entity identity stable across renaming and source sensor replacement.

### 10.3 Planned per-plant display entities

The next implementation change adds:

```text
sensor.<plant>_soil_moisture
sensor.<plant>_dry_below
sensor.<plant>_clear_at
```

The resulting plant device will contain:

```text
Soil moisture       current validated value in %
Status              ok, dry, unavailable, or invalid
Watering needed     on or off
Dry below           configured threshold in %
Clear alert at      configured threshold in %
```

`Dry below` and `Clear alert at` are read-only diagnostic/configuration displays. They are edited only through **Edit plant**.

### 10.4 Attribute cleanup

The frequently changing moisture value is currently included as an attribute of existing plant entities.

When the dedicated soil-moisture entity is added, the dynamic moisture attribute will be removed from:

- the per-plant status sensor;
- the per-plant watering-needed binary sensor.

Threshold attributes may also be removed where they become redundant after the dedicated threshold entities exist.

This avoids storing a frequently changing measurement repeatedly as attributes on multiple entities.

## 11. User interface

### 11.1 Installation and initial setup

The integration is:

1. added to HACS as a custom repository;
2. downloaded through HACS;
3. loaded after a Home Assistant restart;
4. added from **Settings → Devices & services → Integrations**.

The integration must appear as **Plant Monitor (Helper)** only because Home Assistant already contains another integration named Plant Monitor. Internally, this project is configured as a hub, not as a helper.

A future naming decision may rename the public integration to reduce confusion with Home Assistant’s built-in Plant integration.

### 11.2 Plant management

Inside the Plant Monitor integration page, the user can:

- use **Add plant**;
- open an existing plant Subentry;
- edit its configuration;
- delete it.

The add/edit form contains:

```text
Plant name
Soil moisture sensor
Dry below
Clear alert at
```

### 11.3 Mobile-first operation

Configuration must remain practical on a phone:

- no per-plant YAML;
- no manual registry editing;
- no editing of internal storage;
- no duplicate configuration surfaces;
- clear labels and validation messages;
- all plant values grouped on the logical plant device.

A custom dashboard card remains outside the MVP.

## 12. Error handling and invariants

The implementation must preserve these invariants:

1. One main Config Entry only.
2. One Config Subentry per plant.
3. One source sensor per plant.
4. The same source sensor cannot be assigned to two plants.
5. `dry_below` must be lower than `clear_at`.
6. Valid percentages are restricted to 0 through 100.
7. Sensor failure does not clear the retained watering state.
8. Listener registration must be reversed during unload.
9. Plant entity unique IDs must not depend on the plant name or source entity ID.
10. Source entities remain owned by their original integration.
11. All thresholds are edited through the Config Subentry flow only.

## 13. Repository structure

Target structure:

```text
ha-plant-monitor/
├── custom_components/
│   └── plant_monitor/
│       ├── brand/
│       │   └── icon.png
│       ├── translations/
│       │   ├── en.json
│       │   └── de.json
│       ├── __init__.py
│       ├── binary_sensor.py
│       ├── config_flow.py
│       ├── const.py
│       ├── entity.py
│       ├── manager.py
│       ├── manifest.json
│       ├── models.py
│       └── sensor.py
├── .github/
│   └── workflows/
│       ├── hacs.yml
│       └── hassfest.yml
├── tests/
├── ARCHITECTURE.md
├── CHANGELOG.md
├── hacs.json
├── LICENSE
├── pyproject.toml
└── README.md
```

Not every target file or directory is implemented yet.

## 14. Validation and quality

The repository currently uses:

- Home Assistant hassfest validation;
- HACS repository validation.

Both workflows passed before this architecture document was added.

Passing these checks confirms repository and metadata structure, but it does not replace unit and integration tests.

Required automated tests still include:

- values below `dry_below`;
- values exactly at `dry_below`;
- values inside the hysteresis band;
- values exactly at `clear_at`;
- values above `clear_at`;
- restart restoration;
- unavailable source while previously dry;
- unavailable source while previously OK;
- non-numeric source values;
- NaN and infinity;
- values outside 0 through 100;
- duplicate sensor rejection;
- add, reconfigure, and delete Subentry flows;
- source sensor replacement;
- full unload and listener cleanup;
- aggregate entity updates.

## 15. Current implementation status

Implemented and manually confirmed:

- public GitHub repository;
- HACS custom-repository installation;
- HACS validation passing;
- hassfest validation passing;
- integration manifest;
- integration type `hub`;
- one main Config Entry;
- native plant Config Subentries;
- add and edit plant flows;
- duplicate sensor validation;
- runtime manager;
- event-driven source updates;
- hysteresis;
- invalid and unavailable handling;
- watering-state persistence;
- logical device per plant;
- central entities;
- per-plant status and watering-needed entities;
- successful installation and startup in Home Assistant;
- two plants created successfully through the UI.

Not yet completed:

- projected per-plant soil-moisture entity;
- per-plant threshold display entities;
- removal of duplicated dynamic moisture attributes;
- complete automated test suite;
- German translation;
- final README;
- changelog;
- release process and first tagged release;
- final naming decision to avoid confusion with the built-in Plant Monitor result.

## 16. Next implementation step

The next code change is deliberately limited to entity presentation.

Add to each plant device:

```text
Soil moisture
Dry below
Clear alert at
```

Then remove the dynamic moisture measurement from the attributes of the existing per-plant entities.

This change must not alter:

- Config Entry or Config Subentry identity;
- manager persistence;
- source sensor ownership;
- plant device identifiers;
- existing status and watering-needed unique IDs;
- hysteresis behaviour;
- lifecycle handling.

## 17. Deferred work

After the display entities are complete:

1. update English translations;
2. add unit and config-flow tests;
3. add German translations in one final pass;
4. complete README and changelog;
5. decide on a less ambiguous public display name;
6. create the first tagged GitHub release;
7. test HACS installation from the release rather than `main`;
8. document a normal Home Assistant notification automation.

## 18. Architectural decision summary

| Decision | Result |
|---|---|
| Configuration storage | Native Config Subentries |
| Main integration type | Hub |
| Number of main entries | One |
| Runtime update model | Event-driven |
| Coordinator | None |
| Polling | Disabled |
| Persistent state | `watering_needed` by Subentry ID |
| Plant identity | Config Subentry ID |
| Plant grouping | One logical device per plant |
| Source sensor ownership | Original integration retains ownership |
| Source sensor relocation | Not allowed |
| Moisture shown on plant device | Read-only projected sensor |
| Threshold editing | Config Subentry flow only |
| Notifications | Normal Home Assistant automation |
| Custom dashboard card | Outside MVP |

This document is the authoritative technical reference for the Plant Monitor repository. Architecture changes should update this file in the same commit as the related code.
