# API research and architecture record

## Research status (7 September 2026)

The implementation is based on the dataset resource definitions and the dedicated MapServer WFS used by the existing repository. An attempted fresh retrieval of the developer pages, dataset page, and live WFS from this build environment was blocked by its outbound CONNECT proxy (HTTP 403). Consequently, live claims that could not be revalidated are called out below rather than disguised as verified facts. Before release, maintainers should capture fresh representative responses and re-run the parser contract suite.

## Endpoints used

Both calls use `https://geo.stadt-muenster.de/mapserv/wetterstationen_serv` with WFS 1.1.0 `GetFeature`:

| Purpose | `TYPENAME` | `OUTPUTFORMAT` | Filtering |
|---|---|---|---|
| master data | `wetterstationen` | `CSV_STAMMDATEN` | none |
| latest values | `wetterstationen_aktuell` | `JSON_AKTUELL` | optional comma-separated `device_ids` |

Historical, WMS, and date-range resources are not used because Home Assistant only needs current observations. This avoids CKAN discovery and prevents historical downloads during polling.

## Relevant schema contract

The dedicated master-data representation is semicolon-delimited CSV. Its
station ID, description, latitude, and longitude columns are normalised across
the punctuation and German/English headings the endpoint has used. Decimal
commas are supported. Numeric IDs are normalised to strings, an absent optional
description falls back to the stable ID, duplicates resolve to one station, and
isolated malformed/ungeolocated rows are skipped. GeoJSON remains accepted as a
compatibility representation; Point coordinates are then interpreted in
mandatory GeoJSON order **longitude, latitude**.

The blocking regression was introduced by requesting `OUTPUTFORMAT=geojson`
and unconditionally parsing the response as JSON. The station service's
dedicated public master-data format is `CSV_STAMMDATEN`, so JSON decoding failed
before either setup mode had usable station metadata. Both modes shared that
failure: station mode failed while constructing its selector, while estimate
mode failed after submission when it first attempted station discovery.

Latest output is accepted as a JSON list, a GeoJSON `features` list, or an object containing `data`/`records`. Relevant properties are: station/device ID, timestamp, temperature in °C, relative humidity in %, heat notification/status, and per-field temperature/humidity quality. Null, empty, non-finite, malformed, out-of-range values are `None`. Unknown JSON fields are ignored. Duplicate station records resolve to the newest timestamp.

ISO-8601 offsets and `Z` are converted to UTC. The service historically emits local timestamps without an offset; those are explicitly interpreted in `Europe/Berlin` (including DST), never as the host timezone.

The quality parser accepts absent flags and explicit good values (`0`, true, `ok`, `valid`, `gültig`/`gueltig`, `good`). False, explicit bad labels, and unknown flag representations are rejected. This conservative handling prevents questionable data entering estimates. Because the official flag value table could not be retrieved through this environment, this mapping must be checked against a current upstream response/document before publishing a release.

HTTP errors/timeouts become connection errors. Invalid JSON and structural/schema failures become response errors. An invalid `device_ids` filter is expected to produce an empty record list; the corresponding individual entities become unavailable. Offline and stale stations are represented by absent/old observations rather than fabricated values.

## Architecture decisions

* Domain: `muenster_weather`; no dependency package is warranted for this small API surface.
* The fully async client accepts Home Assistant's injected shared `aiohttp.ClientSession` and owns all transport/parsing details.
* Typed immutable dataclasses cross the API boundary. The coordinator owns the setup-time station snapshot and polling.
* Config entries use `station:<device_id>` or one `local_estimate` unique ID. Renames do not affect identity; many distinct physical stations are allowed and one estimate entry is allowed.
* Individual updates filter one device ID. Estimate updates select public IDs locally and filter the latest-value request.
* IDW power 2, a 50 m exact-site cutoff, five nearest stations, a 5 km radius, 15-minute polling, and 45-minute staleness are explained in the README and isolated in `interpolation.py`.
* Exact target coordinates remain in config-entry storage because an estimate must remain stable if the global Home Assistant location changes. They are omitted from diagnostics.
* API failures are coordinator failures, giving standard one-log-then-recovery behaviour. A missing configured station raises a translated config-entry error requiring user action.

## Known limitations

The upstream network is observation-only. A categorical heat status cannot be mathematically interpolated and therefore uses the nearest reporting station. Metadata refresh currently occurs on reload/restart, not periodically. No historical entities are created. Formal Home Assistant Platinum status can only be conferred during Core review; this custom repository records its target and exceptions rather than claiming an award.

## Follow-up session (20 September 2026)

Live verification was attempted again and again blocked: direct HTTPS to
`opendata.stadt-muenster.de` and `geo.stadt-muenster.de` returned proxy-level
403s (organisation egress policy denies the CONNECT), the `WebFetch` tool
independently reported `EGRESS_BLOCKED` for both hosts, and a `web.archive.org`
fallback was also unreachable. `developers.home-assistant.io` is blocked the
same way, so the current official Quality Scale/Config Flow docs could not be
re-read either; guidance below relies on trained knowledge plus what `WebSearch`
result snippets surfaced. Per the environment's own operating rules, blocked
hosts are reported rather than retried or routed around — this is an
environment limitation, not a confirmation that the upstream API is unreachable
in production.

`WebSearch` snippets (not fetched pages) corroborate two prior assumptions and
add one new field name:
* the dataset license is confirmed as "Datenlizenz Deutschland Namensnennung
  2.0" (dl-de/by-2.0), matching the README's attribution text;
* the current-values resource is described as JSON with the most recent
  measurement per station, with a separate historical resource accepting
  station-id and `date_from`/`date_to` parameters (not used by this
  integration, consistent with "Historical data" scope decisions);
* a `device_name` field name was mentioned alongside `device_id` and
  `measurement_timestamp`. `device_name` has been added to the station-name
  alias list in `api.py` alongside the existing `description`/`bezeichnung`
  aliases; none of this could be confirmed against a live payload.

None of this reaches the bar of "inspected the live API" that the rest of this
document (and the task's verification-discipline requirement) calls for.
Treat every upstream schema claim here as inherited, best-effort, and due for
a real capture the next time this environment (or a maintainer's own machine)
has outbound access to `stadt-muenster.de`.

### What was newly verified this session

With outbound access to Münster/HA docs blocked, effort went into running the
integration for real against `pytest-homeassistant-custom-component` (the
standard custom-integration test harness) instead of hand-rolled fake modules.
The environment's PyPI mirror only resolves `homeassistant` up to `2024.3.3`
(also a hard cap, not a choice), which surfaced concrete, previously-untested
bugs — all fixed and now covered by regression tests:

* `__init__.py` used the PEP 695 `type X = ConfigEntry[...]` statement, a
  Python 3.12+ syntax error under the Python 3.11 this environment (and,
  historically, Home Assistant Core itself for some releases) runs. Replaced
  with a `TypeAlias` assignment guarded by `TYPE_CHECKING` so it degrades to a
  plain alias on cores where `ConfigEntry` is not yet `Generic`.
* `sensor.py` imported `AddConfigEntryEntitiesCallback`, which does not exist
  on Home Assistant 2024.3.3; reverted to the long-stable `AddEntitiesCallback`.
* `config_flow.py` imported `ConfigFlowResult` from `homeassistant.config_entries`,
  added to Core after 2024.3.3; now imported with a fallback to
  `homeassistant.data_entry_flow.FlowResult`.
* `MuensterWeatherOptionsFlow` was instantiated with no arguments and never
  received the config entry (`async_get_options_flow` returned
  `MuensterWeatherOptionsFlow()`), so every options-flow interaction crashed
  with `AttributeError: no attribute 'config_entry'` — a real bug, not a test
  artefact. Fixed by accepting and storing `config_entry` in `__init__`.
* `MuensterWeatherCoordinator.__init__` unconditionally passed
  `config_entry=entry` to `DataUpdateCoordinator.__init__`, a parameter added
  to Core after 2024.3.3; wrapped in a `try`/`except TypeError` fallback that
  sets `self.config_entry` manually on older cores.

The test suite was rewritten from hand-rolled fake `homeassistant`/`aiohttp`
modules onto real `hass`/`aioclient_mock`/`MockConfigEntry` fixtures (74 tests,
97% line coverage on `custom_components/muenster_weather`), `ruff check`, and
`mypy --ignore-missing-imports` all pass. Re-running this suite against a
current Home Assistant core (once one is reachable) is still recommended
before release, since the pinned 2024.3.3 core cannot exercise the
`config_entry`-aware / Generic-`ConfigEntry` code paths this integration
prefers when they are available.
