# ESP32-Terminal (V1)

Eigenes Stempelgerät für Opentakt Zeit. **Kein Datafox.** Firmware **1**. Bucht nur mit WLAN: Chip an den Leser halten.

## Was anschaffen

Ein Gerät besteht aus ESP32, Display und **einem** 13,56 MHz-Leser. Nicht beide Leser gleichzeitig.

| Teil | Typ, der hier läuft | Hinweis |
| --- | --- | --- |
| Board | **ESP32-WROOM-32** DevKit (30 Pin, USB) | CP2102- oder CH340-USB-Chip |
| Display | **SH1106** OLED **128×64**, I²C, 4 Pin (VCC/GND/SCL/SDA) | Nicht SSD1306 bestellen, wenn SH1106 gemeint ist |
| Leser (empfohlen, getestet) | Seeed **Grove NFC** / **GRV-NFC**, Artikel **C22-307**, Chip **PN532** | UART, 13,56 MHz, **3,3 V** |
| Leser (Alternative) | Joy-IT **SBC-RFID-RC522** | SPI, 13,56 MHz, **nur 3,3 V** |
| Transponder | 13,56 MHz (MIFARE Classic, NTAG, DESFire-UID) | Keine 125 kHz-Chips |
| Kabel | Dupont / Grove-Kabel | Kurze Leitungen, gemeinsame Masse |

Gehäuse: [`cad/README.md`](cad/README.md). Server-API: [`docs/esp32-terminal.md`](../../docs/esp32-terminal.md).

## Anschluss

Alles an **3,3 V**, nichts an 5 V / VIN. Gemeinsame GND. Ein Leser: **entweder** Grove NFC **oder** RC522.

### Display SH1106 (I²C)

| SH1106 | ESP32 DevKit | Funktion |
| --- | --- | --- |
| VCC | **3V3** | Versorgung |
| GND | GND | Masse |
| SDA | GPIO **21** | I²C-Daten |
| SCL | GPIO **22** | I²C-Takt |

RST am Display, falls vorhanden, offen lassen. Adresse üblich **0x3C**. Firmware: U8g2 `U8G2_SH1106_128X64_NONAME_F_HW_I2C`.

### Grove NFC C22-307 (PN532) — so verdrahtet es jetzt

Getestet und in Betrieb. Werksseitig UART, 115200 Baud, **kein Spannungsteiler**.

| Grove-Kabel | Bedeutung | ESP32 DevKit |
| --- | --- | --- |
| Rot | Versorgung | **3V3** (nicht 5 V) |
| Schwarz | GND | GND |
| Gelb | PN532 **TX** → ESP32 RX | GPIO **17** |
| Weiß | PN532 **RX** ← ESP32 TX | GPIO **16** (Pflicht) |

OLED unten rechts: **532 FW 1**. Serial nach dem Start: `PN532 HSU OK`. Chip halten → UID ohne Leerzeichen.

Firmware: Seeed-PN532 **Arduino-Branch**, `-DNFC_INTERFACE_HSU`, `PN532_HSU(uart2, 17, 16)`. Die Pins stehen im Konstruktor. Danach UART **nicht** noch einmal umlegen.

### Alternative: RC522 (SPI)

Nur wenn **kein** Grove NFC hängt.

| RC522 | ESP32 DevKit | Funktion |
| --- | --- | --- |
| VCC / 3.3V | **3V3** | nur 3,3 V, nicht 5 V |
| GND | GND | Masse |
| RST | GPIO **4** | Reset — **nicht** GPIO 21 (das ist OLED-SDA) |
| NSS / SDA / SS | GPIO **5** | SPI Chip-Select, nicht I²C |
| SCK | GPIO **18** | SPI-Takt |
| MOSI | GPIO **23** | ESP32 → Leser |
| MISO | GPIO **19** | Leser → ESP32 |
| IRQ | — | offen |

OLED unten rechts: **522 FW 1**. NSS heißt auf manchen Boards **SDA** oder **SS**.

### Pin-Übersicht

| GPIO | Belegung |
| --- | --- |
| 21 / 22 | OLED SDA / SCL |
| 17 / 16 | PN532 RX / TX (Gelb / Weiß) |
| 5 / 18 / 23 / 19 / 4 | RC522 NSS / SCK / MOSI / MISO / RST |
| 0 | BOOT (kurz: Test-UID, 4 s: WLAN-Portal) |

Ohne erkannten Leser zeigt das Display **--**.

---

## Betrieb

Chip an den Leser. Unten rechts dauerhaft Leser und Firmware (**532** oder **522** vor **FW**), links die IP. Beim OTA: **Flashen…** mit Balken. BOOT **4 s halten** öffnet wieder das Captive-Portal. Ohne Leser: BOOT kurz oder Serial `TAP`.

Die gelesene UID (Hex ohne Doppelpunkt) ist die Transpondernummer in Personal.

## Firmware flashen (Arduino IDE)

1. [Arduino IDE 2](https://www.arduino.cc/en/software) installieren.
2. Boardverwalter: `esp32` von **Espressif Systems** (Datei → Voreinstellungen → zusätzliche Boardverwalter-URL `https://espressif.github.io/arduino-esp32/package_esp32_index.json`, falls sie fehlt).
3. Bibliotheken: **U8g2** (olikraus), **ArduinoJson** 7 (Benoit Blanchon), **MFRC522** (Miguel Balboa), **PN532** (Seeed Studio, Branch **arduino**), **NDEF** (Don Coleman). In `platformio.ini` steht `-DNFC_INTERFACE_HSU`.
4. Board: **ESP32 Dev Module**, Port: der `COM…` mit gestecktem USB (Treiber oft CP2102 oder CH340).
5. Datei → Öffnen → `firmware/esp32-terminal/esp32-terminal.ino`.
6. **Upload**. Serial-Monitor **115200** Baud.

Wenn Upload mit „Failed to connect“ abbricht: BOOT halten, Upload klicken, loslassen wenn „Connecting…“ steht.

### PlatformIO

Erweiterung „PlatformIO IDE“, Ordner `firmware/esp32-terminal` öffnen, **Upload**. Oder:

```bash
pip install platformio
cd firmware/esp32-terminal
pio run -t upload
```

Port z. B. `pio run -t upload --upload-port COM5`. Nur bauen (OTA-Datei): `pio run` → `.pio/build/esp32dev/firmware.bin`.

## Erster Start

1. Kein WLAN gespeichert → Access Point `opentakt-XXXX`, Passwort auf dem Display (`ot-…`).
2. Handy verbinden, Browser `http://192.168.4.1`.
3. SSID, Passwort, Server (`https://zeit.firma.de` oder `http://192.168.1.10:8000`), Secret aus den Einstellungen in Opentakt.
4. Karten-UID (oder Test-UID) in Personal als Transponder eintragen.
5. Speichern → Neustart. 60 s WLAN, sonst wieder AP.

## Firmware-Datei für OTA

`pio run` (ohne `-t upload`) erzeugt:

`firmware/esp32-terminal/.pio/build/esp32dev/firmware.bin`

Das Gerät spielt ein Update nur ein, wenn die Versionsnummer auf dem Server **größer** ist als `kFwVersion` in `src/main.cpp` (aktuell **1**). OLED: **Update… / Laden…**, dann **Flashen…**, danach **Update OK** und Neustart.

1. In `src/main.cpp` `kFwVersion` höher setzen (z. B. **2**).
2. `pio run`.
3. In Opentakt unter **Einstellungen → Terminals → ESP-Terminal** die `firmware.bin` hochladen und dieselbe Versionsnummer speichern.
4. Gerät online lassen. Innerhalb von etwa 30 s Fortschritt, dann Neustart. Unten rechts die neue **FW**-Zahl.

Arduino IDE: **Sketch → Kompilierte Binärdatei exportieren**, dieselbe Datei hochladen. Ohne höhere Versionsnummer bleibt das Gerät bei der laufenden Firmware.

## Serial

Monitor **115200**. `TAP` bucht die Test-UID, `TAP AABBCC` diese UID. `PROBE` prüft RC522 und PN532 (Text tippen und Enter — das ist kein Chip). Gelesene Chips: `RFID` plus UID (RC522) oder `PN532` plus UID.

`PROBE` ohne offenen Monitor tut nichts.

## Welche Chips welcher Leser liest

**MIFARE DESFire** ist 13,56 MHz (oft 7-Byte-UID, SAK `0x20`). Zum Stempeln reicht die UID. Manche DESFire haben eine **zufällige UID** — dann unbrauchbar als Transpondernummer. 125 kHz-Chips liest dieses Terminal nicht.

| Transponder | Typ | RC522 | PN532 |
| --- | --- | --- | --- |
| Joy-IT **SBC-RFID-Clip** | 13,56 MHz, MIFARE | ja | ja |
| Berrybase **125449** (NTAG215) | 13,56 MHz, oft 7 Byte UID | ja | ja |
| **N13-450** (**KF-ABS-F08-BL**) | 13,56 MHz, F08 / Classic 1K | ja | ja |
| **MIFARE DESFire** (EV1/EV2/EV3) | 13,56 MHz, ISO 14443-4 | UID ja | UID ja |
| **RFID-TP 35** und andere 125 kHz | EM4100 / Hitag / HID | nein | nein |

NTAG oft 7 Byte UID, MIFARE Classic / F08 meist 4 Byte.

## Hinweise zum PN532

GetFirmwareVersion liefert bei lebendem Chip u. a. `D5 03 32 01 06 07` (IC `0x32`). Ohne Pins im Konstruktor legt der Treiber UART2 auf die ESP32-Defaults RX 16 / TX 17 — vertauscht zu diesem Anschluss.

```cpp
HardwareSerial pn532Serial(2);
PN532_HSU pn532Hsu(pn532Serial, 17, 16);  // ESP32 RX=17 <- Gelb, TX=16 -> Weiss
PN532 nfc(pn532Hsu);
nfc.begin();
uint32_t ver = nfc.getFirmwareVersion();
```

Kurz 5 V am Rot-Kabel zerstört das Modul nicht zwingend. 3,3 V an Gelb im Leerlauf heißt nur, dass TX lebt — ohne Weiß an GPIO 16 kommt trotzdem kein ACK.

Werksseitig UART. I²C erst nach Umsöten der Pads; Firmware scannt zusätzlich 0x24 auf dem OLED-Bus. Für I²C: Weiß→SDA 21, Gelb→SCL 22.

## Verworfen: Grove RFID 125 (C22-817)

Seeed **Grove RFID 125** / **GRV-RFID-125** wurde **getestet** (RFID-TP 35 / EM4100 funktionierte). Fürs Terminal **verworfen**: 125 kHz-Transponder und die Technik sind deutlich teurer als 13,56 MHz. Die Firmware spricht den 125er nicht mehr an.

Nur zur Dokumentation, nicht anschließen:

- Jumper **U** (UART), **9600 8N1**, Versorgung **4,75–5,25 V** an ESP32 **VIN / 5 V**.
- Gelb ist Modul-TX mit **5 V** — ESP32-Eingänge sind nicht 5 V-tolerant. Spannungsteiler: **2,2 kΩ** Gelb→GPIO 16, **3,3 kΩ** GPIO 16→GND, Pin am Mittelpunkt (~3,0 V). Weiß optional direkt an GPIO 17 (kein Teiler).
- Serial-Frames typisch 12 Hex-Zeichen, z. B. `0700952F229F` → Kartennummer `00952F22`.

```
Leser TX (gelb, 5 V)
        │
     2,2 kΩ
        │
        ├──────── GPIO 16 (ESP32 RX)     ≈ 3,0 V
        │
     3,3 kΩ
        │
       GND
```

Früherer Firmware-Parser (nicht mehr im Gerät):

```cpp
String lfUidFromRaw(const String &raw) {
  String hex;
  for (unsigned i = 0; i < raw.length(); i++) {
    char c = raw[i];
    if (c >= 'a' && c <= 'f') c = static_cast<char>(c - 32);
    if ((c >= '0' && c <= '9') || (c >= 'A' && c <= 'F')) hex += c;
  }
  if (hex.length() >= 12) return hex.substring(2, 10);
  return hex;
}

// UART2 9600 8N1, RX=GPIO16, TX=GPIO17
// Rahmenende: 0x03, CR/LF, oder 12 Hex-Zeichen, sonst Timeout ~50 ms
```
