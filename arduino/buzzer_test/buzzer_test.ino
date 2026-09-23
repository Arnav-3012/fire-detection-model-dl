// Standalone buzzer hardware verification tool -- NOT part of production
// firmware. Isolated check of the buzzer wiring/hardware itself,
// independent of sensors or calibration state. Useful any time buzzer
// wiring is touched or suspected faulty.
//
// Behavior: waits 3s after boot (time to open Serial Monitor), then
// toggles GPIO33 HIGH for 1s / LOW for 1s, 5 times, then prints
// "buzzer test complete". No sensor reads, no WiFi, no warmup gate.
//
// Pin matches sensor_esp32_node.ino's BUZZER_PIN (GPIO33, digital out).

const int BUZZER_PIN = 33;

void setup() {
  Serial.begin(9600);

  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

  delay(3000);  // time to open Serial Monitor

  for (int i = 0; i < 5; i++) {
    digitalWrite(BUZZER_PIN, HIGH);
    delay(1000);
    digitalWrite(BUZZER_PIN, LOW);
    delay(1000);
  }

  Serial.println("buzzer test complete");
}

void loop() {
  // nothing -- test runs once in setup()
}
