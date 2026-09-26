/*
ESP32-Terminal-Gehaeuse Version 2 (Wandleser). Parametrisiert, ungetestet.

Masse gegenueber dem gedruckten Prototyp Version 1 (housing.scad) leicht
korrigiert. Noch nicht nachgedruckt. Weitere Anpassungen folgen.

Platz fuer ein DevKit mit Stiftleisten und Kabeln ist eingeplant (esp_abstand).
Das reicht zum Aufbau und Testen. Fuer den produktiven Einsatz nicht
empfohlen: spaeter flachere Montage ohne lange Pins.

Keine Bibliotheken erforderlich. Nur diese Datei in OpenSCAD oeffnen.

BEDIENUNG
  F5 = farbige Vorschau; F6 = berechnete Druckgeometrie ohne Elektronik.
  Im Customizer 'ansicht' waehlen. Fuer STL 'front' oder 'rueckteil', dann F6.
  'front_innen' zeigt Front samt OLED und Antenne von der Montageseite.
  Rueckteil: Boden auf Druckbett. Front: Aussenseite auf Druckbett.

RICHTUNGEN
  X nach rechts, Y nach oben an der Wand, Z von Wand zum Benutzer.
  Positionen beziehen sich auf die AUSSENKANTEN des Gehaeuses (links/unten).
  Front wird fuer den Druck umgekehrt gezeigt: ihre Innenseite zeigt nach +Z.
  'esp_abstand' ist Innenboden -> PCB-Unterseite, NICHT Gesamthoehe ab Druckbett.

BESTAETIGT
  ESP32: 55.88 x 27.83; symmetrisches Lochbild 51.5 x 24; unten 22 Freiraum.
  USB-C: Ueberstand 1.5; Buchse 3 hoch ab PCB-Oberseite; Steckerhuelle 12 x 8.
  Grove: EAGLE v1.1, Bohrungen 2.2, Koordinaten (-10,-10),(-10,10),(20,0).
    Quelle: https://raw.githubusercontent.com/SeeedDocument/Grove-NFC/master/res/Grove-NFC_v1.1.zip
    20-mm-Abstand vom Nutzer bestaetigt. Unterseite flach. Keine Schienen mehr,
    sondern drei M2-Schraubdome. PCB-Kontur in Vorschau nur angenaehert.
  Antenne: 28.5 breit x 31 hoch x 1 dick, bei lesbarer Schrift.
  OLED: PCB 36 x 34 x 3 gesamt; Lochbild 30.5 x 28.5. Fenster jetzt nach STL.

BEWUSST VORLAEUFIG
  OLED-Fenster und 45-Grad-Fase nach bereitgestelltem 13_Display_Frame_v1.stl
  parametrisch rekonstruiert (kein STL-Import erforderlich). Engstelle 31.494 x
  17.35, aussen 33.894 x 19.75; Fensterzentrum 1.67 unter Lochbildmitte.
  Lochbild bleibt nach Nutzermessung 30.5 x 28.5 statt STL 30.45 x 28.4.
  M2-Schrauben sind Standard. Schmelzzapfen optional, vorher Lochpassung pruefen.
  Beim Verstemmen Hitze/Druck nicht auf Glas oder PCB uebertragen; Ausbau danach
  nur durch Abtragen des Haltekopfs. Kein materialunabhaengiger Temperaturwert.
  PCB-Dicken 1.6, Glasueberstand, Grove-Steckerhuellraum und Antennen-Loetraum
  sind Annahmen. USB bewusst geraeumig. Nach Testdruck einzeln korrigieren.
  M2 fuer alle Platinen. Pilotloecher sind zum vorsichtigen Gewindeschneiden
  oder Einschrauben in Kunststoff gedacht, NICHT Durchgangsloecher/Heatsets.
  Schraubenlaenge nach PCB + Eingriff waehlen; nicht am Sacklochboden aufsetzen.
  Keine Wasserdichtung, keine Netzspannung, keine fertige Zugentlastung.

ANTENNENMONTAGE
  Von unten in L-Schienen einschieben; oben geteilter Anschlag.
  Linke Schiene unten ausgespart fuer seitlich austretendes Kabel/Loetstelle.
  Loetstellen zur Gehaeuse-Innenseite richten, nicht gegen die Front quetschen.
  Offenen Eingang mit Klebestreifen/Klebepunkt sichern (kein Schnappverschluss).
  Schienen haben kurze Ueberhaenge: Slicer/Material pruefen, Passprobe sinnvoll.
*/

/* [Ansicht und Vorschau] */
// Anzeigeart. Nur 'front' und 'rueckteil' einzeln als STL exportieren.
ansicht = "explosion"; // [explosion:Explosionsansicht, geschlossen:Zusammengebaut, innen:Rueckteil innen, front_innen:Front innen mit Bauteilen, druck:Beide Druckteile, rueckteil:Nur Rueckteil, front:Nur Front]
// Vereinfachte Elektronik nur in F5; niemals Teil des STL-Exports.
bauteile_anzeigen = true;
// Zusaetzlicher Abstand der Front in der Explosionsansicht.
explosionsabstand = 32; // [0:1:80]

/* [Gehaeuse] */
// Aussenbreite links -> rechts. Bauteil-X-Positionen bleiben bei Aenderung fix.
breite = 90; // [85:1:140]
// Aussenhoehe unten -> oben. Bauteil-Y-Positionen bleiben bei Aenderung fix.
hoehe = 140; // [135:1:190]
// Gesamttiefe INKLUSIVE Front und Boden. 40 bietet Platz fuer 22-mm-ESP-Dome.
tiefe = 40; // [38:1:65]
// Materialstaerke der umlaufenden Seitenwaende.
wand = 2; // [1.6:0.2:3.2]
// Dicke der Rueckwand (liegt beim Druck unten).
boden = 2.4; // [2:0.2:4]
// Dicke der Frontplatte, auch zwischen NFC-Antenne und Benutzer.
front_dicke = 2; // [1.6:0.2:3]
// Radius der vier aeusseren Gehaeuseecken, nicht Durchmesser.
eckenradius = 6; // [5:1:10]
// Spiel PRO SEITE zwischen Zentrierrand und Gehaeuse; auch Antennen-Seitenspiel.
passspiel = 0.35; // [0.2:0.05:0.7]
// Wie weit die umlaufende Zentrierlippe von der Front ins Rueckteil ragt.
zentrierrand_hoehe = 3;
// Materialdicke dieser Zentrierlippe.
zentrierrand_dicke = 1.2;

/* [ESP32 - gemessene Geometrie] */
// Lange PCB-Kante; steht eingebaut senkrecht, USB nach unten.
esp_laenge = 55.88;
// Kurze PCB-Kante; liegt eingebaut horizontal.
esp_breite = 27.83;
// Reine Leiterplattendicke ohne Bauteile; bisher angenommen.
esp_pcb_dicke = 1.6;
// Mitte-Mitte entlang langer PCB-Kante. Lochbild ist symmetrisch bestaetigt.
esp_lochabstand_laengs = 51.5;
// Mitte-Mitte entlang kurzer PCB-Kante.
esp_lochabstand_quer = 24;
// Gewuenschter Abstand Innenboden -> PCB-Unterseite, INKLUSIVE Kabelreserve.
esp_abstand = 22; // [22:1:32]
// Minimal benoetigter Freiraum laut Messung; keine weitere Reserve aufaddiert.
esp_freiraum_min = 22;
// X-Position der ESP-Platinenmitte ab linker Gehaeuseaussenkante.
esp_x = 28;
// Zusaetzliche Luft zwischen USB-Buchsenvorderkante und innerer Gehaeusewand.
// PCB-Abstand zur Wand wird daraus UND aus 'usb_ueberstand' berechnet.
esp_usb_wandluft = 0.5;
// Durchmesser der tragenden M2-Abstandshalter.
esp_dom_d = 5;
// M2-Vorbohrung: Drucktoleranz pruefen, bei Bedarf vorsichtig aufreiben/tappen.
esp_pilot = 1.7;
// Einschraubtiefe ab Oberseite der ESP-Dome; Bohrung bleibt blind.
esp_bohrtiefe = 6;
// Groesste Bauteilhoehe ab PCB-Oberseite als angenommene Platzreserve.
esp_bauteilraum = 5;
// NUR Vorschau: Hoehe der goldenen Pin-/Buchsenhuellen unter der Platine.
esp_pin_vorschau = 20;

/* [USB-C unten - grosszuegige erste Passprobe] */
// Einziger Kabel-/Portdurchbruch des Gehaeuses. Wand-Schraubloecher bleiben.
usb_oeffnung = true;
// Tatsachliche Steckerummantelung: Breite, nicht nur Metallstecker.
usb_stecker_b = 12;
// Tatsachliche Steckerummantelung: Hoehe.
usb_stecker_h = 8;
// Gesamtzugabe zur Breite (2 bedeutet links UND rechts jeweils 1).
usb_zugabe_b = 2;
// Gesamtzugabe zur Hoehe (2 bedeutet oben UND unten jeweils 1).
usb_zugabe_h = 2;
// Gemessener Ueberstand der Buchse ueber die untere kurze PCB-Kante.
usb_ueberstand = 1.5;
// Gemessene Hoehe der Buchse ab PCB-Oberseite; Buchse sitzt direkt darauf.
usb_buchse_h = 3;
// Nach Testdruck: Ausschnitt nach oben (+) oder unten (-) entlang Z korrigieren.
usb_z_korrektur = 0;

/* [Grove PN532 - dreipunktige M2-Befestigung] */
// Grundkoerper ohne gerundete Laschen. Langseite steht im Gehaeuse senkrecht.
nfc_laenge = 40;
// Breite Grundkoerper ohne Laschen.
nfc_breite = 20;
// Reine Leiterplattendicke, angenommen; Unterseite laut Nutzer flach.
nfc_pcb_dicke = 1.6;
// Platinenmittelpunkt von links gemessen.
nfc_x = 22;
// Platinenmittelpunkt von unten gemessen. Grove-Stecker zeigt nach oben.
nfc_y = 84;
// Innenboden -> PCB-Unterseite. Freiraum auch fuer Schraubdom-Sackloecher.
nfc_abstand = 5;
// Durchmesser jedes M2-Schraubdoms.
nfc_dom_d = 4.4;
// M2-Pilotloch, kein Durchgangsloch; muss zum Druck/Schraubenmaterial passen.
nfc_pilot = 1.7;
// Bohrtiefe ab Domoberseite.
nfc_bohrtiefe = 4;
// Original-Bohrung in der Grove-Platine laut Herstellerdatei (nur Vorschau).
nfc_pcb_loch_d = 2.2;
// Platz nach aussen ab oberer PCB-Grundkante: Nutzer ca. 10, plus Reserve unten.
nfc_steckerraum = 10;
// Extra Platz fuer Biegen des Kabels; noch nicht vermessen, bewusst reserviert.
nfc_kabelreserve = 4;
// Angenommene Breite des eingesteckten Grove-Steckers (nur Freiraum/Vorschau).
nfc_stecker_b = 12;
// Angenommene Steckerhoehe ab PCB-Oberseite (nur Freiraum/Vorschau).
nfc_stecker_h = 8;

/* [NFC-Antenne - Einschub mit Kabelauslass] */
// Bei lesbarer Schrift: links -> rechts, endgueltig vom Nutzer korrigiert.
antenne_breite = 28.5;
// Bei lesbarer Schrift: unten -> oben.
antenne_hoehe = 31;
// Dicke am Rand, OHNE auftragende Kabel-/Loetstellen.
antenne_dicke = 1;
// Position der Antennenmitte ab linker Gehaeuseaussenkante.
antenne_x = 63;
// Position der Antennenmitte ab unterer Gehaeuseaussenkante.
antenne_y = 66;
// Luft zwischen Antennenplatte und innerer Frontflaeche.
antenne_frontabstand = 0.2;
// Zusaetzliche Hoehe in der Einschubnut ueber Antennenplatte.
antenne_dickenspiel = 0.35;
// Wie weit die obere Schienenlippe ueber die Antennenkante greift.
antenne_randuebergriff = 1;
// Materialstaerke der oberen Schienenlippe, senkrecht zur Front.
antenne_lippe_dicke = 1.2;
// Materialstaerke der seitlichen Schienenwand.
antenne_schienenwand = 1.2;
// Laenge der unten links fehlenden Schiene fuer Kabel/Loetstelle, vorlaeufig.
antenne_kabel_freiraum = 10;
// Abstand zwischen den beiden oberen Anschlagstuecken (Zugang/Reserve).
antenne_anschlag_luecke = 12;

/* [OLED - M2, Fenster nach Testdruck feinjustieren] */
// PCB-Aussenbreite horizontal, ohne Kabel.
oled_breite = 36;
// PCB-Aussenhoehe vertikal, ohne Kabel.
oled_hoehe = 34;
// Reine PCB-Dicke angenommen; Glasdicke folgt aus Gesamtdicke minus PCB.
oled_pcb_dicke = 1.6;
// Bisher genanntes Gesamtmass PCB + Glas, Anschluesse NICHT enthalten.
oled_gesamt_dicke = 3;
// PCB-Mitte nach rechts (+) oder links (-) relativ zur Gehaeusemitte.
oled_x_versatz = 0;
// PCB-Mitte von unterer Gehaeuseaussenkante gemessen.
oled_y = 112;
// Gemessener horizontaler Abstand der Lochmitten; mittig zur PCB angenommen.
oled_lochabstand_x = 30.5;
// Gemessener vertikaler Abstand der Lochmitten; mittig zur PCB angenommen.
oled_lochabstand_y = 28.5;
// Engste lichte Fensterbreite hinter der Fase, aus Referenz-STL rekonstruiert.
oled_fenster_b = 31.494;
// Engste lichte Fensterhoehe hinter der Fase, aus Referenz-STL rekonstruiert.
oled_fenster_h = 17.35;
// Aufweitung PRO SEITE nach aussen. Aussenbreite = Fensterbreite + 2 * Wert.
oled_fase_breite = 1.2;
// Tiefe der Schraege von AUSSEN nach innen; gleicher Wert wie Breite = 45 Grad.
oled_fase_tiefe = 1.2;
// Schrauben fuer Testdruck; alternative massive Zapfen zum thermischen Verformen.
oled_befestigung = "schrauben"; // [schrauben:M2-Schrauben, schmelzzapfen:Schmelzzapfen]
// Tatsachlichen freien PCB-Lochdurchmesser hier eintragen; 2.2 konservative Annahme.
oled_pcb_loch_d = 2.2;
// Diametrales Spiel: Zapfendurchmesser = PCB-Lochdurchmesser minus dieses Mass.
oled_zapfen_spiel = 0.3;
// Materialueberstand hinter der PCB zum Formen des Haltekopfs; Materialtest noetig.
oled_zapfen_ueberstand = 1.5;
// Fenster relativ zur PCB-Mitte nach rechts (+) oder links (-) verschieben.
oled_fenster_versatz_x = 0;
// Fenster relativ zur PCB-Mitte nach oben (+) oder unten (-) verschieben.
oled_fenster_versatz_y = -1.67;
// Front-INNENflaeche -> PCB-Vorderseite; Dome tragen PCB, NICHT Displayglas.
oled_abstand = 4;
// Schlanke Dome: 4 mm lassen das grosse Fenster zwischen den Lochreihen frei.
oled_dom_d = 4;
// M2-Pilotbohrung. Alle Platinen nutzen damit M2, keine M3 fuer OLED noetig.
oled_pilot = 1.7;
// Sackloch-Einschraubtiefe; Bohrung endet oberhalb der eigentlichen Frontplatte.
oled_bohrtiefe = 3.5;
// NUR Vorschau: Raum hinter der OLED-PCB fuer Anschluss/Kabel, noch angenommen.
oled_kabelraum = 6;

/* [Gehaeuseschrauben und Wandmontage] */
// Abstand der vier Gehaeuse-Schraubachsen von ihren benachbarten Aussenkanten.
gehaeuse_schraubrand = 8;
// Durchmesser der hohen Dome fuer Front/Rueckteil-Verschraubung.
gehaeuse_dom_d = 8;
// Pilotloch fuer Gehaeuseschrauben (z.B. M3, vor Druck testen), NICHT PCB-M2.
gehaeuse_pilot = 2.5;
// Durchgangsloch in der Front fuer diese Gehaeuseschrauben.
gehaeuse_durchgang = 3.4;
// Blindbohrtiefe im Rueckteil ab Oberkante der Gehaeusedome.
gehaeuse_bohrtiefe = 10;
// Durchmesser der beiden Schraubloecher fuer Befestigung an der Wand.
wandloch_d = 4.5;
// Untere Wandbefestigung: Y ab unterer Gehaeusekante, X liegt mittig.
wandloch_y_unten = 47;
// Obere Wandbefestigung: Y ab unterer Gehaeusekante, X liegt mittig.
wandloch_y_oben = 91;
// Materialverstaerkung um die Wandloecher, Durchmesser.
wandloch_auflage_d = 11;
// Zusaetzliche Auflagenhoehe auf der Innenseite des Bodens.
wandloch_auflage_h = 1.5;

/* [Hidden] */
// Ab hier automatisch berechnete Groessen: normalerweise NICHT bearbeiten.
$fn=48;                     // Kreisaufloesung, 48 Segmente fuer Druckgeometrie.
eps=0.02;                   // Winzige Ueberlappung fuer robuste boolesche Operationen.
schale_h=tiefe-front_dicke;
esp_y=wand+usb_ueberstand+esp_usb_wandluft+esp_laenge/2;
esp_z=boden+esp_abstand;
esp_loch_x=esp_lochabstand_laengs/2;
esp_loch_y=esp_lochabstand_quer/2;
usb_breite=usb_stecker_b+usb_zugabe_b;
usb_hoehe=usb_stecker_h+usb_zugabe_h;
usb_z=esp_z+esp_pcb_dicke+usb_buchse_h/2+usb_z_korrektur;
oled_x=breite/2+oled_x_versatz;
oled_glas_h=oled_gesamt_dicke-oled_pcb_dicke;
antenne_nut_z=front_dicke+antenne_frontabstand+antenne_dicke+antenne_dickenspiel;
antenne_nut_b=antenne_breite+2*passspiel;
antenne_nut_h=antenne_hoehe+2*passspiel;
schraubpunkte=[for(x=[gehaeuse_schraubrand,breite-gehaeuse_schraubrand],y=[gehaeuse_schraubrand,hoehe-gehaeuse_schraubrand]) [x,y]];
// Original-EAGLE-Koordinaten; NICHT aus Foto geschaetzt. Lokale X-Achse = lange PCB-Kante.
nfc_lochpunkte=[[-10,-10],[-10,10],[20,0]];

// Abbruch bei bekannten unmoeglichen Einstellungen statt stillen Kollisionen.
assert(esp_abstand>=esp_freiraum_min,"ESP32: mindestens 22 mm inkl. Kabelreserve erforderlich.");
assert(esp_z+esp_pcb_dicke+esp_bauteilraum<schale_h-zentrierrand_hoehe,"ESP32 zu hoch: tiefe vergroessern.");
assert(breite>=85 && hoehe>=135,"Dieses Layout benoetigt mindestens 85 x 135 mm.");
assert(eckenradius>wand+passspiel+zentrierrand_dicke,"Eckenradius zu klein fuer Zentrierlippe.");
assert(esp_x-esp_breite/2>gehaeuse_schraubrand+gehaeuse_dom_d/2+0.5,"ESP32 kollidiert links mit Gehaeuse-Schraubdom.");
assert(esp_y+esp_laenge/2+0.5<nfc_y-20-nfc_dom_d/2,"ESP32/Grove: Abstand in Y vergroessern.");
assert(nfc_y+nfc_laenge/2+nfc_steckerraum+nfc_kabelreserve<hoehe-wand,"Grove-Stecker/Kabel zu nah an oberer Wand.");
assert(oled_y+oled_hoehe/2+1<hoehe-wand,"OLED zu nah an oberer Wand.");
assert(oled_glas_h>0 && oled_abstand>oled_glas_h,"OLED-Glas drueckt gegen Front, oled_abstand erhoehen.");
assert(oled_fase_tiefe>0 && oled_fase_tiefe<front_dicke && oled_fase_breite>=0,"Fase muss flacher als Frontdicke sein.");
assert(oled_befestigung=="schrauben" || oled_befestigung=="schmelzzapfen","Unbekannte OLED-Befestigung.");
assert(oled_pcb_loch_d>oled_zapfen_spiel && oled_zapfen_spiel>0 && oled_zapfen_ueberstand>0,"Zapfen benoetigen positives Spiel und Ueberstand.");
assert(oled_dom_d>oled_pcb_loch_d,"OLED-Auflage muss breiter als PCB-Bohrung sein.");
assert(oled_fenster_h/2+abs(oled_fenster_versatz_y)+oled_dom_d/2+0.1<oled_lochabstand_y/2,"Fenster trifft OLED-Dome. Fensterhoehe/Versatz verkleinern.");
assert(antenne_x+antenne_nut_b/2+antenne_schienenwand<breite-wand-passspiel,"Antennenhalter trifft Seitenwand.");
assert(antenne_dicke>0 && antenne_dickenspiel>0,"Antennendicke/Nutspiel muessen positiv sein.");
assert(antenne_kabel_freiraum>0 && antenne_kabel_freiraum<antenne_hoehe/2,"Kabelauslass zu lang: linke Fuehrung fehlt.");
assert(antenne_anschlag_luecke<antenne_breite-4,"Zu wenig Platz fuer oberen Antennenanschlag.");
assert(esp_bohrtiefe<esp_abstand && nfc_bohrtiefe<nfc_abstand && oled_bohrtiefe<oled_abstand,"Blindbohrung darf nicht durch Boden/Front gehen.");

// Ab hier Geometriebausteine. Einzelne Module koennen in Pruefdateien benutzt werden.
module rundplatte(w,h,z,r) {
    linear_extrude(height=z) hull()
        for(x=[r,w-r],y=[r,h-r]) translate([x,y]) circle(r=r);
}
module rect_center(w,h,z) { translate([-w/2,-h/2,0]) cube([w,h,z]); }
module esp_position() { translate([esp_x,esp_y,0]) rotate([0,0,-90]) children(); }
module esp_punkte() {
    esp_position() for(x=[-esp_loch_x,esp_loch_x],y=[-esp_loch_y,esp_loch_y])
        translate([x,y,0]) children();
}
// Original-Platine: Grove-Stecker links; nach -90 Grad zeigt er nach oben.
module nfc_position() { translate([nfc_x,nfc_y,0]) rotate([0,0,-90]) children(); }
module nfc_punkte() { nfc_position() for(p=nfc_lochpunkte) translate([p[0],p[1],0]) children(); }
module oled_punkte() {
    for(x=[-oled_lochabstand_x/2,oled_lochabstand_x/2],y=[-oled_lochabstand_y/2,oled_lochabstand_y/2])
        translate([oled_x+x,oled_y+y,0]) children();
}
module rueckteil() {
    difference() {
        union() {
            difference() {
                rundplatte(breite,hoehe,schale_h,eckenradius);
                translate([wand,wand,boden]) rundplatte(breite-2*wand,hoehe-2*wand,schale_h,eckenradius-wand);
            }
            for(p=schraubpunkte) translate([p[0],p[1],boden-eps]) cylinder(d=gehaeuse_dom_d,h=schale_h-boden+eps);
            esp_punkte() translate([0,0,boden-eps]) cylinder(d=esp_dom_d,h=esp_abstand+eps);
            nfc_punkte() translate([0,0,boden-eps]) cylinder(d=nfc_dom_d,h=nfc_abstand+eps);
            for(y=[wandloch_y_unten,wandloch_y_oben]) translate([breite/2,y,boden-eps]) cylinder(d=wandloch_auflage_d,h=wandloch_auflage_h+eps);
        }
        for(p=schraubpunkte) translate([p[0],p[1],schale_h-gehaeuse_bohrtiefe]) cylinder(d=gehaeuse_pilot,h=gehaeuse_bohrtiefe+eps);
        esp_punkte() translate([0,0,esp_z-esp_bohrtiefe]) cylinder(d=esp_pilot,h=esp_bohrtiefe+eps);
        nfc_punkte() translate([0,0,boden+nfc_abstand-nfc_bohrtiefe]) cylinder(d=nfc_pilot,h=nfc_bohrtiefe+eps);
        for(y=[wandloch_y_unten,wandloch_y_oben]) translate([breite/2,y,-eps]) cylinder(d=wandloch_d,h=boden+wandloch_auflage_h+2*eps);
        // Einziger Port: unten, genau vor der USB-C-Buchse. Seitenwaende geschlossen.
        if(usb_oeffnung) translate([esp_x-usb_breite/2,-eps,usb_z-usb_hoehe/2]) cube([usb_breite,wand+2*eps,usb_hoehe]);
    }
}
module antennenhalter() {
    difference() {
        union() {
            for(s=[-1,1]) {
                translate([antenne_x+s*(antenne_nut_b/2+antenne_schienenwand/2),antenne_y,front_dicke-eps])
                    rect_center(antenne_schienenwand,antenne_nut_h,antenne_nut_z-front_dicke+antenne_lippe_dicke+eps);
                translate([antenne_x+s*(antenne_nut_b/2-antenne_randuebergriff/2+antenne_schienenwand/2),antenne_y,antenne_nut_z])
                    rect_center(antenne_schienenwand+antenne_randuebergriff,antenne_nut_h,antenne_lippe_dicke);
                anschlag_b=(antenne_nut_b-antenne_anschlag_luecke)/2;
                translate([antenne_x+s*(antenne_anschlag_luecke/2+anschlag_b/2),antenne_y+antenne_nut_h/2+antenne_schienenwand/2-eps,front_dicke-eps])
                    rect_center(anschlag_b,antenne_schienenwand,antenne_nut_z-front_dicke+antenne_lippe_dicke+eps);
            }
        }
        // Linke Schiene unten entfernen, NICHT die Front selbst durchbrechen.
        translate([antenne_x-antenne_nut_b/2-antenne_schienenwand-eps,antenne_y-antenne_nut_h/2-eps,front_dicke-2*eps])
            cube([antenne_schienenwand+antenne_randuebergriff+2*eps,antenne_kabel_freiraum+eps,antenne_nut_z+antenne_lippe_dicke]);
    }
}
// Aussenseite der Front liegt auf Z=0: dort ist die Oeffnung am groessten.
// Der Frustum reicht exakt bis Fasenende, dahinter bleibt ein gerader Durchlass.
module oled_ausschnitt() {
    translate([oled_x+oled_fenster_versatz_x,oled_y+oled_fenster_versatz_y,0]) {
        translate([0,0,-eps]) rect_center(oled_fenster_b+2*oled_fase_breite,oled_fenster_h+2*oled_fase_breite,eps);
        linear_extrude(height=oled_fase_tiefe,scale=[oled_fenster_b/(oled_fenster_b+2*oled_fase_breite),oled_fenster_h/(oled_fenster_h+2*oled_fase_breite)])
            square([oled_fenster_b+2*oled_fase_breite,oled_fenster_h+2*oled_fase_breite],center=true);
        translate([0,0,oled_fase_tiefe-eps]) rect_center(oled_fenster_b,oled_fenster_h,front_dicke-oled_fase_tiefe+2*eps);
    }
}
module front() {
    // Berechnete Front auch in F5: verhindert OpenCSG-Artefakte an der Fase.
    render(convexity=10)
    difference() {
        union() {
            rundplatte(breite,hoehe,front_dicke,eckenradius);
            translate([wand+passspiel,wand+passspiel,front_dicke-eps]) difference() {
                rundplatte(breite-2*(wand+passspiel),hoehe-2*(wand+passspiel),zentrierrand_hoehe+eps,eckenradius-wand-passspiel);
                translate([zentrierrand_dicke,zentrierrand_dicke,-eps])
                    rundplatte(breite-2*(wand+passspiel+zentrierrand_dicke),hoehe-2*(wand+passspiel+zentrierrand_dicke),zentrierrand_hoehe+3*eps,eckenradius-wand-passspiel-zentrierrand_dicke);
            }
            oled_punkte() translate([0,0,front_dicke-eps]) cylinder(d=oled_dom_d,h=oled_abstand+eps);
            if(oled_befestigung=="schmelzzapfen")
                oled_punkte() translate([0,0,front_dicke+oled_abstand-eps])
                    cylinder(d=oled_pcb_loch_d-oled_zapfen_spiel,h=oled_pcb_dicke+oled_zapfen_ueberstand+eps);
            antennenhalter();
        }
        oled_ausschnitt();
        for(p=schraubpunkte) translate([p[0],p[1],-eps]) cylinder(d=gehaeuse_durchgang,h=front_dicke+zentrierrand_hoehe+2*eps);
        if(oled_befestigung=="schrauben")
            oled_punkte() translate([0,0,front_dicke+oled_abstand-oled_bohrtiefe]) cylinder(d=oled_pilot,h=oled_bohrtiefe+eps);
    }
}
module front_position(extra=0) { translate([0,0,tiefe+extra]) mirror([0,0,1]) children(); }

// NUR VORSCHAU: Platinen mit echten Lochpositionen; Bauteilhuellen angenaehert.
module elektronik_hinten() {
    color("seagreen") difference() {
        esp_position() translate([0,0,esp_z]) rect_center(esp_laenge,esp_breite,esp_pcb_dicke);
        esp_punkte() translate([0,0,esp_z-eps]) cylinder(d=2.2,h=esp_pcb_dicke+2*eps);
    }
    esp_position() {
        color("silver") translate([-9,0,esp_z+esp_pcb_dicke]) rect_center(25,18,3);
        color("black") translate([-esp_laenge/2+4,0,esp_z+esp_pcb_dicke]) rect_center(8,18,0.5);
        // Buchsenlaenge/-breite nur angenaehert, Ueberstand und Hoehe gemessen.
        color("silver") translate([esp_laenge/2+usb_ueberstand-3,0,esp_z+esp_pcb_dicke]) rect_center(6,9,usb_buchse_h);
        for(s=[-1,1]) color([0.9,0.65,0.1,0.55]) translate([0,s*(esp_breite/2-3),esp_z-esp_pin_vorschau]) rect_center(esp_laenge-10,3,esp_pin_vorschau);
    }
    color("royalblue") nfc_position() translate([0,0,boden+nfc_abstand]) difference() {
        union() {
            rect_center(nfc_laenge,nfc_breite,nfc_pcb_dicke);
            for(p=nfc_lochpunkte) translate([p[0],p[1],0]) cylinder(r=2,h=nfc_pcb_dicke);
        }
        for(p=nfc_lochpunkte) translate([p[0],p[1],-eps]) cylinder(d=nfc_pcb_loch_d,h=nfc_pcb_dicke+2*eps);
    }
    color("black") translate([nfc_x,nfc_y,boden+nfc_abstand+nfc_pcb_dicke]) rect_center(10,10,2);
    color("white") translate([nfc_x,nfc_y+nfc_laenge/2-4,boden+nfc_abstand+nfc_pcb_dicke]) rect_center(nfc_stecker_b,8,nfc_stecker_h);
    color([1,0.5,0,0.3]) translate([nfc_x,nfc_y+nfc_laenge/2+(nfc_steckerraum+nfc_kabelreserve)/2,boden+nfc_abstand+nfc_pcb_dicke]) rect_center(nfc_stecker_b,nfc_steckerraum+nfc_kabelreserve,nfc_stecker_h);
}
module elektronik_front() {
    color("royalblue") difference() {
        translate([oled_x,oled_y,front_dicke+oled_abstand]) rect_center(oled_breite,oled_hoehe,oled_pcb_dicke);
        oled_punkte() translate([0,0,front_dicke+oled_abstand-eps]) cylinder(d=oled_pcb_loch_d,h=oled_pcb_dicke+2*eps);
    }
    // Unbekannte Glas-Aussenkontur vorlaeufig wie Fenster, KEIN Hersteller-CAD.
    color("black") translate([oled_x,oled_y,front_dicke+oled_abstand-oled_glas_h]) rect_center(oled_fenster_b,oled_fenster_h,oled_glas_h);
    color("cyan") translate([oled_x+oled_fenster_versatz_x,oled_y+oled_fenster_versatz_y,front_dicke+oled_abstand-oled_glas_h-0.03]) rect_center(oled_fenster_b,oled_fenster_h,0.03);
    color([1,0.5,0,0.25]) translate([oled_x,oled_y+oled_hoehe/2-3,front_dicke+oled_abstand+oled_pcb_dicke]) rect_center(12,6,oled_kabelraum);
    color("black") translate([antenne_x,antenne_y,front_dicke+antenne_frontabstand]) difference() {
        rect_center(antenne_breite,antenne_hoehe,antenne_dicke);
        translate([0,0,-eps]) cylinder(d=10,h=antenne_dicke+2*eps); // Mittelbohrung optischer Platzhalter.
    }
    // Kabelauslass unten links: Huellkoerper fuer Loetstelle/Kabel, NICHT vermessen.
    color([1,0.5,0,0.6]) translate([antenne_x-antenne_breite/2-2,antenne_y-antenne_hoehe/2+3,front_dicke+antenne_frontabstand+antenne_dicke]) rect_center(7,3,2);
}
module bauteile_hinten() { if($preview && bauteile_anzeigen) elektronik_hinten(); }
module bauteile_front() { if($preview && bauteile_anzeigen) elektronik_front(); }

if(ansicht=="rueckteil") rueckteil();
else if(ansicht=="front") front();
else if(ansicht=="front_innen") { color("gainsboro") front(); bauteile_front(); }
else if(ansicht=="druck") { rueckteil(); translate([breite+12,0,0]) front(); }
else if(ansicht=="innen") { color("gainsboro") rueckteil(); bauteile_hinten(); }
else if(ansicht=="explosion" || ansicht=="geschlossen") {
    color("gainsboro") rueckteil();
    bauteile_hinten();
    front_position(ansicht=="explosion" ? explosionsabstand : 0) {
        color([0.24,0.29,0.36,ansicht=="explosion" ? 0.55 : 1]) front();
        bauteile_front();
    }
}
else assert(false,"Unbekannte Ansicht");
