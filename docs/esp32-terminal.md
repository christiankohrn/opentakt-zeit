# ESP32-Terminal für Opentakt Zeit

Eigenes Gerät (ESP32-WROOM-32 + SH1106-OLED). **Kein Datafox**, eigene JSON-API.

Firmware und Gehäuse: [`firmware/esp32-terminal/`](../firmware/esp32-terminal/).

## Server

Das Shared-Secret stellt ein Administrator unter **Einstellungen → ESP-Terminal** ein (oder als Fallback `esp_terminal_secret` in `/etc/zeiterfassung/config.toml`). Leer = API aus.

`POST /api/terminals/esp/punch` und `POST /api/terminals/esp/hello` mit Header `X-Terminal-Key` oder `Authorization: Bearer …`.

```json
{ "badge": "CHIP", "event_id": "mindestens8zeichen", "device_id": "AABBCCDDEEFF", "fw": 2 }
```

Antwort:

```json
{ "ok": true, "line1": "Anna", "line2": "Kommen +2,5h", "kind": "in" }
```

Ohne `fn`: abwesend → Kommen, sonst Gehen (auch aus der Pause). Gleiche `event_id` wird nicht doppelt gespeichert. Die Geräte-ID (MAC) wird mitgebucht; in den Einstellungen kann man das Gerät benennen (z. B. „Eingang“), der Name steht an der Stempelung.

Displayzeilen stellt ein Administrator unter **Einstellungen** ein. Platzhalter: `{first_name}`, `{display_name}`, `{kind}`, `{flex_month}`, `{flex_total}`. Das OLED hat 21 Zeichen; längere Vorlagen werden gespeichert, auf dem Display aber abgeschnitten.

V1: das Gerät puffert **nicht**. Ohne WLAN keine Buchung.

Geräte holen alle 30 s eine Hello-Antwort: optional neues WLAN, optional Firmware-URL. Firmware-`.bin` in den Einstellungen hochladen, Versionsnummer höher als im Gerät (aktuell **2**). Erstes Aufspielen weiterhin per USB; danach OTA.

Falsches Secret: OLED **Falsches Secret**. Server nicht erreichbar (Timeout, 502, …): **Server nicht erreicht**. BOOT 4 Sekunden halten öffnet wieder das Captive-Portal.

## Gerät

Firmware flashen: [`firmware/esp32-terminal/README.md`](../firmware/esp32-terminal/README.md) (Arduino IDE).

Gehäuse: [`firmware/esp32-terminal/cad/README.md`](../firmware/esp32-terminal/cad/README.md). In OpenSCAD `teil = 1` (Unterschale) bzw. `teil = 2` (Deckel), jeweils ein STL exportieren.
