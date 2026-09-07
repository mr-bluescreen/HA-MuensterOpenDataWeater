# API research and architecture record

## Research status (7 September 2026)

The implementation is based on the dataset resource definitions and the dedicated MapServer WFS used by the existing repository. An attempted fresh retrieval of the developer pages, dataset page, and live WFS from this build environment was blocked by its outbound CONNECT proxy (HTTP 403). Consequently, live claims that could not be revalidated are called out below rather than disguised as verified facts. Before release, maintainers should capture fresh representative responses and re-run the parser contract suite.

## Endpoints used

Both calls use `https://geo.stadt-muenster.de/mapserv/wetterstationen_serv` with WFS 1.1.0 `GetFeature`:

| Purpose | `TYPENAME` | `OUTPUTFORMAT` | Filtering |
|---|---|---|---|
| master data | `wetterstationen` | `geojson` | none |
| latest values | `wetterstationen_aktuell` | `JSON_AKTUELL` | optional comma-separated `device_ids` |

Historical, WMS, and date-range resources are not used because Home Assistant only needs current observations. This avoids CKAN discovery and prevents historical downloads during polling.

## Relevant schema contract

Master data is interpreted as a GeoJSON FeatureCollection. The stable station ID is represented as `device_id` (numeric IDs are normalised to strings); station labels are read from `name`/`bezeichnung`/`standort`; Point coordinates are interpreted in mandatory GeoJSON order **longitude, latitude**. Explicit latitude/longitude properties are accepted as a resilient fallback. Invalid or ungeolocated features are ignored.

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
