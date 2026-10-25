#include <Servo.h>

Servo mouthServo;
int servoPin = 9;

void setup() {
  // Start the USB Serial connection at high speed
  Serial.begin(115200);
  
  mouthServo.attach(servoPin);
  mouthServo.write(0); 
}

void loop() {
  if (Serial.available() > 0) {
    int angle = Serial.parseInt();
    
    if (angle >= 0 && angle <= 90) {
      mouthServo.write(angle*2);
    }
  }
}