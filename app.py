from flask import Flask, request, jsonify
import pandas as pd
import openai
import os
import random
import re
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Load and clean data
df = pd.read_csv("movies.csv")
df.dropna(subset=["title", "genres", "runtime", "final_score", "release_year"], inplace=True)
df["runtime"] = df["runtime"].astype(float)
df["final_score"] = df["final_score"].astype(float)
df = df[df["runtime"] >= 60]
if "adult" in df.columns:
    df = df[df["adult"] == False]

# Normalize score: scaled to 6.0–10.0 for display
min_score = df["final_score"].min()
max_score = df["final_score"].max()
def normalize_score(score):
    norm = (score - min_score) / (max_score - min_score)
    return f"{round(norm * 4 + 6, 1)}/10"

# Config
openai.api_key = os.getenv("OPENAI_API_KEY")

GENRE_OPTIONS = sorted({g.strip().title()
    for genre_list in df["genres"]
    for g in str(genre_list).strip("[]").replace("'", "").split(",") if g.strip()})

LENGTH_OPTIONS = {
    "עד 90 דקות": (0, 90),
    "מעל 90 דקות": (91, 1000),
    "לא משנה לי האורך": None
}

MOOD_TO_GENRES = {
    "sad": ["Comedy"],
    "happy": ["Comedy", "Adventure"],
    "angry": ["Action", "Thriller"],
    "bored": ["Fantasy", "Animation"],
    "tired": ["Short", "Family"],
    "romantic": ["Romance", "Comedy"],
    "default": ["Drama", "Adventure"]
}

SESSIONS = {}

# Utils
def is_english(text):
    return bool(re.match(r'^[\x00-\x7F\s.,!?\'"-]+$', text))

def detect_intent(text):
    prompt = f"""
Message: "{text}"
Classify the user's intent:
- greeting
- movie_request
- mood_description
- more
- unrelated
Respond with one label only."""
    try:
        res = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )
        return res.choices[0].message.content.strip().lower()
    except:
        return "unrelated"

def classify(text, category):
    prompt = f"""
Message: "{text}"
Classify the user's {category}:
- For genre: {', '.join(GENRE_OPTIONS)}
- For length: עד 90 דקות, מעל 90 דקות, לא משנה לי האורך
Respond with one phrase or 'Unknown'."""
    try:
        res = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )
        return res.choices[0].message.content.strip().title()
    except:
        return "Unknown"

def guess_genre_from_mood(text):
    mood = text.lower()
    for keyword, genres in MOOD_TO_GENRES.items():
        if keyword in mood:
            return random.choice(genres)
    return random.choice(MOOD_TO_GENRES["default"])

def format_movie_cards(movie_list):
    cards = []
    for _, row in movie_list.iterrows():
        cards.append({
            "title": row["title"],
            "year": int(row["release_year"]),
            "score": normalize_score(row["final_score"])
        })
    return {"cards": cards}

# Chat endpoint
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    messages = data.get("messages", [])
    session_id = data.get("session_id", "default")
    user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "").strip()

    if not is_english(user_msg):
        return jsonify({"response": "❌ English only please."})

    if session_id not in SESSIONS:
        SESSIONS[session_id] = {"genre": None, "length": None, "results": None, "pointer": 0}
    session = SESSIONS[session_id]

    intent = detect_intent(user_msg)

    # Greeting
    if intent == "greeting" or "happy" in user_msg.lower():
        return jsonify({"response": "😄 I love that energy! Let's keep the good vibes going – what kind of movie or length are you in the mood for?"})

    if intent == "more" and session["results"] is not None:
        start = session["pointer"]
        end = start + 5
        next_batch = session["results"].iloc[start:end]
        session["pointer"] = end
        if next_batch.empty:
            return jsonify({"response": "🚫 That's all for now. Try a different genre or vibe!"})
        return jsonify(format_movie_cards(next_batch))

    # Extract genre
    if not session["genre"]:
        g = classify(user_msg, "genre")
        if g in GENRE_OPTIONS:
            session["genre"] = g
        else:
            session["genre"] = guess_genre_from_mood(user_msg)

    # Extract length
    if not session["length"]:
        l = classify(user_msg, "length")
        if l in LENGTH_OPTIONS:
            session["length"] = l

    if not session["genre"]:
        return jsonify({"response": "[[ASK_GENRE]]"})
    if not session["length"]:
        return jsonify({"response": "[[ASK_LENGTH]]"})

    genre = session["genre"].lower()
    length_range = LENGTH_OPTIONS[session["length"]]

    filtered = df[df["genres"].str.lower().str.contains(genre)]

    if length_range:
        filtered = filtered[filtered["runtime"].between(length_range[0], length_range[1])]

    if filtered.empty:
        return jsonify({"response": "😕 I couldn’t find anything with that combo. Try a new vibe or genre?"})

    result_df = filtered.copy()
    result_df = result_df.sample(n=min(40, len(result_df)), weights=result_df["final_score"], random_state=random.randint(1, 9999))

    session["results"] = result_df.reset_index(drop=True)
    session["pointer"] = 5

    intro = f"🍿 Based on your vibe – *{session['genre']}*, {session['length']} – here are some great picks:"
    return jsonify({"response": intro, **format_movie_cards(session["results"].iloc[:5])})

@app.route("/genres", methods=["GET"])
def get_genres():
    return jsonify(sorted(GENRE_OPTIONS))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
