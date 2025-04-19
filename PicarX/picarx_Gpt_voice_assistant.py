import os
import speech_recognition as sr
import pyttsx3
import openai  # Use openai, not OpenAI class
import yaml

# Load the YAML
with open('.secrets', 'r') as f:
    secrets = yaml.safe_load(f)

openai_key   = secrets['openai']['api_key']
client = openai(api_key=openai_key)

# Setup text-to-speech with espeak (works better on Pi)
engine = pyttsx3.init(driverName='espeak')
engine.setProperty("rate", 180)

# Setup speech recognizer
recognizer = sr.Recognizer()
mic = sr.Microphone()

def speak(text):
    print(f"Assistant: {text}")
    engine.say(text)
    engine.runAndWait()

def listen():
    with mic as source:
        print("🎙️ Listening...")
        recognizer.adjust_for_ambient_noise(source)
        audio = recognizer.listen(source)

    try:
        print("🧠 Recognizing...")
        return recognizer.recognize_google(audio)
    except sr.UnknownValueError:
        return "Sorry, I didn’t catch that."
    except sr.RequestError:
        return "Error with the speech recognition service."

def chat_with_gpt(user_input):
    response = openai.ChatCompletion.create(  # This is the correct usage now
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful assistant who speaks like ChatGPT."},
            {"role": "user", "content": user_input}
        ]
    )
    return response.choices[0].message["content"].strip()

# Main loop
if __name__ == "__main__":
    while True:
        user_input = listen()
        print(f"You said: {user_input}")
        if user_input.lower() in ["exit", "quit", "stop"]:
            speak("Goodbye!")
            break
        reply = chat_with_gpt(user_input)
        speak(reply)