# Münster Open Data Weather

A UI-configured Home Assistant custom integration for observations from the City of Münster's **Stadt.Temperatur** public weather-station network. It is structured like a Home Assistant Core integration while remaining installable through HACS.

## Features and entities

Two setup modes are available:

* **Individual station** requests only the selected municipal `device_id`.
* **Local weather estimate** chooses public stations locally around Home Assistant's configured position and requests only those IDs. Home coordinates are never sent upstream.

Each entry creates a device with **Temperature**, **Humidity**, and **Heat status** sensors. **Observation time** (disabled by default) is diagnostic. Estimates additionally expose **Contributing stations** and **Nearest station distance** (disabled by default). This observation-only integration deliberately provides neither a forecast nor an invented weather condition.

## Installation and configuration

### HACS

Add this repository as a custom **Integration** repository, install it, restart Home Assistant, then select **Settings → Devices & services → Add integration → Münster Open Data Weather**.

### Manual

Copy `custom_components/muenster_weather` to the Home Assistant configuration directory and restart. Configuration is UI-only; YAML is unsupported.

For a station entry, select the friendly station label (which includes its stable municipal ID). For an estimate, select a radius and a maximum contributor count. Options can later change these two settings. The defaults are **5 km** and **5 stations**: five kilometres spans several typical Münster neighbourhoods without incorporating most of the opposite side of the city, while five stations prevents numerous distant observations from collectively overwhelming nearby ones.

## Calculation, refresh, and quality

Distance is calculated locally with the haversine great-circle formula. Continuous values are interpolated independently using inverse-distance weighting, `1 / distance²`. Squared decay gives neighbourhood-scale observations substantially more influence than distant ones. A station within 50 m is used directly to avoid division by zero and unrealistic amplification. Each field has its own contributor set; missing humidity never removes otherwise-valid temperature. Categorical heat status comes from the nearest station reporting it.

The coordinator polls every **15 minutes**, matching the observed quarter-hour timestamp cadence while avoiding requests that cannot yield new data. Measurements older than **45 minutes** (three expected publication periods) are excluded from estimates. One valid station is transparently returned; no valid station makes that entity unavailable. Explicit invalid quality flags, malformed values, impossible humidity/temperature values, and nulls are never converted to zero.

The integration fetches station master data once per config-entry setup and current values once per coordinator cycle. Restart/reload refreshes changed station metadata. Temporary errors use coordinator availability and recover automatically.

## Troubleshooting and removal

If setup cannot connect, verify DNS/HTTPS access from the Home Assistant host and retry; the municipal WFS occasionally undergoes maintenance. If an existing entity is unavailable, inspect **Observation time** and diagnostics. A removed physical station prevents setup with a translated config-entry error rather than silently attaching the entry to another station.

Remove the entry from **Settings → Devices & services**, then uninstall the HACS repository (or delete its directory) and restart. No cloud account or remote cleanup is needed.

## Privacy

Station coordinates and measurements are public. In estimate mode Home Assistant's latitude/longitude are read and processed only inside Home Assistant. Diagnostics omit target coordinates and include only public station IDs, counts, configuration radius, timestamps, and update status.

## Upstream data and attribution

Data source: Stadt Münster, [“Messdaten der Wetterstationen aus dem Projekt Stadt Temperatur”](https://opendata.stadt-muenster.de/dataset/messdaten-der-wetterstationen-aus-dem-projekt-stadt-temperatur). The portal identifies the open data under **Datenlizenz Deutschland – Namensnennung – Version 2.0 (dl-de/by-2-0)**; attribution remains **Stadt Münster**. This software is independently maintained and is not endorsed by the City.

See [`docs/research.md`](docs/research.md) for endpoint/schema research and [`quality_scale.yaml`](quality_scale.yaml) for the rule-by-rule quality audit. Integration source code is MIT licensed; upstream data retains its own licence.

## Development

```bash
pytest -q
python -m compileall -q custom_components tests
```

Home Assistant itself is required to run Core config-flow/entity tests. Pure API, timestamp, coordinate, distance, quality, staleness, and interpolation contracts run without Home Assistant.
