#include <Arduino.h>
#include <cstring>
#include <DNSServer.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <Update.h>
#include <WebServer.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <U8g2lib.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <HardwareSerial.h>
#include <SPI.h>
#include <MFRC522.h>

#ifndef NFC_INTERFACE_HSU
#define NFC_INTERFACE_HSU
#endif
#include <PN532_HSU.h>
#include <PN532.h>

namespace {

constexpr int kFwVersion = 1;
constexpr uint32_t kStaTimeoutMs = 60000;
constexpr uint32_t kHelloMs = 30000;
constexpr uint32_t kBootPortalMs = 4000;
constexpr uint32_t kRfidCooldownMs = 2500;
constexpr uint8_t kSdaPin = 21;
constexpr uint8_t kSclPin = 22;
constexpr uint8_t kBootPin = 0;
constexpr uint8_t kRfidSsPin = 5;
constexpr uint8_t kRfidRstPin = 4;
constexpr uint8_t kPn532RxPin = 17;
constexpr uint8_t kPn532TxPin = 16;
constexpr uint8_t kPn532I2cAddr = 0x24;
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
int otaPercent = -1;
bool bootWasHigh = true;
uint32_t bootDownAt = 0;
bool bootLongHandled = false;
bool inFlight = false;
MFRC522 rfid(kRfidSsPin, kRfidRstPin);
HardwareSerial uart2(2);
PN532_HSU pn532Hsu(uart2, kPn532RxPin, kPn532TxPin);
PN532 pn532(pn532Hsu);
bool rfidOk = false;
bool pn532UartOk = false;
bool pn532I2cOk = false;
String lastRfidUid;
uint32_t lastRfidMs = 0;

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

const char *readerTag() {
  if (rfidOk) return "522";
  if (pn532UartOk || pn532I2cOk) return "532";
  return "--";
}

void drawFwRight(uint8_t y) {
  u8g2.setFont(u8g2_font_5x8_tf);
  char fw[16];
  snprintf(fw, sizeof(fw), "%s FW %d", readerTag(), kFwVersion);
  u8g2.drawStr(128 - static_cast<int>(strlen(fw)) * 5, y, fw);
}

void draw() {
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_6x13_tf);
  u8g2.drawStr(0, 14, line1.c_str());
  u8g2.drawStr(0, 32, line2.c_str());
  if (otaPercent >= 0) {
    u8g2.drawFrame(0, 40, 128, 10);
    int w = (otaPercent * 126) / 100;
    if (w > 0) u8g2.drawBox(1, 41, w, 8);
    drawFwRight(56);
  } else if (mode == Mode::Portal) {
    u8g2.setFont(u8g2_font_5x8_tf);
    u8g2.drawStr(0, 48, "http://192.168.4.1");
    String pw = "WLAN-PW " + apPass();
    u8g2.drawStr(0, 60, pw.c_str());
    drawFwRight(60);
  } else if (mode == Mode::Station) {
    u8g2.setFont(u8g2_font_5x8_tf);
    u8g2.drawStr(0, 56, WiFi.localIP().toString().c_str());
    drawFwRight(56);
  } else {
    drawFwRight(56);
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
  page += F("<p>Einen Leser anschliessen (RC522 oder Grove NFC). BOOT kurz: Test-UID. BOOT 4&nbsp;s halten: wieder dieses Portal.</p></body></html>");
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
  otaPercent = 0;
  show("Update...", "Laden...");
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
    otaPercent = -1;
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
    otaPercent = -1;
    showHttpError(code);
    return false;
  }
  int len = http.getSize();
  if (!Update.begin(len > 0 ? static_cast<size_t>(len) : UPDATE_SIZE_UNKNOWN)) {
    http.end();
    otaPercent = -1;
    show("Update fehlgeschl", "Flash", 4000);
    return false;
  }
  show("Flashen...", len > 0 ? "0 %" : "...");
  WiFiClient *stream = http.getStreamPtr();
  uint8_t buf[1024];
  size_t written = 0;
  int lastPct = -1;
  uint32_t lastDraw = 0;
  uint32_t idleSince = millis();
  bool writeOk = true;
  while (writeOk) {
    size_t avail = stream->available();
    if (avail) {
      idleSince = millis();
      size_t n = avail > sizeof(buf) ? sizeof(buf) : avail;
      int rd = stream->readBytes(buf, n);
      if (rd <= 0) break;
      if (Update.write(buf, static_cast<size_t>(rd)) != static_cast<size_t>(rd)) {
        writeOk = false;
        break;
      }
      written += static_cast<size_t>(rd);
      if (len > 0) {
        int pct = static_cast<int>((written * 100) / static_cast<size_t>(len));
        if (pct > 100) pct = 100;
        if (pct != lastPct && millis() - lastDraw >= 120) {
          lastPct = pct;
          lastDraw = millis();
          otaPercent = pct;
          show("Flashen...", String(pct) + " %");
        }
        if (written >= static_cast<size_t>(len)) break;
      } else if (millis() - lastDraw >= 200) {
        lastDraw = millis();
        show("Flashen...", String(written / 1024) + " kB");
      }
    } else {
      if (!http.connected() && !stream->available()) break;
      if (millis() - idleSince > 8000) break;
      delay(1);
    }
  }
  bool ok = writeOk && Update.end() && (len <= 0 || written == static_cast<size_t>(len));
  http.end();
  otaPercent = -1;
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

String uidHex() {
  String s;
  s.reserve(static_cast<unsigned>(rfid.uid.size) * 2 + 1);
  for (byte i = 0; i < rfid.uid.size; i++) {
    if (rfid.uid.uidByte[i] < 0x10) s += '0';
    s += String(rfid.uid.uidByte[i], HEX);
  }
  s.toUpperCase();
  return s;
}

void initRc522() {
  SPI.begin();
  rfid.PCD_Init();
  rfid.PCD_SetAntennaGain(MFRC522::RxGain_max);
  delay(40);
  byte ver = rfid.PCD_ReadRegister(MFRC522::VersionReg);
  rfidOk = (ver != 0 && ver != 0xFF);
  if (rfidOk) {
    Serial.printf("RC522 Version 0x%02X\n", ver);
  } else {
    Serial.println("RC522 nicht erkannt");
  }
}

void handleRfid() {
  if (!rfidOk || inFlight || mode != Mode::Station) return;
  if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) return;
  String uid = uidHex();
  byte sak = rfid.uid.sak;
  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
  if (uid.isEmpty()) return;
  if (uid == lastRfidUid && millis() - lastRfidMs < kRfidCooldownMs) return;
  lastRfidUid = uid;
  lastRfidMs = millis();
  Serial.printf("RFID %s SAK=0x%02X\n", uid.c_str(), sak);
  punch(uid);
}

bool probePn532Hsu() {
  pn532.begin();
  uint32_t ver = pn532.getFirmwareVersion();
  if (!ver) {
    Serial.println("PN532 HSU: keine Firmware (Konstruktor RX=17 TX=16)");
    return false;
  }
  Serial.printf("PN532 HSU OK  IC=0x%02lx ver %lu.%lu\n",
                (unsigned long)((ver >> 24) & 0xFF),
                (unsigned long)((ver >> 16) & 0xFF),
                (unsigned long)((ver >> 8) & 0xFF));
  pn532.SAMConfig();
  return true;
}

bool pn532I2cReady(uint32_t timeoutMs) {
  uint32_t start = millis();
  while (millis() - start < timeoutMs) {
    if (Wire.requestFrom(kPn532I2cAddr, static_cast<uint8_t>(1)) >= 1) {
      int b = Wire.read();
      if (b >= 0 && (b & 1)) return true;
    }
    delay(5);
  }
  return false;
}

bool pn532I2cSend(const uint8_t *data, uint8_t len) {
  uint8_t cmdlen = static_cast<uint8_t>(len + 1);
  Wire.beginTransmission(kPn532I2cAddr);
  uint8_t checksum = static_cast<uint8_t>(0x00 + 0x00 + 0xFF);
  Wire.write(static_cast<uint8_t>(0x00));
  Wire.write(static_cast<uint8_t>(0x00));
  Wire.write(static_cast<uint8_t>(0xFF));
  Wire.write(cmdlen);
  Wire.write(static_cast<uint8_t>(~cmdlen + 1));
  Wire.write(static_cast<uint8_t>(0xD4));
  checksum = static_cast<uint8_t>(checksum + 0xD4);
  for (uint8_t i = 0; i < len; i++) {
    Wire.write(data[i]);
    checksum = static_cast<uint8_t>(checksum + data[i]);
  }
  Wire.write(static_cast<uint8_t>(~checksum));
  Wire.write(static_cast<uint8_t>(0x00));
  if (Wire.endTransmission() != 0) return false;
  if (!pn532I2cReady(200)) return false;
  uint8_t got = Wire.requestFrom(kPn532I2cAddr, static_cast<uint8_t>(8));
  if (got < 7) return false;
  Wire.read();
  uint8_t ack[6];
  for (uint8_t i = 0; i < 6; i++) ack[i] = static_cast<uint8_t>(Wire.read());
  const uint8_t expect[6] = {0x00, 0x00, 0xFF, 0x00, 0xFF, 0x00};
  return memcmp(ack, expect, 6) == 0;
}

bool pn532I2cReadResponse(uint8_t *out, uint8_t outMax, uint8_t *outLen, uint32_t timeoutMs) {
  if (!pn532I2cReady(timeoutMs)) return false;
  uint8_t got = Wire.requestFrom(kPn532I2cAddr, static_cast<uint8_t>(24));
  if (got < 8) return false;
  Wire.read();
  uint8_t buf[22];
  uint8_t n = 0;
  while (Wire.available() && n < sizeof(buf)) buf[n++] = static_cast<uint8_t>(Wire.read());
  int start = -1;
  for (uint8_t i = 0; i + 2 < n; i++) {
    if (buf[i] == 0x00 && buf[i + 1] == 0x00 && buf[i + 2] == 0xFF) {
      start = i + 3;
      break;
    }
    if (buf[i] == 0x00 && buf[i + 1] == 0xFF) {
      start = i + 2;
      break;
    }
  }
  if (start < 0 || start + 2 > static_cast<int>(n)) return false;
  uint8_t length = buf[start];
  if (static_cast<uint8_t>(length + buf[start + 1]) != 0 || length < 2 || length > outMax) return false;
  if (start + 2 + length > static_cast<int>(n)) return false;
  memcpy(out, buf + start + 2, length);
  *outLen = length;
  return true;
}

bool probePn532I2c() {
  Wire.beginTransmission(kPn532I2cAddr);
  uint8_t err = Wire.endTransmission();
  if (err != 0) {
    Serial.println("I2C 0x24: kein ACK (normal im UART-Modus)");
    return false;
  }
  Serial.println("I2C 0x24: ACK, GetFirmwareVersion...");
  delay(40);
  const uint8_t cmd[] = {0x02};
  if (!pn532I2cSend(cmd, 1)) {
    Serial.println("I2C PN532: kein ACK auf Befehl");
    return false;
  }
  uint8_t resp[16];
  uint8_t n = 0;
  if (!pn532I2cReadResponse(resp, sizeof(resp), &n, 250)) return false;
  if (n >= 3 && resp[0] == 0xD5 && resp[1] == 0x03 && resp[2] == 0x32) {
    Serial.printf("PN532 I2C OK  ver %u.%u\n", static_cast<unsigned>(resp[3]), static_cast<unsigned>(resp[4]));
    return true;
  }
  return false;
}

bool pn532I2cSamConfig() {
  const uint8_t cmd[] = {0x14, 0x01, 0x01, 0x00};
  if (!pn532I2cSend(cmd, 4)) return false;
  uint8_t resp[8];
  uint8_t n = 0;
  return pn532I2cReadResponse(resp, sizeof(resp), &n, 200) && n >= 2 && resp[0] == 0xD5 && resp[1] == 0x15;
}

void offerPn532Uid(const uint8_t *resp, uint8_t n) {
  if (n < 9 || resp[0] != 0xD5 || resp[1] != 0x4B || resp[2] < 1) return;
  uint8_t uidLen = resp[7];
  if (uidLen < 4 || uidLen > 10 || static_cast<uint8_t>(8 + uidLen) > n) return;
  String uid;
  uid.reserve(uidLen * 2u + 1u);
  for (uint8_t i = 0; i < uidLen; i++) {
    if (resp[8 + i] < 0x10) uid += '0';
    uid += String(resp[8 + i], HEX);
  }
  uid.toUpperCase();
  if (uid == lastRfidUid && millis() - lastRfidMs < kRfidCooldownMs) return;
  lastRfidUid = uid;
  lastRfidMs = millis();
  Serial.print("PN532 ");
  Serial.println(uid);
  punch(uid);
}

void handlePn532() {
  if (inFlight || mode != Mode::Station) return;
  if (pn532I2cOk) {
    const uint8_t cmd[] = {0x4A, 0x01, 0x00};
    if (!pn532I2cSend(cmd, 3)) return;
    uint8_t resp[32];
    uint8_t n = 0;
    if (!pn532I2cReadResponse(resp, sizeof(resp), &n, 120)) return;
    offerPn532Uid(resp, n);
    return;
  }
  if (!pn532UartOk) return;
  uint8_t uid[10];
  uint8_t uidLen = sizeof(uid);
  if (!pn532.readPassiveTargetID(PN532_MIFARE_ISO14443A, uid, &uidLen, 120)) return;
  if (uidLen < 4) return;
  String hex;
  hex.reserve(uidLen * 2u + 1u);
  for (uint8_t i = 0; i < uidLen; i++) {
    if (uid[i] < 0x10) hex += '0';
    hex += String(uid[i], HEX);
  }
  hex.toUpperCase();
  if (hex == lastRfidUid && millis() - lastRfidMs < kRfidCooldownMs) return;
  lastRfidUid = hex;
  lastRfidMs = millis();
  Serial.print("PN532 ");
  Serial.println(hex);
  punch(hex);
}

void initUartReader() {
  pn532UartOk = false;
  Serial.println("PN532 HSU: Gelb->GPIO17 (ESP32 RX)  Weiss->GPIO16 (ESP32 TX)  3,3V  kein Teiler");
  if (probePn532Hsu()) {
    pn532UartOk = true;
    Serial.println("UART: PN532");
    return;
  }
  uart2.end();
  Serial.println("UART: kein PN532");
}

void initReaders() {
  pn532I2cOk = false;
  initRc522();
  initUartReader();
  if (!pn532UartOk && probePn532I2c()) {
    pn532I2cOk = true;
    if (!pn532I2cSamConfig()) Serial.println("PN532 I2C SAM-Config fehlgeschlagen, Leser trotzdem aktiv");
  }
  Serial.printf("Leser %s\n", readerTag());
  if (pn532UartOk || pn532I2cOk) {
    show("PN532 OK", pn532I2cOk ? "I2C" : "UART", 2000);
  } else if (!rfidOk) {
    show("kein PN532", "Gelb 17 Weiss 16", 4000);
    delay(3500);
  }
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
    return;
  }
  if (cmd == "PROBE" || cmd == "LESER") {
    initReaders();
    Serial.printf("SPI-RC522 %s  UART-%s  I2C-%s\n", rfidOk ? "ja" : "nein",
                  pn532UartOk ? "532" : "-",
                  pn532I2cOk ? "532" : "-");
    show("Leser", readerTag(), 3000);
  }
}

}  // namespace

void setup() {
  Serial.begin(115200);
  pinMode(kBootPin, INPUT_PULLUP);
  u8g2.begin();
  loadPrefs();
  initReaders();
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
  handleRfid();
  if (pn532UartOk || pn532I2cOk) handlePn532();
  if (!lastHello || millis() - lastHello >= kHelloMs) hello();
  idleScreen();
}
