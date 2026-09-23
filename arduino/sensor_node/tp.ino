void setup() {
  pinMode(33, OUTPUT);
}

void loop() {
  digitalWrite(33, LOW);   // LOW turns this LED ON (inverted logic on this board)
  delay(1000);
  digitalWrite(33, HIGH);  // HIGH turns it OFF
  delay(1000);
}