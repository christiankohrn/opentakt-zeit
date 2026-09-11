#include <Arduino.h>
#include <DNSServer.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <Update.h>
#include <WebServer.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <U8g2lib.h>
#include <ArduinoJson.h>

namespace {

constexpr int kFwVersion = 2;
constexpr uint32_t kStaTimeoutMs = 60000;
constexpr uint32_t kHelloMs = 30000;
constexpr uint32_t kBootPortalMs = 4000;
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
uint32_t lastHello = 0;
String line1 = "Opentakt";
String line2 = "Start";
uint32_t showUntil = 0;
bool bootWasHigh = true;
uint32_t bootDownAt = 0;
bool bootLongHandled = false;
bool inFlight = false;

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

String deviceId() {
  uint8_t mac[6];
  WiFi.macAddress(mac);
  char buf[18];
  snprintf(buf, sizeof(buf), "%02X%02X%02X%02X%02X%02X", mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
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
  page.reserve(2000);
  page += F("<!DOCTYPE html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
            "<title>Opentakt Terminal</title><style>"
            "body{font-family:sans-serif;max-width:28rem;margin:1.5rem auto;padding:0 1rem}"
            "label{display:block;margin:.8rem 0 .2rem}input{width:100%;padding:.4rem;box-sizing:border-box}"
            "button{margin-top:1rem;padding:.6rem 1rem;width:100%}</style></head><body>");
  page += F("<h1>Opentakt Terminal</h1><p>Firmware ");
  page += String(kFwVersion);
  page += F(" · ");
  page += deviceId();
  page += F("</p><form method='POST' action='/save'>");
  page += F("<label>WLAN-Name (SSID)</label><input name='ssid' value='");
  page += wifiSsid;
  page += F("'><label>WLAN-Passwort</label><input name='pass' type='password' value='");
  page += wifiPass;
  page += F("'><label>Server (https://zeit.firma.de)</label><input name='server' value='");
  page += serverBase;
  page += F("'><label>Secret</label><input name='secret' value='");
  page += apiSecret;
  page += F("'><label>Test-UID (ohne RFID)</label><input name='uid' value='");
  page += testUid;
  page += F("'><button type='submit'>Speichern und verbinden</button></form>");
  page += F("<p>BOOT kurz: buchen. BOOT 4&nbsp;s halten: wieder dieses Portal.</p></body></html>");
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
  WiFi.disconnect(true, false);
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

void showHttpError(int code) {
  if (code == 401) {
    show("Falsches Secret", "", 4000);
    return;
  }
  if (code == 503) {
    show("API aus", "kein Secret", 4000);
    return;
  }
  if (code <= 0 || code == 408 || code == 502 || code == 504) {
    show("Server nicht erreicht", "", 4000);
    return;
  }
  show("Fehler", String(code), 4000);
}

struct HttpResult {
  int code = -1;
  String body;
};

HttpResult httpCall(const char *method, const String &path, const String &payload) {
  HttpResult out;
  if (serverBase.isEmpty()) return out;
  String url = serverBase + path;
  HTTPClient http;
  WiFiClient client;
  WiFiClientSecure secure;
  bool https = url.startsWith("https://");
  bool begun = false;
  if (https) {
    secure.setInsecure();
    secure.setTimeout(8);
#if defined(ESP32)
    secure.setHandshakeTimeout(8);
#endif
    begun = http.begin(secure, url);
  } else {
    client.setTimeout(8);
    begun = http.begin(client, url);
  }
  if (!begun) {
    out.code = -1;
    return out;
  }
  http.setConnectTimeout(4000);
  http.setTimeout(8000);
  http.setReuse(false);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Terminal-Key", apiSecret);
  if (strcmp(method, "GET") == 0) {
    out.code = http.GET();
  } else {
    out.code = http.POST(payload);
  }
  if (out.code > 0) out.body = http.getString();
  http.end();
  return out;
}

bool otaFromUrl(const String &url) {
  if (url.isEmpty()) return false;
  show("Update...", String("FW ") + kFwVersion);
  HTTPClient http;
  WiFiClient client;
  WiFiClientSecure secure;
  bool https = url.startsWith("https://");
  bool begun = false;
  if (https) {
    secure.setInsecure();
    secure.setTimeout(20);
#if defined(ESP32)
    secure.setHandshakeTimeout(12);
#endif
    begun = http.begin(secure, url);
  } else {
    client.setTimeout(20);
    begun = http.begin(client, url);
  }
  if (!begun) {
    show("Update fehlgeschl", "HTTP", 4000);
    return false;
  }
  http.setConnectTimeout(8000);
  http.setTimeout(25000);
  http.setReuse(false);
  http.addHeader("X-Terminal-Key", apiSecret);
  int code = http.GET();
  if (code != 200) {
    http.end();
    showHttpError(code);
    return false;
  }
  int len = http.getSize();
  if (!Update.begin(len > 0 ? static_cast<size_t>(len) : UPDATE_SIZE_UNKNOWN)) {
    http.end();
    show("Update fehlgeschl", "Flash", 4000);
    return false;
  }
  WiFiClient *stream = http.getStreamPtr();
  size_t written = Update.writeStream(*stream);
  bool ok = Update.end() && (len <= 0 || written == static_cast<size_t>(len));
  http.end();
  if (!ok) {
    show("Update fehlgeschl", "Schreiben", 4000);
    return false;
  }
  show("Update OK", "Neustart", 1500);
  delay(800);
  ESP.restart();
  return true;
}

void applyHello(JsonDocument &parsed) {
  const char *ssid = parsed["wifi_ssid"] | "";
  const char *pass = parsed["wifi_pass"] | "";
  if (ssid[0]) {
    String nextSsid = String(ssid);
    String nextPass = String(pass);
    bool change = nextSsid != wifiSsid || (nextPass.length() && nextPass != wifiPass);
    if (change) {
      wifiSsid = nextSsid;
      if (nextPass.length()) wifiPass = nextPass;
      savePrefs();
      show("WLAN neu", wifiSsid, 1500);
      delay(500);
      ESP.restart();
      return;
    }
  }
  const char *url = parsed["firmware_url"] | "";
  int remoteFw = parsed["fw"] | 0;
  if (url[0] && remoteFw > kFwVersion) {
    otaFromUrl(String(url));
  }
}

void hello() {
  if (inFlight || mode != Mode::Station || WiFi.status() != WL_CONNECTED) return;
  if (serverBase.isEmpty() || apiSecret.isEmpty()) return;
  inFlight = true;
  JsonDocument body;
  body["device_id"] = deviceId();
  body["fw"] = kFwVersion;
  body["ssid"] = wifiSsid;
  body["ip"] = WiFi.localIP().toString();
  String payload;
  serializeJson(body, payload);
  HttpResult res = httpCall("POST", "/api/terminals/esp/hello", payload);
  inFlight = false;
  lastHello = millis();
  if (res.code != 200) return;
  JsonDocument parsed;
  if (deserializeJson(parsed, res.body)) return;
  inFlight = true;
  applyHello(parsed);
  inFlight = false;
}

bool punch(const String &badge) {
  if (inFlight) return false;
  if (mode != Mode::Station || WiFi.status() != WL_CONNECTED) {
    show("Kein Netz", "nicht gebucht", 2500);
    return false;
  }
  if (serverBase.isEmpty() || apiSecret.isEmpty() || badge.isEmpty()) {
    show("Config fehlt", "nicht gebucht", 2500);
    return false;
  }
  inFlight = true;
  show("Senden...", badge);
  JsonDocument body;
  body["badge"] = badge;
  body["event_id"] = newEventId();
  body["device_id"] = deviceId();
  body["fw"] = kFwVersion;
  body["ssid"] = wifiSsid;
  String payload;
  serializeJson(body, payload);
  HttpResult res = httpCall("POST", "/api/terminals/esp/punch", payload);
  inFlight = false;
  if (res.code != 200) {
    showHttpError(res.code);
    return false;
  }
  JsonDocument parsed;
  if (deserializeJson(parsed, res.body)) {
    show("Antwort ungueltig", "", 3000);
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
  if (!bootHigh) {
    if (bootWasHigh) {
      bootDownAt = millis();
      bootLongHandled = false;
    } else if (!bootLongHandled && millis() - bootDownAt >= kBootPortalMs) {
      bootLongHandled = true;
      if (mode != Mode::Portal) startPortal();
    }
  } else if (!bootWasHigh && !bootLongHandled) {
    delay(30);
    if (digitalRead(kBootPin) == HIGH && mode == Mode::Station) punch(testUid);
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
      lastHello = 0;
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
  if (!lastHello || millis() - lastHello >= kHelloMs) hello();
  idleScreen();
}
