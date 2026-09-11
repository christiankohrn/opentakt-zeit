# Gehäuse drucken

Zwei Teile, kein zusammengebautes Modell. In OpenSCAD siehst du bei `teil = 0` **Unterschale links** und **Deckel rechts** — das Rechteck daneben ist der Deckel, nichts Schwebendes im Kasten.

```
        Unterschale                         Deckel
   ┌─────────────────┐                 ┌─────────────────┐
   │                 │  Öffnung oben   │     [OLED]      │  Fenster
   │  == ESP32 == USB│                 │                 │
   │                 │                 │  (später RFID)  │
   └─────────────────┘                 └─────────────────┘
```

1. [OpenSCAD](https://openscad.org/) öffnen, `housing.scad` laden.
2. Zeile `teil = 1;` setzen → **Render (F6)** → STL speichern als `unterschale.stl`.
3. `teil = 2;` → Render → `deckel.stl`.
4. Cura/PrusaSlicer, PETG oder PLA, 0,2 mm, 15–20 % infill.
   - Unterschale: so liegen lassen (Boden auf dem Bett). USB-Schlitz geht von oben runter, **keine Stützen**.
   - Deckel: so liegen lassen (große Fläche auf dem Bett).
5. ESP32 in die zwei Leisten legen, USB zum Schlitz. OLED von innen in die Mulde am Deckel, Display durchs Fenster. Deckel draufdrücken (Lippe).

RFID: in V1 leer lassen. Später das Modul unter die freie Deckelhälfte kleben und ggf. die Mulde anpassen.
