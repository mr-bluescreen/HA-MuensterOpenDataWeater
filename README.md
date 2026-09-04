# Münster Open Data Weather for Home Assistant

A Home Assistant custom integration for observations published in the City of Münster's **Stadt.Temperatur** [Open Data dataset](https://opendata.stadt-muenster.de/dataset/messdaten-der-wetterstationen-aus-dem-projekt-stadt-temperatur).

## Features

- UI-only setup with either a dynamically populated station selector or an automatic local average
- Inverse-distance weighting of the nearest geolocated stations, with configurable radius and station count
- One device per station, with current weather plus temperature, humidity, atmospheric pressure, wind speed, precipitation and illuminance sensors
- Five-minute coordinated polling (one request shared by all entities)
- Stable unique IDs, diagnostics through Home Assistant's coordinator logging, clean unload, and localized English/German UI
- No credentials, YAML, or external Python packages required

Only measurements actually supplied by a station have a value. The dataset supplies observations rather than forecasts, so the weather entity intentionally has no forecast feature or inferred condition.

## Installation

### HACS

1. Add this repository as a **Custom repository** of category **Integration** in HACS.
2. Install **Münster Open Data Weather**.
3. Restart Home Assistant.

### Manual

Copy `custom_components/muenster_weather` into the `custom_components` directory in your Home Assistant configuration, then restart Home Assistant.

## Setup

1. Open **Settings → Devices & services → Add integration**.
2. Search for **Münster Open Data Weather**.
3. Select either a station published by the portal or **Calculate local average**.
4. For the automatic mode, choose a search radius and maximum station count. The integration uses the latitude and longitude configured under Home Assistant's general settings and exposes the contributing stations and distances as entity attributes.

Add the integration again to monitor another station. A station can only be configured once.

## Data source and privacy

The integration connects directly to the City of Münster Open Data portal over HTTPS and downloads the machine-readable resource advertised by the dataset metadata. It sends no credentials or Home Assistant data. Attribution and dataset licensing remain with the [City of Münster Open Data portal](https://opendata.stadt-muenster.de/).

## Troubleshooting

If setup reports that it cannot connect, verify internet/DNS access from the Home Assistant host and check that the municipal portal is available. Existing entities become unavailable during an outage and recover automatically at the next successful update. Enable debug logging if needed:

```yaml
logger:
  logs:
    custom_components.muenster_weather: debug
```

## Development

```bash
python -m compileall custom_components tests
python -m unittest discover -s tests
```

The integration follows Home Assistant's Integration Quality Scale practices applicable to a custom, cloud-polling integration. `quality_scale.yaml` records the rule coverage. Formal Platinum status is awarded only to integrations merged into Home Assistant Core.

## Contributing and support

Please open an issue with the Home Assistant version, relevant debug logs (with private information removed), and the affected station. Pull requests and additional translations are welcome.
