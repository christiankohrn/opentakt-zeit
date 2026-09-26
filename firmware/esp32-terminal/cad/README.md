# Gehäuse drucken

OpenSCAD-Modelle für das ESP32-Terminal. [OpenSCAD](https://openscad.org/) öffnen, Datei laden, F5 Vorschau, F6 berechnen, STL exportieren. PETG oder PLA, 0,2 mm, 15–20 % infill.

Stückliste und Pins: [`../README.md`](../README.md#anschluss). Grove NFC (PN532) oder RC522, nicht beide. 125 kHz-Grove wurde getestet und verworfen.

## Version 1 — Prototyp (`housing.scad`)

Gedruckt und anhand dessen vermessen. Zwei Teile, kein zusammengebautes Modell. Bei `teil = 0` siehst du **Unterschale links** und **Deckel rechts** — das Rechteck daneben ist der Deckel, nichts Schwebendes im Kasten.

```
        Unterschale                         Deckel
   ┌─────────────────┐                 ┌─────────────────┐
   │                 │  Öffnung oben   │     [OLED]      │  Fenster
   │  == ESP32 == USB│                 │                 │
   │                 │                 │   RC522 (3,3V)   │
   └─────────────────┘                 └─────────────────┘
```

1. `housing.scad` laden.
2. Zeile `teil = 1;` setzen → **Render (F6)** → STL speichern als `unterschale.stl`.
3. `teil = 2;` → Render → `deckel.stl`.
4. Unterschale so liegen lassen (Boden auf dem Bett). USB-Schlitz geht von oben runter, **keine Stützen**. Deckel so liegen lassen (große Fläche auf dem Bett).
5. ESP32 in die zwei Leisten legen, USB zum Schlitz. OLED von innen in die Mulde am Deckel, Display durchs Fenster. Deckel draufdrücken (Lippe).

RFID-Leser unter die freie Deckelhälfte, **Antenne nach außen** (nicht gegen das ESP32-Blech). Nur **3,3 V**. RC522 etwa 40×60 mm, passt in den Innenraum (70×88 mm).

## Version 2 — Wandleser (`housing-v2.scad`)

Parametrisiert (Customizer). Maße gegenüber Version 1 leicht korrigiert. **Ungetestet — noch nicht gedruckt.** Weitere Anpassungen folgen.

Es gibt Platz für ein ESP32-DevKit **mit Stiftleisten und Kabeln**. Das ist für den Laboraufbau gedacht, **nicht für den produktiven Einsatz**. Später eine flachere Variante ohne lange Pins.

Zwei Druckteile: Rückteil und Front. Im Customizer `ansicht` wählen.

| `ansicht` | Zweck |
| --- | --- |
| `explosion` / `geschlossen` / `innen` / `front_innen` / `druck` | nur anschauen (F5, Elektronik optional) |
| `rueckteil` | STL: Rückteil, Boden auf dem Druckbett |
| `front` | STL: Front, Außenseite auf dem Druckbett |

`bauteile_anzeigen` gilt nur für F5. Vor dem STL-Export `ansicht` auf `front` oder `rueckteil` stellen und F6 — die Elektronik geht nicht mit ins STL.

Richtung: X nach rechts, Y nach oben an der Wand, Z von der Wand zum Benutzer. Parameter und Hinweise stehen im Dateikopf von `housing-v2.scad`.
