// FireWatch - Day 6/7 sensor + alarm sketch (plan.md sections 5.2, 8)
//
// Streams MQ-2 (A0) and MQ-135 (A1) raw ADC readings once per second as a
// continuous "mq2,mq135\n" CSV line, consumed by edge/sensors.py and
// eval/calibrate_mq.py. No temp/humidity fields: DHT22 was cut (Phase 0g).
//
// Phase 7 addition — single-byte alarm command (plan.md Day 6 bytes):
//   'A' -> buzzer (D8) HIGH    'S' -> buzzer (D8) LOW
// Anything else is ignored. Deliberately no acknowledgment and no other
// commands: the alarm write from edge/main.py is fire-and-forget, and any
// reply here would interleave with the CSV stream and complicate parsing.
//
// Timing uses millis(), not delay(1000): with delay(), an alarm byte could
// sit unread for up to a second — real latency in the local alarm path
// (info.md 4.3's <=3s hazard-to-buzzer target). The CSV cadence is still
// 1 Hz; only the waiting mechanism changed.

const int BUZZER_PIN = 8;                       // plan.md 5.2: active buzzer on D8
const unsigned long SAMPLE_INTERVAL_MS = 1000;  // 1 Hz, same as the Day 6 sketch

unsigned long lastSampleMs = 0;

void setup() {
  Serial.begin(9600);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);  // boot silent — alarm state is host-driven only
}

void loop() {
  // Non-blocking command check every pass (~thousands/sec between samples).
  if (Serial.available() > 0) {
    int cmd = Serial.read();
    if (cmd == 'A') {
      digitalWrite(BUZZER_PIN, HIGH);
    } else if (cmd == 'S') {
      digitalWrite(BUZZER_PIN, LOW);
    }
  }

  unsigned long now = millis();
  if (now - lastSampleMs >= SAMPLE_INTERVAL_MS) {
    lastSampleMs = now;
    int mq2 = analogRead(A0);
    int mq135 = analogRead(A1);

    Serial.print(mq2);
    Serial.print(",");
    Serial.println(mq135);
  }
}
