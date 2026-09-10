#include <Arduino.h>
#include <DNSServer.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <WebServer.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <U8g2lib.h>
#include <ArduinoJson.h>
#include <time.h>

namespace {

constexpr uint32_t kStaTimeoutMs = 60000;
constexpr uint8_t kSdaPin = 21;
constexpr uint8_t kSclPin = 22;
constexpr uint8_t kBootPin = 0;
constexpr uint16_t kDnsPort = 53;

U8G2_SH1106_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE);
Preferences prefs;
WebServer server(80);
DNSServer dns;

String wifiSsid;
String wifiPass;
String serverBase;
String apiSecret;
String testUid;

enum class Mode { Connecting, Station, Portal };
Mode mode = Mode::Connecting;
uint32_t staStarted = 0;
String line1 = "Opentakt";
String line2 = "Start";
uint32_t showUntil = 0;
bool bootWasHigh = true;

String apSsid() {
  uint8_t mac[6];
  WiFi.macAddress(mac);
  char buf[24];
  snprintf(buf, sizeof(buf), "opentakt-%02X%02X", mac[4], mac[5]);
  return String(buf);
}

String apPass() {
  uint8_t mac[6];
  WiFi.macAddress(mac);
  char buf[16];
  snprintf(buf, sizeof(buf), "ot-%02X%02X%02X", mac[3], mac[4], mac[5]);
  return String(buf);
}

void draw() {
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_6x13_tf);
  u8g2.drawStr(0, 14, line1.c_str());
  u8g2.drawStr(0, 32, line2.c_str());
  if (mode == Mode::Portal) {
    u8g2.setFont(u8g2_font_5x8_tf);
    String hint = "http://192.168.4.1";
    u8g2.drawStr(0, 48, hint.c_str());
    String pw = "WLAN-PW " + apPass();
    u8g2.drawStr(0, 60, pw.c_str());
  } else if (mode == Mode::Station) {
    u8g2.setFont(u8g2_font_5x8_tf);
    u8g2.drawStr(0, 56, WiFi.localIP().toString().c_str());
  }
  u8g2.sendBuffer();
}

void show(const String &a, const String &b, uint32_t ms = 0) {
  line1 = a.substring(0, 21);
  line2 = b.substring(0, 21);
  showUntil = ms ? millis() + ms : 0;
  draw();
}

void loadPrefs() {
  prefs.begin("ot", true);
  wifiSsid = prefs.getString("ssid", "");
  wifiPass = prefs.getString("pass", "");
  serverBase = prefs.getString("server", "");
  apiSecret = prefs.getString("secret", "");
  testUid = prefs.getString("uid", "TESTCHIP");
  prefs.end();
}

void savePrefs() {
  prefs.begin("ot", false);
  prefs.putString("ssid", wifiSsid);
  prefs.putString("pass", wifiPass);
  prefs.putString("server", serverBase);
  prefs.putString("secret", apiSecret);
  prefs.putString("uid", testUid);
  prefs.end();
}

String htmlPage() {
  String page;
  page.reserve(1800);
  page += F("<!DOCTYPE html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
            "<title>Opentakt Terminal</title><style>"
            "body{font-family:sans-serif;max-width:28rem;margin:1.5rem auto;padding:0 1rem}"
            "label{display:block;margin:.8rem 0 .2rem}input{width:100%;padding:.4rem;box-sizing:border-box}"
            "button{margin-top:1rem;padding:.6rem 1rem;width:100%}</style></head><body>");
  page += F("<h1>Opentakt Terminal</h1><form method='POST' action='/save'>");
  page += F("<label>WLAN-Name (SSID)</label><input name='ssid' value='");
  page += wifiSsid;
  page += F("'><label>WLAN-Passwort</label><input name='pass' type='password' value='");
  page += wifiPass;
  page += F("'><label>Server (https://zeit.firma.de)</label><input name='server' value='");
  page += serverBase;
  page += F("'><label>Secret (esp_terminal_secret)</label><input name='secret' value='");
  page += apiSecret;
  page += F("'><label>Test-UID (ohne RFID)</label><input name='uid' value='");
  page += testUid;
  page += F("'><button type='submit'>Speichern und verbinden</button></form></body></html>");
  return page;
}

void handleRoot() { server.send(200, "text/html; charset=utf-8", htmlPage()); }

void handleSave() {
  if (server.hasArg("ssid")) wifiSsid = server.arg("ssid");
  if (server.hasArg("pass")) wifiPass = server.arg("pass");
  if (server.hasArg("server")) {
    serverBase = server.arg("server");
    while (serverBase.endsWith("/")) serverBase.remove(serverBase.length() - 1);
  }
  if (server.hasArg("secret")) apiSecret = server.arg("secret");
  if (server.hasArg("uid")) testUid = server.arg("uid");
  savePrefs();
  server.send(200, "text/html; charset=utf-8",
              F("<p>Gespeichert. Das Gerät startet neu und verbindet sich mit dem WLAN.</p>"));
  delay(400);
  ESP.restart();
}

void startPortal() {
  mode = Mode::Portal;
  WiFi.mode(WIFI_AP);
  String ssid = apSsid();
  String pass = apPass();
  WiFi.softAP(ssid.c_str(), pass.c_str());
  dns.start(kDnsPort, "*", WiFi.softAPIP());
  server.on("/", handleRoot);
  server.on("/save", HTTP_POST, handleSave);
  server.onNotFound(handleRoot);
  server.begin();
  show(ssid, "AP-Modus");
}

void startSta() {
  mode = Mode::Connecting;
  staStarted = millis();
  WiFi.mode(WIFI_STA);
  WiFi.begin(wifiSsid.c_str(), wifiPass.c_str());
  show("WLAN...", wifiSsid);
}

String newEventId() {
  char buf[24];
  snprintf(buf, sizeof(buf), "%08lx%08lx", static_cast<unsigned long>(millis()), static_cast<unsigned long>(esp_random()));
  return String(buf);
}

bool punch(const String &badge) {
  if (mode != Mode::Station || WiFi.status() != WL_CONNECTED) {
    show("Kein Netz", "nicht gebucht", 2500);
    return false;
  }
  if (serverBase.isEmpty() || apiSecret.isEmpty() || badge.isEmpty()) {
    show("Config fehlt", "nicht gebucht", 2500);
    return false;
  }
  show("Senden...", badge);
  String url = serverBase + "/api/terminals/esp/punch";
  JsonDocument body;
  body["badge"] = badge;
  body["event_id"] = newEventId();
  uint8_t mac[6];
  WiFi.macAddress(mac);
  char dev[18];
  snprintf(dev, sizeof(dev), "%02X%02X%02X%02X%02X%02X", mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
  body["device_id"] = dev;
  String payload;
  serializeJson(body, payload);

  HTTPClient http;
  WiFiClient client;
  WiFiClientSecure secure;
  bool https = url.startsWith("https://");
  if (https) {
    secure.setInsecure();
    if (!http.begin(secure, url)) {
      show("HTTP Fehler", "begin", 2500);
      return false;
    }
  } else if (!http.begin(client, url)) {
    show("HTTP Fehler", "begin", 2500);
    return false;
  }
  http.setTimeout(8000);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Terminal-Key", apiSecret);
  int code = http.POST(payload);
  String resp = http.getString();
  http.end();
  if (code == 401 || code == 503) {
    show(code == 401 ? "Zugang" : "API aus", "verweigert", 3000);
    return false;
  }
  JsonDocument parsed;
  if (deserializeJson(parsed, resp)) {
    show("Antwort?", String(code), 3000);
    return false;
  }
  show(parsed["line1"] | "OK", parsed["line2"] | "", 4000);
  return parsed["ok"] | false;
}

void idleScreen() {
  if (showUntil && millis() < showUntil) return;
  showUntil = 0;
  if (mode == Mode::Station) show("Bereit", "Chip halten");
}

void handleSerial() {
  if (!Serial.available()) return;
  String cmd = Serial.readStringUntil('\n');
  cmd.trim();
  cmd.toUpperCase();
  if (cmd == "TAP" || cmd.startsWith("TAP ")) {
    String uid = testUid;
    int sp = cmd.indexOf(' ');
    if (sp > 0) uid = cmd.substring(sp + 1);
    uid.trim();
    punch(uid);
  }
}

}  // namespace

void setup() {
  Serial.begin(115200);
  pinMode(kBootPin, INPUT_PULLUP);
  u8g2.begin();
  loadPrefs();
  configTzTime("CET-1CEST,M3.5.0,M10.5.0/3", "pool.ntp.org");
  if (wifiSsid.isEmpty()) {
    startPortal();
  } else {
    startSta();
  }
}

void loop() {
  handleSerial();
  bool bootHigh = digitalRead(kBootPin) == HIGH;
  if (bootWasHigh && !bootHigh) {
    delay(30);
    if (digitalRead(kBootPin) == LOW) punch(testUid);
  }
  bootWasHigh = bootHigh;

  if (mode == Mode::Portal) {
    dns.processNextRequest();
    server.handleClient();
    return;
  }

  if (mode == Mode::Connecting) {
    if (WiFi.status() == WL_CONNECTED) {
      mode = Mode::Station;
      show("Bereit", "Chip halten");
    } else if (millis() - staStarted >= kStaTimeoutMs) {
      startPortal();
    }
    return;
  }

  if (WiFi.status() != WL_CONNECTED) {
    show("Kein Netz", "nicht gebucht", 2000);
    startSta();
    return;
  }
  idleScreen();
}
