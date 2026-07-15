# Plant Monitor Architecture

Repository: `ydw5w4mbsr-glitch/ha-plant-monitor`  
Home Assistant domain: `plant_monitor`  
Architecture status: Functional MVP; automated tests, documentation and release hardening pending  
Last updated: 2026-07-15

## 1. Purpose

Plant Monitor is a small Home Assistant custom integration for managing plants with soil-moisture sensors entirely through the Home Assistant user interface.

The integration answers one operational question:

> Which plants need watering now?

Each configured plant has:

- one existing Home Assistant soil-moisture sensor;
- an individual lower threshold, `dry_below`;
- an individual recovery threshold, `clear_at`;
- a retained watering state with hysteresis;
- one logical Home Assistant device containing the plant-centred display entities.

Plant Monitor does not own or alter the physical moisture sensor. It reads the source entity, validates its value and projects the relevant plant state into its own entities.

The integration is distributed through this public GitHub repository and installed through HACS as a custom repository.

## 2. Design principles

### 2.1 UI-first configuration

Plants are added, edited and deleted through Home Assistant. No per-plant YAML configuration is required.

### 2.2 Small, understandable MVP

Only functionality needed for a reliable watering decision belongs in the MVP. Species databases, predictions, fertilisation tracking and automatic irrigation remain outside the current scope.

### 2.3 Native Home Assistant concepts

The integration uses:

- one Config Entry;
- native Config Subentries for plants;
- entity and device registries;
- translation files;
- storage helpers;
- event-driven state listeners.

### 2.4 Stable plant identity

A plant is a persistent logical object. Its identity must not depend on:

- its display name;
- the selected source entity ID;
- the physical moisture-sensor device.

Replacing a sensor or renaming a plant must not create a new logical plant.

### 2.5 No polling

Source changes are processed from Home Assistant state-change events. Plant Monitor entities have polling disabled.

### 2.6 No ownership of source sensors

Plant Monitor reads an existing sensor entity but does not:

- move it to another device;
- rename it;
- disable it;
- alter its registry entry;
- remove it from its original integration;
- change its state.

### 2.7 One configuration source of truth

Thresholds are stored in the plant Config Subentry. They are displayed as read-only diagnostic sensors but edited only through the plant configuration flow.

### 2.8 Fail safely

A temporary sensor failure must not silently clear an existing watering alert.

## 3. MVP scope

Each plant is configured with:

- plant name;
- soil-moisture sensor;
- `dry_below`;
- `clear_at`.

The functional MVP supports:

- adding plants;
- editing plants;
- deleting plants;
- different thresholds per plant;
- duplicate source-sensor prevention;
- event-driven source updates;
- moisture-value validation;
- hysteresis;
- restoration of the last watering state after reload or restart;
- unavailable and invalid source states;
- one logical device per plant;
- central aggregate entities;
- five display entities per plant;
- English and German translations;
- use of all exposed entities in ordinary Home Assistant dashboards and automations.

The MVP does not include:

- a custom Lovelace card;
- a plant species database;
- pictures, notes, pot size or location metadata;
- fertilisation tracking;
- watering predictions;
- built-in push notifications;
- automatic irrigation;
- an upper “too wet” threshold;
- direct threshold editing through entities;
- ownership or relocation of source sensors.

Notifications should be implemented with ordinary Home Assistant automations.

## 4. Home Assistant integration model

### 4.1 Integration type

The manifest declares:

```json
"integration_type": "hub"
```

Plant Monitor is not implemented as a Home Assistant helper. It owns one central Config Entry, multiple Config Subentries, persistent runtime state, aggregate entities and logical plant devices.

The `hub` integration type exposes the integration under:

`Settings → Devices & services → Integrations`

### 4.2 Main Config Entry

Exactly one main Config Entry is allowed:

```json
"single_config_entry": true
```

The main entry represents the Plant Monitor service. It contains no individual plant configuration.

### 4.3 Plant Config Subentries

Each plant is represented by a native Config Subentry of type:

```text
plant
```

A plant Subentry contains:

```text
title               plant name
moisture_sensor     source sensor entity ID
dry_below           lower watering threshold
clear_at             alert-clear threshold
```

The Config Subentry ID is the stable internal plant identity.

### 4.4 Duplicate source sensors

One source moisture sensor can be assigned to only one plant.

The Config Subentry flow checks all existing plant Subentries and rejects a source entity already assigned elsewhere. During reconfiguration, the currently edited plant is excluded from that comparison.

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

### 5.3 Public status values

The public plant status is one of:

```text
ok
dry
unavailable
invalid
```

Meaning:

- `ok`: source value valid and retained watering state false;
- `dry`: source value valid and retained watering state true;
- `unavailable`: source entity missing, `unknown` or `unavailable`;
- `invalid`: source state exists but is not a valid percentage from 0 through 100.

The public status and retained watering state are intentionally separate. During a source failure, the status describes the current sensor problem while the watering state preserves the last safe watering decision.

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

This hysteresis prevents repeated switching around a single threshold.

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

For an invalid or unavailable source value:

- `status` becomes `unavailable` or `invalid`;
- projected soil moisture becomes unavailable;
- the last retained `watering_needed` value remains unchanged.

A plant that was dry therefore remains marked as requiring water if its sensor temporarily fails.

## 7. Runtime architecture

### 7.1 Manager

`PlantMonitorManager` is the central runtime object and is stored as typed Config Entry runtime data:

```python
ConfigEntry[PlantMonitorManager]
```

It is assigned to:

```python
entry.runtime_data
```

The manager owns:

- all `PlantState` objects;
- the source-entity-to-plant mapping;
- source state listeners;
- retained-state persistence;
- update callbacks for entities;
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

1. the manager validates the source value;
2. it applies the hysteresis state machine;
3. it schedules persistence if the retained watering state changed;
4. it notifies registered entities;
5. entities write their updated Home Assistant state.

### 7.3 Setup

During `async_setup_entry`:

1. plant Config Subentries are converted into `PlantConfig` objects;
2. `PlantMonitorManager` is created;
3. the manager is assigned to `entry.runtime_data`;
4. a Config Entry update listener is registered;
5. persisted watering states are restored;
6. source sensor listeners are registered;
7. current source states are evaluated;
8. binary-sensor and sensor platforms are forwarded.

### 7.4 Unload

During `async_unload_entry`:

1. entity platforms are unloaded;
2. source listeners are removed;
3. current retained watering states are saved;
4. manager listeners are cleared.

### 7.5 Reload after plant changes

Adding, editing or deleting a plant changes the main Config Entry through its Subentries.

A single update listener reloads the main Config Entry. The reconfigure flow updates the Subentry but does not independently request an additional reload.

## 8. Persistence

Only state that cannot always be reconstructed safely after restart is persisted:

```text
watering_needed by plant Config Subentry ID
```

Current moisture and public status are not persisted. They are recalculated from the source entity during startup.

Persisting by Config Subentry ID provides stable restoration if:

- the plant is renamed;
- the source sensor is replaced;
- thresholds are changed.

Stored IDs belonging to deleted plants are ignored.

## 9. Device model

### 9.1 One logical device per plant

Every plant has one logical Home Assistant device.

Its identifier is derived from:

```text
main Config Entry ID + plant Config Subentry ID
```

The device groups all Plant Monitor entities belonging to the configured plant.

The device represents a Plant Monitor service object. It does not imply that the plant itself is electronic hardware.

### 9.2 Source sensor remains independent

The selected source sensor remains attached to its original integration and original hardware device, for example an Ecowitt WH51.

Plant Monitor does not:

- move the source entity;
- attach it to the logical plant device;
- remove it from the source device;
- change its entity ID;
- claim registry ownership.

### 9.3 Reason for separation

Plant and source sensor have different lifecycles:

- a plant can receive a replacement sensor;
- a sensor can later be assigned to another plant;
- thresholds belong to the plant;
- retained watering state belongs to the plant;
- plant automations should survive hardware replacement.

Attaching Plant Monitor entities to the hardware device would couple stable plant identity to replaceable hardware.

### 9.4 Projected soil-moisture sensor

The physical source entity cannot simultaneously belong to its original hardware device and the separate logical plant device.

Plant Monitor therefore exposes a read-only projected sensor:

```text
sensor.<plant>_soil_moisture
```

It:

- mirrors the validated current source value;
- uses `%`;
- uses the moisture device class;
- uses measurement state class;
- belongs to the logical plant device;
- does not replace or modify the source entity;
- is unavailable when no valid current value exists.

This duplication is intentional only at the presentation layer.

## 10. Entity model

### 10.1 Central entities

The main Config Entry exposes:

```text
binary_sensor.plant_monitor_watering_needed
sensor.plant_monitor_dry_plants
sensor.plant_monitor_unavailable_sensors
```

Responsibilities:

- central watering-needed binary sensor: on if any retained plant watering state is true;
- dry-plants sensor: count and names of plants requiring water;
- unavailable-sensors sensor: count and entity IDs of unavailable source sensors, with invalid-source diagnostics as attributes.

### 10.2 Per-plant entities

Each logical plant device exposes five entities:

```text
sensor.<plant>_soil_moisture
sensor.<plant>_status
binary_sensor.<plant>_watering_needed
sensor.<plant>_dry_below
sensor.<plant>_clear_at
```

Displayed meaning:

```text
Soil moisture       current validated source value in %
Status              ok, dry, unavailable or invalid
Watering needed     retained decision, on or off
Dry below           configured lower threshold in %
Clear alert at      configured recovery threshold in %
```

`Dry below` and `Clear alert at` are read-only diagnostic entities. Their values are changed only through **Edit plant**.

### 10.3 Stable unique IDs

Per-plant unique IDs are derived from:

```text
main Config Entry ID + plant Config Subentry ID + entity key
```

Existing status and watering-needed unique IDs must never be changed merely to rename entities or adjust presentation.

The new entity keys are:

```text
soil_moisture
dry_below
clear_at
```

### 10.4 Entity availability

The projected soil-moisture sensor is available only when `PlantState.moisture` contains a validated numeric value.

The status and retained watering-needed entities remain available during source failures so that the failure and previous watering decision remain visible.

### 10.5 State attributes

Dynamic moisture and threshold values are not duplicated as attributes of the per-plant status and watering-needed entities.

Current per-plant attributes are intentionally limited:

- status sensor: source moisture-sensor entity ID and retained watering state;
- watering-needed binary sensor: source moisture-sensor entity ID.

The dedicated moisture and threshold entities are the canonical display surfaces for those values.

## 11. User interface

### 11.1 Installation

The current development installation flow is:

1. add the repository to HACS as a custom integration repository;
2. download Plant Monitor through HACS;
3. restart Home Assistant;
4. add the integration from `Settings → Devices & services → Integrations`.

No tagged GitHub release exists yet. Development installation currently follows the repository default branch.

### 11.2 Plant management

Inside the Plant Monitor integration page, the user can:

- select **Add plant**;
- open an existing plant Config Subentry;
- edit it;
- delete it.

The add/edit form contains:

```text
Plant name
Soil moisture sensor
Dry below
Clear alert at
```

### 11.3 Plant device display

The logical plant device shows:

- three normal entities under Sensors:
  - soil moisture;
  - status;
  - watering needed;
- two read-only threshold entities under Diagnostic:
  - dry below;
  - clear alert at.

### 11.4 Mobile-first operation

Configuration must remain practical on a phone:

- no per-plant YAML;
- no manual entity-registry changes;
- no editing of internal storage;
- no duplicate configuration surfaces;
- clear labels and validation messages;
- all plant-centred values grouped on one logical device.

A custom dashboard card remains outside the MVP.

## 12. Translations

The repository contains:

```text
custom_components/plant_monitor/translations/en.json
custom_components/plant_monitor/translations/de.json
```

Both files cover:

- initial integration setup;
- add-plant and reconfigure flows;
- validation and abort messages;
- central entity names;
- all five per-plant entity names;
- translated enum states.

English translation keys are the implementation baseline. Additional languages must preserve the same key structure.

## 13. Error handling and invariants

The implementation must preserve these invariants:

1. Exactly one main Config Entry.
2. Exactly one Config Subentry per plant.
3. Exactly one source sensor per plant.
4. The same source sensor cannot be assigned to two plants.
5. `dry_below` must be lower than `clear_at`.
6. Valid moisture percentages are restricted to 0 through 100.
7. Sensor failure does not clear retained watering state.
8. Listener registration is reversed during unload.
9. Plant entity unique IDs do not depend on plant name or source entity ID.
10. Source entities remain owned by their original integrations.
11. Thresholds are edited only through the Config Subentry flow.
12. The projected moisture entity never writes to the source entity.
13. Existing entity unique IDs remain backward compatible.
14. Presentation changes must not alter the hysteresis state machine or persistence key.

## 14. Repository structure

Current relevant structure:

```text
ha-plant-monitor/
├── .github/
│   └── workflows/
│       ├── hacs.yml
│       └── hassfest.yml
├── custom_components/
│   └── plant_monitor/
│       ├── brand/
│       │   └── icon.png
│       ├── translations/
│       │   ├── de.json
│       │   └── en.json
│       ├── __init__.py
│       ├── binary_sensor.py
│       ├── config_flow.py
│       ├── const.py
│       ├── entity.py
│       ├── manager.py
│       ├── manifest.json
│       ├── models.py
│       └── sensor.py
├── .gitignore
├── ARCHITECTURE.md
├── hacs.json
├── LICENSE
└── README.md
```

Test infrastructure, changelog and release automation are not yet present.

## 15. Validation and quality

The repository uses:

- Home Assistant hassfest validation;
- HACS repository validation.

Both workflows pass for the implemented entity model and English/German translations.

These checks validate repository and integration structure but do not replace automated behavioural tests.

### 15.1 Required automated tests

Automated coverage must include at least:

#### Watering state machine

- value below `dry_below`;
- value exactly at `dry_below`;
- value inside the hysteresis band after an OK state;
- value inside the hysteresis band after a dry state;
- value exactly at `clear_at`;
- value above `clear_at`.

#### Invalid and unavailable values

- missing source entity;
- `unknown`;
- `unavailable`;
- non-numeric state;
- NaN;
- positive and negative infinity;
- values below 0;
- values above 100;
- failure while previously dry;
- failure while previously OK.

#### Persistence and lifecycle

- retained watering-state restoration;
- renamed plant;
- replaced source sensor;
- threshold change;
- deleted plant data ignored;
- full unload and listener cleanup;
- reload after add, edit and delete.

#### Config flow

- single main Config Entry;
- add plant;
- reconfigure plant;
- delete plant;
- invalid threshold combinations;
- duplicate sensor rejection;
- current plant excluded from duplicate check during reconfiguration.

#### Entities

- creation of all central entities;
- creation of all five per-plant entities;
- stable unique IDs;
- correct logical plant-device association;
- projected moisture value and availability;
- diagnostic threshold values;
- aggregate updates;
- preservation of status and watering state during source failures;
- absence of redundant dynamic moisture and threshold attributes.

## 16. Current implementation status

### 16.1 Implemented and manually confirmed

- public GitHub repository;
- HACS custom-repository installation;
- HACS validation passing;
- hassfest validation passing;
- integration manifest version `0.1.0`;
- integration type `hub`;
- one main Config Entry;
- native plant Config Subentries;
- add, edit and delete plant support;
- duplicate sensor validation;
- runtime manager;
- event-driven source updates;
- hysteresis;
- invalid and unavailable source handling;
- retained watering-state persistence;
- one logical device per plant;
- central aggregate entities;
- per-plant projected soil-moisture sensor;
- per-plant status entity;
- per-plant watering-needed binary sensor;
- per-plant threshold display sensors;
- removal of redundant dynamic moisture and threshold attributes;
- English translations;
- German translations;
- successful installation and startup in Home Assistant;
- multiple plants created through the UI;
- all five expected entities visible on each tested plant device.

### 16.2 Not yet completed

- automated test infrastructure;
- complete automated behavioural test suite;
- final user-facing README;
- changelog;
- documented notification-automation example;
- final public naming decision;
- release process;
- first tagged GitHub release;
- HACS installation test from a tagged release.

## 17. Next implementation step

The next development step is automated test infrastructure and a first behavioural test set.

The first test increment should be deliberately limited to:

1. establish the repository test environment;
2. test the watering state machine at all threshold boundaries;
3. test invalid and unavailable input handling;
4. test retained watering-state behaviour during source failure;
5. test creation, values, availability, unique IDs and device association of all five per-plant entities;
6. run tests in GitHub Actions.

This step must not change:

- the Config Entry or Config Subentry model;
- persistence keys;
- device identifiers;
- existing unique IDs;
- source sensor ownership;
- hysteresis semantics;
- entity presentation already confirmed in Home Assistant.

## 18. Deferred work

After the initial automated tests:

1. complete Config Flow, persistence and lifecycle tests;
2. replace the placeholder README with installation and operation documentation;
3. add a changelog;
4. document a normal Home Assistant notification automation;
5. decide whether the public display name should change to avoid confusion with other plant-related integrations;
6. define versioning and release procedure;
7. create the first tagged release;
8. test a clean HACS installation from that release.

## 19. Architectural decision summary

| Decision | Result |
|---|---|
| Configuration storage | Native Config Subentries |
| Main integration type | Hub |
| Number of main entries | One |
| Runtime update model | Event-driven |
| Coordinator | None |
| Polling | Disabled |
| Persistent state | `watering_needed` by Config Subentry ID |
| Plant identity | Config Subentry ID |
| Plant grouping | One logical device per plant |
| Source sensor ownership | Original integration retains ownership |
| Source sensor relocation | Not allowed |
| Moisture on plant device | Read-only projected sensor |
| Threshold display | Read-only diagnostic sensors |
| Threshold editing | Config Subentry flow only |
| Per-plant entity count | Five |
| Translation languages | English and German |
| Notifications | Ordinary Home Assistant automation |
| Custom dashboard card | Outside MVP |
| Next development priority | Automated tests |

This document is the authoritative technical reference for the Plant Monitor repository. Any architectural change must update this file in the same commit as the related code.
