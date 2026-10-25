import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import serial
import time
import numpy as np
import sounddevice as sd
import soundfile as sf
import pyttsx3
import speech_recognition as sr
from google import genai
import os

# Optional .env support so the Gemini key does not need to be typed in PowerShell every time.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# =========================================================
# GLOBAL VARIABLES
# =========================================================

arduino = None

# =========================================================
# GEMINI AI
# =========================================================
# Set your Gemini API key in PowerShell before running:
# $env:GEMINI_API_KEY="YOUR_NEW_API_KEY"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
client = None
GEMINI_MODEL = "gemini-2.5-flash"

if GEMINI_API_KEY:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print("GEMINI CLIENT ERROR:", repr(e))
        client = None

TEMP_WAV = "temp_speech.wav"
LISTEN_WAV = "robot_listen.wav"

chat_running = False
current_frame = 0


# =========================================================
# STATUS
# =========================================================

def update_status(msg, color="blue"):
    try:
        root.after(
            0,
            lambda: status_label.config(
                text=msg,
                fg=color
            )
        )
    except:
        pass


def add_chat(text):
    try:
        def update():
            chat_log.insert(
                tk.END,
                text
            )
            chat_log.see(tk.END)

        root.after(0, update)

    except:
        pass


# =========================================================
# ARDUINO + AUDIO PLAYBACK
# =========================================================

def play_audio_with_sync(wav_file_path):
    global arduino
    global current_frame

    if not arduino or not arduino.is_open:
        update_status(
            "Error: Arduino not connected!",
            "red"
        )
        return

    try:

        data, fs = sf.read(
            wav_file_path,
            dtype="float32"
        )

        # Stereo -> Mono
        if len(data.shape) > 1:
            data = data[:, 0]

        current_frame = 0

        def audio_callback(
            outdata,
            frames,
            time_info,
            status
        ):
            global current_frame

            chunk = data[
                current_frame:
                current_frame + frames
            ]

            if len(chunk) < frames:

                outdata[:len(chunk), 0] = chunk

                outdata[
                    len(chunk):,
                    0
                ] = 0

            else:

                outdata[:, 0] = chunk

            # -----------------------------------------
            # VOLUME
            # -----------------------------------------

            if len(chunk) > 0:

                volume = np.abs(
                    chunk
                ).mean()

            else:

                volume = 0

            # -----------------------------------------
            # MOUTH MOVEMENT
            # -----------------------------------------

            compressed_volume = np.sqrt(
                volume
            )

            angle = int(
                min(
                    90,
                    compressed_volume * 2.9 * 90
                )
            )

            try:

                arduino.write(
                    f"{angle}\n".encode()
                )

            except:
                pass

            current_frame += frames

        update_status(
            "🔊 Robot is talking...",
            "green"
        )

        with sd.OutputStream(
            samplerate=fs,
            channels=1,
            callback=audio_callback
        ):

            while current_frame < len(data):

                time.sleep(0.01)

        # Close mouth
        try:
            arduino.write(
                b"0\n"
            )
        except:
            pass

        update_status(
            "Idle",
            "blue"
        )

    except Exception as e:

        update_status(
            f"Playback error: {str(e)}",
            "red"
        )


# =========================================================
# TEXT TO SPEECH
# =========================================================

def generate_and_play_tts(text):

    try:

        update_status(
            "Generating robot voice...",
            "orange"
        )

        engine = pyttsx3.init()

        engine.setProperty(
            "rate",
            160
        )

        engine.setProperty(
            "volume",
            1.0
        )

        engine.save_to_file(
            text,
            TEMP_WAV
        )

        engine.runAndWait()

        time.sleep(0.2)

        if os.path.exists(TEMP_WAV):

            play_audio_with_sync(
                TEMP_WAV
            )

        else:

            update_status(
                "Voice file was not created.",
                "red"
            )

    except Exception as e:

        update_status(
            f"TTS Error: {str(e)}",
            "red"
        )


# =========================================================
# ARDUINO CONNECTION
# =========================================================

def connect_arduino():

    global arduino

    port = port_entry.get().strip()

    if not port:

        update_status(
            "Please enter COM port.",
            "red"
        )

        return

    try:

        arduino = serial.Serial(
            port,
            115200,
            timeout=1
        )

        time.sleep(2)

        update_status(
            f"Connected to {port}",
            "green"
        )

    except Exception as e:

        update_status(
            f"Connection failed: {str(e)}",
            "red"
        )


# =========================================================
# CUSTOM WAV
# =========================================================

def play_custom_audio():

    file_path = filedialog.askopenfilename(
        filetypes=[
            ("WAV files", "*.wav"),
            ("All files", "*.*")
        ]
    )

    if file_path:

        threading.Thread(
            target=play_audio_with_sync,
            args=(file_path,),
            daemon=True
        ).start()


# =========================================================
# STORY MODE
# =========================================================

def read_story():

    text = story_text.get(
        "1.0",
        tk.END
    ).strip()

    if text:

        threading.Thread(
            target=generate_and_play_tts,
            args=(text,),
            daemon=True
        ).start()

    else:

        messagebox.showwarning(
            "Empty",
            "Please paste a story into the box first!"
        )


# =========================================================
# MICROPHONE RECORDING
# =========================================================
# IMPORTANT:
# This replaces sr.Microphone()
# No PyAudio required.
# =========================================================

def record_microphone():

    try:

        SAMPLE_RATE = 16000
        CHANNELS = 1

        # Listen for up to 8 seconds
        RECORD_SECONDS = 8

        update_status(
            "🎤 Listening... Speak now!",
            "red"
        )

        # Record microphone using sounddevice
        audio_data = sd.rec(
            int(
                RECORD_SECONDS *
                SAMPLE_RATE
            ),
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32"
        )

        sd.wait()

        # Save microphone audio
        sf.write(
            LISTEN_WAV,
            audio_data,
            SAMPLE_RATE
        )

        return LISTEN_WAV

    except Exception as e:

        update_status(
            f"Microphone error: {str(e)}",
            "red"
        )

        return None


# =========================================================
# SPEECH TO TEXT
# =========================================================

def speech_to_text(wav_file):

    try:

        update_status(
            "🧠 Understanding...",
            "orange"
        )

        recognizer = sr.Recognizer()

        # Read saved WAV file
        with sr.AudioFile(wav_file) as source:

            audio = recognizer.record(
                source
            )

        # Google speech recognition
        text = recognizer.recognize_google(
            audio,
            language="en-IN"
        )

        return text.strip()

    except sr.UnknownValueError:

        update_status(
            "I couldn't understand that.",
            "blue"
        )

        return None

    except sr.RequestError as e:

        update_status(
            f"Speech service error: {str(e)}",
            "red"
        )

        return None

    except Exception as e:

        update_status(
            f"Speech error: {str(e)}",
            "red"
        )

        return None


# =========================================================
# GEMINI AI
# =========================================================

def ask_gemini(user_text):

    try:

        text = user_text.strip()

        if not text:
            return "I didn't hear you."

        # Special greeting responses
        lower_text = text.lower()

        greetings = {
            "hi",
            "hello",
            "hey",
            "hii",
            "hiii",
            "hello robot",
            "hi robot",
            "hey robot"
        }

        if lower_text in greetings:

            return (
                "Hii! 😄 "
                "How are you? "
                "What can I do for you?"
            )

        # Check API key
        if not GEMINI_API_KEY or client is None:

            return (
                "Gemini API key is not configured. "
                "Create a .env file beside this Python file and add "
                "GEMINI_API_KEY=YOUR_KEY, then restart the app."
            )

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=(
                "You are a friendly cardboard robot assistant.\n"
                "Personality: friendly, funny, slightly sarcastic, "
                "helpful and natural.\n"
                "Keep answers short, normally 1 to 3 sentences.\n"
                "Do not use markdown.\n\n"
                f"User: {text}"
            )
        )

        reply = (response.text or "").strip()

        if not reply:
            return "Sorry, I don't know what to say."

        return reply

    except Exception as e:

        error_text = repr(e)
        print("GEMINI ERROR:", error_text)

        return (
            "I could not connect to Gemini. "
            f"Error: {error_text}"
        )


# =========================================================
# LISTEN ONCE
# =========================================================

def listen_once():

    # Record microphone
    wav_file = record_microphone()

    if not wav_file:

        return None

    # Convert speech -> text
    user_text = speech_to_text(
        wav_file
    )

    return user_text


# =========================================================
# CONTINUOUS AI CHAT
# =========================================================

def ai_chat():

    global chat_running

    if chat_running:

        update_status(
            "Listen & Talk is already running.",
            "orange"
        )

        return

    chat_running = True

    listen_button.config(
        state="disabled"
    )

    stop_button.config(
        state="normal"
    )

    threading.Thread(
        target=chat_loop,
        daemon=True
    ).start()


# =========================================================
# CHAT LOOP
# =========================================================

def chat_loop():

    global chat_running

    add_chat(
        "\n"
        "==============================\n"
        "🤖 Robot Listen & Talk Started\n"
        "==============================\n\n"
    )

    while chat_running:

        # -----------------------------------------
        # LISTEN
        # -----------------------------------------

        user_text = listen_once()

        if not chat_running:

            break

        if not user_text:

            continue

        user_text = user_text.strip()

        add_chat(
            f"You: {user_text}\n"
        )

        # -----------------------------------------
        # STOP COMMAND
        # -----------------------------------------

        stop_words = [
            "stop listening",
            "stop talking",
            "bye robot",
            "goodbye robot",
            "shutdown robot"
        ]

        if any(
            word in user_text.lower()
            for word in stop_words
        ):

            reply = (
                "Okay! I will go quiet now. "
                "See you later!"
            )

            add_chat(
                f"Robot: {reply}\n\n"
            )

            generate_and_play_tts(
                reply
            )

            break

        # -----------------------------------------
        # THINK
        # -----------------------------------------

        update_status(
            "🤖 Robot is thinking...",
            "orange"
        )

        reply = ask_gemini(
            user_text
        )

        add_chat(
            f"Robot: {reply}\n\n"
        )

        # -----------------------------------------
        # TALK
        # -----------------------------------------

        if chat_running:

            generate_and_play_tts(
                reply
            )

    # -----------------------------------------
    # FINISH
    # -----------------------------------------

    chat_running = False

    root.after(
        0,
        lambda: listen_button.config(
            state="normal"
        )
    )

    root.after(
        0,
        lambda: stop_button.config(
            state="disabled"
        )
    )

    update_status(
        "Idle",
        "blue"
    )

    add_chat(
        "\n"
        "🤖 Robot Listen & Talk stopped.\n\n"
    )


# =========================================================
# STOP LISTEN & TALK
# =========================================================

def stop_ai_chat():

    global chat_running

    chat_running = False

    update_status(
        "Stopping robot...",
        "orange"
    )

    # Close mouth
    try:

        if arduino and arduino.is_open:

            arduino.write(
                b"0\n"
            )

    except:
        pass


# =========================================================
# CLOSE APP
# =========================================================

def close_app():

    global chat_running

    chat_running = False

    try:

        if arduino and arduino.is_open:

            arduino.write(
                b"0\n"
            )

            arduino.close()

    except:
        pass

    # Delete temporary files
    try:

        if os.path.exists(
            TEMP_WAV
        ):
            os.remove(
                TEMP_WAV
            )

        if os.path.exists(
            LISTEN_WAV
        ):
            os.remove(
                LISTEN_WAV
            )

    except:
        pass

    root.destroy()


# =========================================================
# GUI
# =========================================================

root = tk.Tk()

root.title(
    "Cardboard Robot Control Dashboard"
)

root.geometry(
    "500x720"
)

root.configure(
    padx=20,
    pady=20
)

root.protocol(
    "WM_DELETE_WINDOW",
    close_app
)

# Show a helpful warning if the Gemini key has not been configured.
if not GEMINI_API_KEY:
    print(
        "WARNING: GEMINI_API_KEY is not set. "
        "Set it in PowerShell before using Live AI Chatbot."
    )



# =========================================================
# STATUS
# =========================================================

status_label = tk.Label(
    root,
    text="Not Connected",
    fg="red",
    font=("Arial", 12, "bold")
)

status_label.pack(
    pady=5
)


# =========================================================
# ARDUINO
# =========================================================

tk.Label(
    root,
    text="1. Connect to Arduino",
    font=("Arial", 10, "bold")
).pack(
    anchor="w",
    pady=(10, 0)
)

port_frame = tk.Frame(root)

port_frame.pack(
    fill="x",
    pady=5
)

tk.Label(
    port_frame,
    text="COM Port:"
).pack(
    side="left"
)

port_entry = tk.Entry(
    port_frame,
    width=15
)

port_entry.insert(
    0,
    "COM11"
)

port_entry.pack(
    side="left",
    padx=5
)

tk.Button(
    port_frame,
    text="Connect",
    command=connect_arduino,
    bg="#4CAF50",
    fg="white"
).pack(
    side="left"
)


tk.Frame(
    root,
    height=2,
    bd=1,
    relief="sunken"
).pack(
    fill="x",
    pady=15
)


# =========================================================
# CUSTOM AUDIO
# =========================================================

tk.Label(
    root,
    text="2. Play Custom WAV File",
    font=("Arial", 10, "bold")
).pack(
    anchor="w"
)

tk.Button(
    root,
    text="Browse & Play Audio",
    command=play_custom_audio,
    width=20
).pack(
    pady=5
)


tk.Frame(
    root,
    height=2,
    bd=1,
    relief="sunken"
).pack(
    fill="x",
    pady=15
)


# =========================================================
# STORY MODE
# =========================================================

tk.Label(
    root,
    text="3. Story / Reader Mode",
    font=("Arial", 10, "bold")
).pack(
    anchor="w"
)

story_text = tk.Text(
    root,
    height=5,
    width=50
)

story_text.pack(
    pady=5
)

tk.Button(
    root,
    text="Read Out Loud",
    command=read_story,
    width=20
).pack()


tk.Frame(
    root,
    height=2,
    bd=1,
    relief="sunken"
).pack(
    fill="x",
    pady=15
)


# =========================================================
# AI CHATBOT
# =========================================================

tk.Label(
    root,
    text="4. Live AI Chatbot",
    font=("Arial", 10, "bold")
).pack(
    anchor="w"
)


listen_button = tk.Button(
    root,
    text="🎤 Listen & Talk",
    command=ai_chat,
    bg="#008CBA",
    fg="white",
    font=("Arial", 12, "bold"),
    width=20
)

listen_button.pack(
    pady=5
)


stop_button = tk.Button(
    root,
    text="⛔ Stop Listening",
    command=stop_ai_chat,
    bg="#d9534f",
    fg="white",
    font=("Arial", 11, "bold"),
    width=20,
    state="disabled"
)

stop_button.pack(
    pady=3
)


# =========================================================
# CHAT LOG
# =========================================================

chat_log = tk.Text(
    root,
    height=9,
    width=50,
    bg="#f0f0f0",
    wrap="word"
)

chat_log.pack(
    pady=8
)


# =========================================================
# START
# =========================================================

root.mainloop()