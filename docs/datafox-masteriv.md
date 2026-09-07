# Datafox MasterIV an Opentakt Zeit

Die App spricht **HTTP API Level 1**. Jedes Terminal braucht eine Route zum öffentlichen Host der Instanz (`https://zeit.firma.de`). Die optionale Datafox-Bibliothek DFCom liefern wir nicht mit; wer sie lokal bauen will, siehe unten.

Typischer Aufbau: ein oder mehrere PZE-MasterIV in unterschiedlichen Netzen, Firmware ab 04.02.x. HTTPS und HTTP-Basic-Auth hängen an der Firmware (siehe unten).

## Firmware

HTTPS und Basic Auth sind auf älteren Ständen **nicht** verfügbar:

- HTTPS erst ab Firmware **04.03.11**
- HTTP-Basic-Auth erst ab **04.03.16**

Deshalb sendet das Terminal vorerst per **HTTP** an denselben Host; nginx lässt nur den Pfad `/api/terminals/datafox` unverschlüsselt durch. Das Geheimnis steckt in der URL (`?k=…`), nicht im HTTP-Header.

Empfohlen, sobald Datafox StudioIV das Update anbietet: Geräte auf mindestens **04.03.11** heben und die Send-URL auf `https://…` umstellen.

## Zugang: Webseite oder nur Terminal

| Rolle | Webseite | Terminal |
| --- | --- | --- |
| Personal, Admin, Vorgesetzt | immer | wenn Transponder hinterlegt |
| Mitarbeiter | **ja, Standard** | wenn Transponder hinterlegt |
| Mitarbeiter, Haken „Anmeldung auf der Webseite aktivieren“ aus | nein | nur Transponder |

Mitarbeiter dürfen sich also normal in der PWA anmelden (Kommen/Gehen, eigene Zeiten). Wer nur stempeln soll, bekommt eine Transpondernummer und **keinen** Web-Zugang; das Passwort ist dann optional.

Personal kann niemanden aus der Web-Oberfläche aussperren: bei HR/Admin/Vorgesetzt bleibt der Web-Login erzwungen.

## 1. Transponder in der App eintragen

1. Als Personal anmelden → **Personal** → Person öffnen.
2. Karte **Terminal und Webseite**.
3. Transpondernummer eintragen, **genau so wie das Gerät sie sendet** (siehe unten „Nummer am Gerät lesen“).
4. Optional Web-Anmeldung abschalten.
5. **Zugang speichern**.

Ohne Transpondernummer antwortet das Terminal mit „Unbekannter Ausweis“. Die Buchung gilt am Gerät als erledigt (kein Endlos-Wiederholen), landet aber nicht in Opentakt Zeit.

## 2. Geheimnis auf dem Server

In `/etc/zeiterfassung/config.toml`:

```toml
datafox_secret = "…langes Zufallswort…"
```

Beim Update wird der Eintrag ergänzt, falls er fehlt. Den Wert nur lokal notieren, nicht ins Git.

Auslesen (auf der VM):

```bash
sudo python3 -c "import tomllib; print(tomllib.load(open('/etc/zeiterfassung/config.toml','rb'))['datafox_secret'])"
```

## 3. Datafox StudioIV — Kommunikation

An jedem Gerät gleich vorgehen (StudioIV → Gerät verbinden, Status grün **Done**).

1. Gerät öffnen → Kommunikation / HTTP (Bezeichnung je nach Studio-Version: *HTTP*, *HTTP-API* oder *Kommunikation HTTP*).
2. HTTP aktivieren, **Level 1**.
3. Methode **GET oder POST**, beides wird akzeptiert.
4. **Send-URL** (HTTP, solange Firmware < 04.03.11):

   `http://zeit.firma.de/api/terminals/datafox?k=GEHEIM`

   Nach Firmware-Update:

   `https://zeit.firma.de/api/terminals/datafox?k=GEHEIM`

   `GEHEIM` durch den Wert aus `datafox_secret` ersetzen. Kein Benutzer/Passwort, kein Zertifikat am Gerät nötig.
5. Timeout 10–15 Sekunden. Bei HTTP-2xx und Antwortbeginn `df_api=1` die Buchung **nicht** wiederholen (das ist das Normalverhalten).
6. Option **Serverantwort anzeigen** / *Server online* einschalten, damit `df_msg` auf dem Display erscheint (z. B. Vorname + Kommen).
7. Uhrzeit vom Server übernehmen (`df_time` kommt in jeder Antwort).

Die Terminal-Netze müssen Port 80 (und nach dem Firmware-Update 443) zum Server durchlassen.

## Optional: Datafox DFCom lokal bauen (nicht mitgeliefert)

Opentakt Zeit spricht die Geräte standardmäßig per **HTTP**. Die Kommunikationsbibliothek **DFCom** (`libDFCom.so`) ist Software der **Datafox GmbH**, nicht Teil dieses AGPL-Projekts. Wir legen weder Quellen noch die `.so` ins Git.

Wer DFCom später für Polling (Server holt Buchungen per TCP vom Gerät) vorbereiten will, lädt das offizielle SDK von Datafox und baut auf der Debian-Maschine:

```bash
# Produktion, als root
bash /opt/zeiterfassung/deploy/install-dfcom.sh
# → /opt/zeiterfassung/lib/libDFCom.so
```

Das Skript holt das Source-Zip **direkt von datafox.de**, prüft die SHA-256-Summe und ruft `make` auf. Es spiegelt Datafox-Code nicht. Ohne Netz das Zip selbst laden und `DFCOM_ZIP=/pfad/zur.zip` setzen.

Polling (Server holt Buchungen per TCP, typisch Port **8000**) schaltet ein Administrator unter **Einstellungen** ein. Fehlt die `.so`, bleibt HTTP-Stempeln unverändert. Polling braucht, dass der Server die Geräte per TCP erreicht (LAN oder VPN). TopZeit und Opentakt dürfen dieselben Geräte **nicht** gleichzeitig pollen.

Bestehende MasterIV mit BSS-Setup `bss_PZEMaster_Basic` bleiben unverändert (kein Studio-Rewrite). Opentakt ersetzt den Poller von TopZeit.

### Was geht beim Polling zum Terminal?

| Richtung | Inhalt |
| --- | --- |
| Terminal → Server | Datensätze der Tabelle `Stempelung` (und weiterhin `Booking` für HTTP-Setups) |
| Server → Terminal, Normalbetrieb | Bestätigung (`DFCQuitRecord`): der Datensatz wird am Gerät gelöscht. Zusätzlich die Uhrzeit. Liste `PERSONAL` (Name, Zeitkonto, genommene Urlaubstage), nur wenn sich der Inhalt geändert hat. |
| Server → Terminal, Testbetrieb | Nichts Schreibendes. Der Datensatz bleibt liegen. Die Personalliste wird nicht geschrieben. |
| Nicht | Resturlaub (Anspruch), Kranktage, andere Listen (`ABWESENHEIT`, `AUFTRAG`, …) |

`Stempelung.Kennzeichen`: **0 = Kommen, 1 = Gehen**. Das ist nicht dasselbe wie HTTP-`fn` (dort ist 1 = Kommen). Andere Kennzeichen (Abwesenheit) werden bestätigt, aber nicht als Stempel gespeichert.

Beim **HTTP**-Stempeln kommt nach der Buchung ein kurzer Display-Text zurück (Vorname + Gleitzeit). Beim Polling steht der Name und das Zeitkonto in der Liste `PERSONAL` auf dem Gerät.

**Testbetrieb** (Haken in den Einstellungen): Buchungen werden gelesen, aber **nicht bestätigt** — sie bleiben auf dem Terminal und landen nicht in Opentakt. Datafox liefert ohne Bestätigung immer denselben ältesten Datensatz.

### Wie kommt die Mitarbeiterliste aufs Terminal?

Im Normalbetrieb schreibt Opentakt die Liste `PERSONAL` (Index 0 im BSS-Setup): `KARTE`, `NAME`, `ZKO` (Gleitzeit des Monats), `UKO` (genommene Urlaubstage im Kalenderjahr, ohne Anspruch). Nur aktive Personen mit Transponder. Die Liste wird nicht bei jedem Poll neu geflasht, sondern nur wenn sich der Inhalt geändert hat. Unter Einstellungen gibt es zusätzlich **Personalliste jetzt schreiben**.

Unbekannter Chip → keine Stempelzeile in Opentakt (im Normalbetrieb wird der Datensatz trotzdem bestätigt, damit er nicht ewig wiederholt wird).

DFCom unterliegt den Bedingungen von Datafox. Opentakt Zeit bleibt AGPL.

## 4. Datafox StudioIV — Tabelle Booking

Eine Tabelle anlegen, die bei jeder Buchung gesendet wird. Namen **exakt** so verwenden (Groß/Kleinschreibung egal, Prefix `df_col_` setzt Studio selbst):

| Feld in StudioIV | Inhalt | Beispiel |
| --- | --- | --- |
| Tabellenname | `Booking` | |
| `badge` | Transponder / Ausweis | Dezimal oder Hex |
| `fn` | Funktionstaste | `1` Kommen, `2` Gehen, `3` Pause, `4` Pause Ende |
| `timestamp` | lokale Zeit | `2026-09-05T07:32:01` |

Zusätzlich darf Studio `df_id` mitsenden (wird zur Idempotenz genutzt). Andere Spalten werden ignoriert.

Funktionstasten am MasterIV:

| Taste | Wert `fn` | Buchung |
| --- | --- | --- |
| F1 / Kommen | `1` | Kommen |
| F2 / Gehen | `2` | Gehen |
| F3 / Pause | `3` | Pause Beginn |
| F4 / Pause Ende | `4` | Pause Ende |

Ablauf am Gerät: Taste drücken, Transponder halten. Unbekannter Chip → Display „Unbekannter Ausweis“. Ungültiger Wechsel (z. B. nochmal Kommen, obwohl schon da) → Hinweis auf Deutsch, Buchung wird **nicht** doppelt gespeichert, das Gerät hakt nicht.

Nach einer gültigen Buchung zeigt das Display zwei Zeilen: Vorname und darunter z. B. `Kommen +2,5h`. Die Zahl ist das **Gleitzeit-Delta des laufenden Monats** (Ist minus Soll), dasselbe wie in der App unter Zeiten. Es wird nicht vorher aufs Gerät geladen, sondern in der HTTP-Antwort (`df_msg`) mitgeschickt.

**Nicht** auf dem Terminal per HTTP: Resturlaub, Jahresanspruch, Kranktage, Monatsübersicht als Liste. Dafür gibt es in der App Personal → Urlaub eintragen und die eigene Zeiten-Ansicht. Ein Urlaubskonto (Anspruch minus genommen) ist noch nicht modelliert. Listen/Menüs fest im MasterIV sind mit HTTP Level 1 nicht vorgesehen; beim **DFCom-Polling** schreibt Opentakt die Liste `PERSONAL` (siehe oben).

## 5. Nummer am Gerät lesen

Im StudioIV am angeschlossenen Terminal:

- Testdialog / letztes Medium, oder
- eine Testbuchung auslösen und in der HTTP-Vorschau `df_col_badge` ablesen.

Diese Zeichenkette 1:1 in der Personalkarte speichern. Leerzeichen, Doppelpunkte und Bindestriche werden beim Vergleich ignoriert; Dezimal und Hex derselben Nummer gelten als gleich.

## 6. Kurztest ohne Gerät

Von einem PC im selben Netz wie das Terminal (Secret und Host einsetzen):

```bash
curl -sS "http://zeit.firma.de/api/terminals/datafox?k=GEHEIM&df_table=Booking&df_col_badge=TESTCHIP&df_col_fn=1&df_col_timestamp=2026-09-05T08:00:00"
```

Erwartet: Text beginnt mit `df_api=1`. Unbekannter Chip → `df_msg=Unbekannter Ausweis…`. Nach hinterlegtem Transponder → Vorname und `Kommen` plus Monatssaldo, danach in der App **Anwesend**.

Falsches `k` → `Zugang verweigert`, keine Buchung. Leeres `datafox_secret` in der Config → HTTP 503, Terminals nicht aktiv.

## Fehlerbilder

| Display / Verhalten | Ursache |
| --- | --- |
| Endlos „senden…“ | Antwort war kein HTTP 2xx oder Body beginnt nicht mit `df_api=1` (URL, nginx, Secret-Config) |
| Unbekannter Ausweis | Transponder in Personal nicht gespeichert oder andere Schreibweise |
| Zugang verweigert | `?k=` stimmt nicht mit `datafox_secret` |
| Keine Anzeige der Begrüßung | In Studio „Serverantwort anzeigen“ aus |
| HTTPS-Fehler / Timeout | Firmware zu alt — HTTP-URL verwenden oder updaten |
| Webseite: „Anmeldung nur am Terminal“ | Web-Login für diese Person absichtlich aus |
