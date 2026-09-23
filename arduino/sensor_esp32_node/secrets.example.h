#pragma once

// Template. Copy this file to secrets.h (same directory) and fill in
// your own values. secrets.h is gitignored; this file is not.
// Never put real credentials in this template.

// ---------------------------------------------------------------------
// WiFi networks, tried IN ORDER until one connects (Stage 3, 2026-09-23).
//
// A LIST, not a single SSID, because this board moves between networks:
// home for development, a phone hotspot for demos elsewhere. Reflashing
// to change networks is not viable when the demo venue is decided on the
// day, so every network you might use is registered here once.
//
// Order matters: the board tries [0] first, then [1], and so on. Put the
// network you use most first so the common case connects fastest.
//
// NOTE on campus/enterprise WiFi: many university networks enable client
// isolation (devices reach the internet but NOT each other), which blocks
// board -> laptop POSTs no matter how correct the credentials are. That
// is a network policy, not something firmware can work around. Use a
// phone hotspot for demos on such networks -- you control it and it has
// no isolation.
// ---------------------------------------------------------------------
struct WifiNetwork {
  const char *ssid;
  const char *password;
};

static const WifiNetwork WIFI_NETWORKS[] = {
  {"YOUR_HOME_SSID",    "YOUR_HOME_PASSWORD"},
  {"YOUR_HOTSPOT_SSID", "YOUR_HOTSPOT_PASSWORD"},
};
static const int WIFI_NETWORK_COUNT = sizeof(WIFI_NETWORKS) / sizeof(WIFI_NETWORKS[0]);

// ---------------------------------------------------------------------
// Where this board POSTs its 1 Hz JSON reading: the machine running
// edge/main.py with sensors.transport: "wifi" in config.yaml. NOT the
// dashboard backend -- the ingest server lives in the edge loop so the
// detector never depends on the dashboard (see edge/wifi_source.py).
//
// INGEST_HOST is tried FIRST and should be an mDNS hostname (macOS and
// most Linux advertise one automatically; find yours with
// `scutil --get LocalHostName` and append ".local"). A hostname survives
// the laptop getting a different IP on every network, which is exactly
// what happens when you switch between home WiFi and a phone hotspot --
// so this is what makes the board work on a new network with NO reflash.
//
// INGEST_FALLBACK_IP is used only if the hostname does not resolve
// (some hotspots, notably certain Android builds, do not forward mDNS).
// Leave it "" to disable the fallback.
//
// Set BOTH to "" to disable transmission entirely -- the board still
// runs gas detection and its buzzer, serial-only.
// ---------------------------------------------------------------------
const char *INGEST_HOST = "your-laptop.local";  // e.g. "Arnavs-MacBook-Pro-2.local"
const char *INGEST_FALLBACK_IP = "";            // e.g. "192.168.1.3"
const int   INGEST_PORT = 8002;                 // matches config.yaml sensors.ingest_port
const char *INGEST_PATH = "/ingest";
