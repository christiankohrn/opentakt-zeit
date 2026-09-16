# Gehäuse drucken

Zwei Teile, kein zusammengebautes Modell. In OpenSCAD siehst du bei `teil = 0` **Unterschale links** und **Deckel rechts** — das Rechteck daneben ist der Deckel, nichts Schwebendes im Kasten.

```
        Unterschale                         Deckel
   ┌─────────────────┐                 ┌─────────────────┐
   │                 │  Öffnung oben   │     [OLED]      │  Fenster
   │  == ESP32 == USB│                 │                 │
   │                 │                 │   RC522 (3,3V)   │
   └─────────────────┘                 └─────────────────┘
```

1. [OpenSCAD](https://openscad.org/) öffnen, `housing.scad` laden.
2. Zeile `teil = 1;` setzen → **Render (F6)** → STL speichern als `unterschale.stl`.
3. `teil = 2;` → Render → `deckel.stl`.
4. Cura/PrusaSlicer, PETG oder PLA, 0,2 mm, 15–20 % infill.
   - Unterschale: so liegen lassen (Boden auf dem Bett). USB-Schlitz geht von oben runter, **keine Stützen**.
   - Deckel: so liegen lassen (große Fläche auf dem Bett).
5. ESP32 in die zwei Leisten legen, USB zum Schlitz. OLED von innen in die Mulde am Deckel, Display durchs Fenster. Deckel draufdrücken (Lippe).

RFID-Leser unter die freie Deckelhälfte, **Antenne nach außen** (nicht gegen das ESP32-Blech). Nur **3,3 V**. Pinbelegung: [`../README.md`](../README.md#anschluss). RC522 etwa 40×60 mm, passt in den Innenraum (70×88 mm). Grove NFC (PN532) statt RC522, nicht beide. 125 kHz-Grove wurde getestet und verworfen.
