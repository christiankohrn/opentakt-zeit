# ESP32-Terminal (V1)

Eigenes Gerät: ESP32-WROOM-32, OLED **SH1106 128×64 I²C** (SDA **GPIO 21**, SCL **GPIO 22**). Kein Datafox.

Bucht **nur mit WLAN**. Ohne RFID: BOOT kurz oder Serial `TAP`. BOOT **4 s halten** öffnet wieder das Portal (Secret/WLAN). Firmware-Stand im Gerät: **2** (OTA ab dieser Version).

Gehäuse (zwei Druckteile): `[cad/README.md](cad/README.md)`.

## Firmware flashen (am einfachsten: Arduino IDE)

1. [Arduino IDE 2](https://www.arduino.cc/en/software) installieren.
2. Boardverwalter: `esp32` von **Espressif Systems** (Datei → Voreinstellungen → zusätzliche Boardverwalter-URL
  `https://espressif.github.io/arduino-esp32/package_esp32_index.json` falls sie nicht schon da ist).
3. Bibliotheksverwalter: **U8g2** (olikraus) und **ArduinoJson** (Benoit Blanchon, Version 7).
4. Board: **ESP32 Dev Module**, Port: der `COM…`, der erscheint wenn das USB-Kabel steckt (Treiber: oft CP2102 oder CH340).
5. Datei → Öffnen → `firmware/esp32-terminal/esp32-terminal.ino`.
6. **Upload** (Pfeil). Danach Serial-Monitor 115200 Baud.

Wenn Upload mit „Failed to connect“ abbricht: BOOT halten, Upload klicken, loslassen wenn „Connecting…“ steht.

OTA später: in Opentakt unter Einstellungen die gebaute `firmware.bin` hochladen (PlatformIO: `.pio/build/esp32dev/firmware.bin`) mit einer Versionsnummer **größer als 2**.

## Alternative: PlatformIO (Cursor / VS Code)

Erweiterung „PlatformIO IDE“, Ordner `firmware/esp32-terminal` öffnen, **Upload**. Oder:

```bash
pip install platformio
cd firmware/esp32-terminal
pio run -t upload
```

Port setzen z. B. `pio run -t upload --upload-port COM5`. Die Datei für OTA liegt nach `pio run` unter `.pio/build/esp32dev/firmware.bin`.

## Erster Start

1. Kein WLAN gespeichert → Access Point `opentakt-XXXX`, Passwort auf dem Display (`ot-…`).
2. Handy verbinden, Browser `http://192.168.4.1`.
3. SSID, Passwort, Server (`https://zeit.firma.de` oder `http://192.168.1.10:8000`), Secret aus den Einstellungen in Opentakt.
4. Test-UID in Personal als Transponder eintragen.
5. Speichern → Neustart. 60 s WLAN, sonst wieder AP.

## Serial

`TAP` bucht die Test-UID. `TAP AABBCC` diese UID.
