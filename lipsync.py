import serial
import time
import numpy as np
import sounddevice as sd
import soundfile as sf

# --- CONFIGURATION ---
COM_PORT = 'COM7'  
WAV_FILE = 'voice.wav'

print(f"Connecting to {COM_PORT}...")
arduino = serial.Serial(COM_PORT, 115200)
time.sleep(2) 

print("Loading audio file...")
data, fs = sf.read(WAV_FILE, dtype='float32')
if len(data.shape) > 1:
    data = data[:, 0] 

print("Playing audio and moving servo...")

def audio_callback(outdata, frames, time_info, status):
    global current_frame
    chunk = data[current_frame:current_frame + frames]
    
   
    if len(chunk) < frames:
        outdata[:len(chunk), 0] = chunk
        outdata[len(chunk):, 0] = 0
    else:
        outdata[:, 0] = chunk

    
    volume = np.abs(chunk).mean()
    
    # --- DYNAMIC COMPRESSION CURVE ---
    # np.sqrt() boosts quiet sounds heavily but barely boosts loud sounds.
    compressed_volume = np.sqrt(volume)
    
    
    angle = int(min(90, compressed_volume * 2.5 * 90))
    
    print(f"angle: {angle}")
    # Send the angle to the Arduino instantly over USB
    arduino.write(f"{angle}\n".encode())
    
    current_frame += frames

current_frame = 0

# Start playing the audio out loud while running the math callback
with sd.OutputStream(samplerate=fs, channels=1, callback=audio_callback):
    while current_frame < len(data):
        time.sleep(0.01)
        
arduino.write(b"0\n") # Close mouth when audio finishes
print("Finished!")