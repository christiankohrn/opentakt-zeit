// Zwei Druckteile, Maße in mm. In OpenSCAD: F5 Vorschau, F6 STL.
//
// teil = 0  beide nebeneinander (nur anschauen)
// teil = 1  Unterschale  — mit der Öffnung nach oben aufs Druckbett
// teil = 2  Deckel       — Sichtseite nach unten (Fensterschnitt nach oben)

teil = 0;

$fn = 48;
wand = 2.2;
spiel = 0.35;

// Innenraum
innen_x = 70;
innen_y = 88;
innen_z = 22;

// DevKit 30-Pin (typisch 54.5 x 28). USB an der kurzen Seite.
esp_x = 55.5;
esp_y = 29.0;
usb_b = 12;
usb_h = 8;

// 1,3"-SH1106-Modul, Sichtfenster etwas kleiner als das Glas
oled_modul_x = 36;
oled_modul_y = 34;
fenster_x = 29;
fenster_y = 16;

aussen_x = innen_x + 2 * wand;
aussen_y = innen_y + 2 * wand;

module platte(x, y, z, r = 3) {
  hull() {
    for (px = [r, x - r], py = [r, y - r])
      translate([px, py, 0]) cylinder(h = z, r = r);
  }
}

// Unterschale: offener Kasten, Boden auf dem Bett, USB-Schlitz von oben
// (kein Loch in der Wand → ohne Stützen druckbar).
module unterschale() {
  difference() {
    platte(aussen_x, aussen_y, wand + innen_z, 4);
    translate([wand, wand, wand])
      cube([innen_x, innen_y, innen_z + 1]);
    // USB: Schlitz von der Oberkante runter, kurze Wand y=0
    translate([wand + 6, -1, wand + 3])
      cube([usb_b + spiel, wand + 3, innen_z]);
  }
  // Zwei Leisten, DevKit liegt dazwischen, USB zur Schlitz-Wand
  translate([wand + 6, wand + 4, wand]) {
    cube([esp_x, 2, 5]);
    translate([0, 2 + esp_y, 0]) cube([esp_x, 2, 5]);
  }
}

// Deckel: flache Platte, Fenster vorn, Lippe greift in den Kasten.
// OLED von innen gegen das Fenster kleben/legen.
module deckel() {
  difference() {
    platte(aussen_x, aussen_y, wand + 1.4, 4);
    translate([
      (aussen_x - fenster_x) / 2,
      wand + 8,
      -1
    ]) cube([fenster_x, fenster_y, wand + 4]);
  }
  // Lippe nach oben (beim Drucken: Deckel mit Fenster nach oben, Lippe nach oben)
  translate([wand + spiel, wand + spiel, wand + 1.4]) difference() {
    cube([innen_x - 2 * spiel, innen_y - 2 * spiel, 2]);
    translate([1.4, 1.4, -0.1])
      cube([innen_x - 2 * spiel - 2.8, innen_y - 2 * spiel - 2.8, 3]);
  }
  // Mulde für das OLED-Modul (innen, um das Fenster)
  translate([
    (aussen_x - oled_modul_x) / 2 - 0.6,
    wand + 5,
    wand + 1.4
  ]) difference() {
    cube([oled_modul_x + 1.2, oled_modul_y + 1.2, 3]);
    translate([0.6, 0.6, 0.8]) cube([oled_modul_x, oled_modul_y, 4]);
    translate([
      (oled_modul_x + 1.2 - fenster_x) / 2,
      3,
      -1
    ]) cube([fenster_x, fenster_y, 6]);
  }
}

if (teil == 1) {
  unterschale();
} else if (teil == 2) {
  deckel();
} else {
  unterschale();
  translate([aussen_x + 12, 0, 0]) deckel();
}
