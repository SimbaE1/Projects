#!/usr/bin/env python3
import os, sys, subprocess, pygame, requests, speech_recognition as sr
import sqlite3
from   datetime import datetime
import yaml

# ─── CONFIG ────────────────────────────────────────────────────────────
# Load the YAML
with open('.secrets', 'r') as f:
    secrets = yaml.safe_load(f)

# Access your keys
groq_key   = secrets['groq']['api_key']

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL        = "llama3-70b-8192"
MAHLER_PATH  = "Pierre Boulez - Conducts Mahler - Symphony No. 6.mp3"


# ─── SDL / ALSA setup ──────────────────────────────────────────────────
os.environ["SDL_AUDIODRIVER"] = "alsa"
os.environ["AUDIODEV"]        = "plughw:0,0"   # HiFiBerry card 0,device 0

pygame.init()
pygame.mixer.init()            # will fail if HiFiBerry is busy
recognizer = sr.Recognizer()
mic        = sr.Microphone()

def speak(text: str):
    """
    1.  Close pygame’s handle so the DAC is free
    2.  Pipe espeak’s raw audio → aplay on HiFiBerry
    3.  Re‑open pygame so Mahler 6 can play next time
    """
    try:
        pygame.mixer.quit()                    # ① release /dev/snd/pcmC0D0p
    except pygame.error:
        pass                                   # mixer wasn’t open

    print(f"🎙️  {text}")
    # ② generate speech → send to aplay on card 0,device 0
    espeak = subprocess.Popen(
        ["espeak", text, "--stdout"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL
    )
    subprocess.run(
        ["aplay", "-D", "plughw:0,0"],
        stdin=espeak.stdout,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    # ③ grab the device again for future music / effects
    pygame.mixer.init()

def listen(timeout: float = 5.0) -> str:
    with mic as source:
        print("🎧 Listening...")
        recognizer.adjust_for_ambient_noise(source)
        audio = recognizer.listen(source, timeout=timeout)
    try:
        print("🧠 Recognizing...")
        return recognizer.recognize_google(audio)
    except sr.UnknownValueError:
        return "Sorry, I didn’t catch that."
    except sr.RequestError:
        return "Error with the speech recognition service."

def ask_groq(messages: list[dict]) -> str | None:
    headers = {
        "Authorization": f"Bearer {groq_key}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model":   MODEL,
        "messages": messages
    }
    resp = requests.post(GROQ_API_URL, json=payload, headers=headers, timeout=15)
    if resp.status_code != 200:
        print("❌ Groq API error:", resp.json())
        return None
    return resp.json()["choices"][0]["message"]["content"].strip()

def type_chat():
    messages = [
        {"role": "system", "content": "You are a friendly assistant who likes playing with kids."} # Add more of a description if wanted
    ]
    print("💬 Type‑chat mode. Type 'exit' to go back.")
    while True:
        you = input("You: ").strip()
        if you.lower() in ("exit", "quit", "stop"):
            break
        messages.append({"role": "user", "content": you})
        print("📡 Sending to Groq…")
        reply = ask_groq(messages)
        if reply:
            print("AI:", reply)
            speak(reply)
            messages.append({"role": "assistant", "content": reply})
        else:
            print("AI: Sorry, there was a problem talking to the AI.")

def voice_chat():
    messages = [
        {"role": "system", "content": "You are a friendly assistant who likes playing with kids."} # Add more of a description if wanted
    ]
    print("🎤 Voice‑chat mode. Say 'exit' to go back.")
    while True:
        you = listen()
        print(f"You (voice): {you}")
        if you.lower() in ("exit", "quit", "stop"):
            break
        messages.append({"role": "user", "content": you})
        print("📡 Sending to Groq…")
        reply = ask_groq(messages)
        if reply:
            print("AI:", reply)
            speak(reply)
            messages.append({"role": "assistant", "content": reply})
        else:
            print("AI: Sorry, there was a problem talking to the AI.")

def play_mahler():
    if not os.path.exists(MAHLER_PATH):
        print(f"⚠️  File not found: {MAHLER_PATH}")
        return
    pygame.mixer.music.load(MAHLER_PATH)
    pygame.mixer.music.play()
    print("▶️  Playing Mahler 6. Press Enter to stop.")
    input()
    pygame.mixer.music.stop()

def main():
    while True:
        print("""
Options:
  t – Type to talk
  v – Voice to talk
  m – Play Mahler 6
  q – Quit
""")
        choice = input("Enter your choice: ").lower().strip()
        if choice == "t":
            type_chat()
        elif choice == "v":
            voice_chat()
        elif choice == "m":
            play_mahler()
        elif choice == "q":
            print("Goodbye!")
            break
        else:
            print("Invalid choice… try again.")

if __name__ == "__main__":
    main()