# ESP32-Terminal für Opentakt Zeit

Eigenes Gerät (ESP32-WROOM-32 + SH1106-OLED). **Kein Datafox**, eigene JSON-API.

Firmware und Gehäuse: [`firmware/esp32-terminal/`](../firmware/esp32-terminal/).

## Server

In `/etc/zeiterfassung/config.toml` (leer = API aus):

```toml
esp_terminal_secret = "…"
```

`POST /api/terminals/esp/punch` mit Header `X-Terminal-Key` oder `Authorization: Bearer …`.

```json
{ "badge": "CHIP", "event_id": "mindestens8zeichen", "device_id": "optional" }
```

Antwort:

```json
{ "ok": true, "line1": "Anna", "line2": "Kommen +2,5h", "kind": "in" }
```

Ohne `fn`: abwesend → Kommen, sonst Gehen (auch aus der Pause). Gleiche `event_id` wird nicht doppelt gespeichert.

Displayzeilen stellt ein Administrator unter **Einstellungen** ein. Platzhalter: `{first_name}`, `{display_name}`, `{kind}`, `{flex_month}`, `{flex_total}`. Maximal 21 Zeichen pro Zeile.

V1: das Gerät puffert **nicht**. Ohne WLAN keine Buchung.

## Gerät

Firmware flashen: [`firmware/esp32-terminal/README.md`](../firmware/esp32-terminal/README.md) (Arduino IDE).

Gehäuse: [`firmware/esp32-terminal/cad/README.md`](../firmware/esp32-terminal/cad/README.md). In OpenSCAD `teil = 1` (Unterschale) bzw. `teil = 2` (Deckel), jeweils ein STL exportieren.
