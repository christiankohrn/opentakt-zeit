# ESP32-Terminal für Opentakt Zeit

Eigenes Gerät (ESP32-WROOM-32 + SH1106-OLED + **ein** RFID-Leser: RC522 oder Grove NFC). **Kein Datafox**, eigene JSON-API.

Firmware und Gehäuse: [`firmware/esp32-terminal/`](../firmware/esp32-terminal/).

## Server

Das Shared-Secret stellt ein Administrator unter **Einstellungen → ESP-Terminal** ein (oder als Fallback `esp_terminal_secret` in `/etc/zeiterfassung/config.toml`). Leer = API aus.

`POST /api/terminals/esp/punch` und `POST /api/terminals/esp/hello` mit Header `X-Terminal-Key` oder `Authorization: Bearer …`.

```json
{ "badge": "A1B2C3D4", "event_id": "mindestens8zeichen", "device_id": "AABBCCDDEEFF", "fw": 1 }
```

Antwort:

```json
{ "ok": true, "line1": "Anna", "line2": "Kommen +2,5h", "kind": "in" }
```

Ohne `fn`: abwesend → Kommen, sonst Gehen (auch aus der Pause). Gleiche `event_id` wird nicht doppelt gespeichert. Die Geräte-ID (MAC) wird mitgebucht; in den Einstellungen kann man das Gerät benennen (z. B. „Eingang“), der Name steht an der Stempelung.

Displayzeilen stellt ein Administrator unter **Einstellungen** ein. Platzhalter: `{first_name}`, `{display_name}`, `{kind}`, `{flex_month}`, `{flex_total}`. Das OLED hat 21 Zeichen; längere Vorlagen werden gespeichert, auf dem Display aber abgeschnitten.

V1: das Gerät puffert **nicht**. Ohne WLAN keine Buchung.

Geräte holen alle 30 s eine Hello-Antwort: optional neues WLAN, optional Firmware-URL. Firmware-`.bin` in den Einstellungen hochladen, Versionsnummer höher als im Gerät (aktuell **1**). OLED zeigt links die IP, rechts dauerhaft **522** oder **532** vor **FW …**; während OTA **Flashen…** und einen Balken. Erstes Aufspielen weiterhin per USB; danach OTA.

Falsches Secret: OLED **Falsches Secret**. Server nicht erreichbar (Timeout, 502, …): **Server nicht erreicht**. BOOT 4 Sekunden halten öffnet wieder das Captive-Portal.

## Gerät

Stückliste und Pinbelegung (Display, Grove NFC, optional RC522): [`firmware/esp32-terminal/README.md`](../firmware/esp32-terminal/README.md). Kurz:

- Display SH1106 I²C: SDA GPIO **21**, SCL GPIO **22**, 3,3 V.
- Grove NFC C22-307 (PN532, getestet): **3,3 V**, kein Teiler. Gelb → GPIO **17** (ESP32 RX), Weiß → GPIO **16** (ESP32 TX). OLED **532**.
- Alternative RC522: **nur 3,3 V**. SPI NSS→GPIO 5, SCK→18, MOSI→23, MISO→19, RST→GPIO 4. IRQ offen. OLED **522**.
- 125 kHz-Grove getestet und verworfen (teurer). Nur Doku in derselben README.
- Die gelesene UID (Hex ohne Doppelpunkt) ist die Transpondernummer in Personal. NTAG oft 7 Byte, MIFARE/F08 oft 4 Byte.

Welche Transponder welcher Leser liest: [`firmware/esp32-terminal/README.md`](../firmware/esp32-terminal/README.md#welche-chips-welcher-leser-liest).

OTA: `cd firmware/esp32-terminal && pio run` erzeugt `.pio/build/esp32dev/firmware.bin`. `kFwVersion` in der Firmware erhöhen, Datei in den Einstellungen mit **höherer** Versionsnummer hochladen. Details in derselben README.

Gehäuse: [`firmware/esp32-terminal/cad/README.md`](../firmware/esp32-terminal/cad/README.md). In OpenSCAD `teil = 1` (Unterschale) bzw. `teil = 2` (Deckel), jeweils ein STL exportieren.
