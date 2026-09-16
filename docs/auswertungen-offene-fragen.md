# Offene Fragen — Auswertungen (zweite Stufe)

Der ursprüngliche Plan lag nur im Agent-Workspace und war nach dem ersten PR nicht mehr im Repo. Dieser Katalog ist die verbindliche Liste der **noch nicht umgesetzten** Punkte. Bitte hier oder in der PR antworten; erst danach implementieren.

Nicht enthalten in der ersten Stufe (und bewusst nicht vorab gebaut):

## 1. Urlaubskonto

Wie wird der Jahresanspruch geführt?

- Gutschrift immer am 1.1. in voller Höhe, oder anteilig bei Eintritt unter Jahr?
- Teilzeit: Anspruch proportional zur Soll-Woche, oder fester Tagewert unabhängig vom Modell?
- Übertrag ins Folgejahr: unbegrenzt, gedeckelt, oder Stichtag mit Verfall?
- Unbezahlter Urlaub / Sonderurlaub: vom Konto abziehen oder eigene Buchungsart ohne Kontowirkung?

## 2. 30-Stunden-Kappe

Soll ein Kalendertag bei mehr als 30 Ist-Stunden gekappt werden (Anzeige, Konto, oder beides)? Gilt das auch für Nachtschichten über Mitternacht?

## 3. Weitere Buchungsarten

TopZeit nutzt u. a. Berufsschule, Sonderurlaub, Raucherpause, Dienstgang. Welche davon brauchen wir, und wie wirken sie auf Soll, Ist und Konto (bezahlt / unbezahlt / nur Vermerk)?

## 4. Abteilungen

Sollen Auswertungen nach Abteilung gefiltert und gruppiert werden? Wenn ja: Abteilung am Mitarbeitenden, am Arbeitsmodell, oder eigene Stammdaten mit Gültigkeitszeitraum?

## 5. Personalnummer (PNR)

Braucht jede Person eine sichtbare PNR in Listen, PDF und Lohnexport? Wer vergibt sie (manuell, fortlaufend)?

## 6. Lohnarten je Arbeitsmodell

Soll jedes Modell eine Lohnart-Bezeichnung für den Export tragen, getrennt vom Anzeigenamen? Welche Auswertungen müssen die Lohnart statt des Modellnamens zeigen?

## 7. Nachtstunden und Auto-Pause

Aktuell zählen Nachtstunden die gestempelten Intervalle **ohne** Auto-Pause. Soll Pause anteilig aus den Fenstern 20–24 / 0–4 / 4–6 herausgerechnet werden?

## 8. Journal-PDF

Erledigt in dieser Stufe: das Journal hat denselben PDF-Export wie die anderen Auswertungen (nicht nur Browserdruck).

## 9. Geburtstage / Einwilligung

Geburtstage stehen im Jubiläumskalender. Braucht die Speicherung eine dokumentierte Einwilligung (Betriebsrat / DSGVO), ein Opt-in am Stammsatz, oder reicht die optionale Erfassung?

## 10. Jubiläumsstufen

10 / 25 / 40 Jahre sind fest. Sollen Stufen konfigurierbar sein (Firma, Tarif)?

## 11. Austritte in Berichten

Aktuell erscheinen Personen nur, wenn der Beschäftigungszeitraum den Berichtszeitraum schneidet. Sollen Ausgetretene in Krankheit/Salden trotzdem mit Restwerten auftauchen, oder eine eigene Austrittsliste?

## 12. Arbeitsmodell-Name vs. Lohnart

Reicht der Modellname in Monatssalden und Journal, oder muss dort die Lohnart-Bezeichnung stehen (siehe Frage 6)?

---

Sobald die Antworten stehen, können Urlaubskonto, Kappe, Buchungsarten, Abteilungen, PNR und Lohnarten in eigenen PRs folgen.
