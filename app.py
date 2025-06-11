from flask import Flask, request, jsonify
import pandas as pd
import openai
import os
import random
import re
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Load data
df = pd.read_csv("movies.csv")
df.dropna(subset=["title", "genres", "runtime", "final_score", "cluster_id", "release_year"], inplace=True)
df["runtime"] = df["runtime"].astype(float)
df["final_score"] = df["final_score"].astype(float)
df = df[df["runtime"] >= 60]
df = df[df["final_score"].between(1.0, 10.0)]  # לשמור על סינון סביר
if "adult" in df.columns:
    df = df[df["adult"] == False]

# Normalize final_score
min_score = df["final_score"].min()
max_score = df["final_score"].max()
def normalize_score(score):
    norm = (score - min_score) / (max_score - min_score)
    return f"{round(norm * 9 + 1, 1)}/10"

# Settings
openai.api_key = os.getenv("OPENAI_API_KEY")
GENRE_OPTIONS = sorted({g.strip().title()
    for genre_list in df["genres"]
    for g in str(genre_list).strip("[]").replace("'", "").split(",") if g.strip()})

LENGTH_OPTIONS = {
    "Short (up to 90 min)": (0, 90),
    "Medium (91-120 min)": (91, 120),
    "Long (over 120 min)": (121, 1000)
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

# Helpers
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
- For length: Short, Medium, Long
Respond with one word or 'Unknown'."""
    try:
        res = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )
        return res.choices[0].message.content.strip()
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

# Routes
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

    # greeting
    if intent == "greeting":
        return jsonify({"response": "👋 Hey there! I’d love to help you find a movie. What genre or vibe are you in the mood for?"})

    # save quick genre/length
    genre = classify(user_msg, "genre")
    if genre in GENRE_OPTIONS:
        session["genre"] = genre

    if not session["length"]:
        l = classify(user_msg, "length").lower()
        for label in LENGTH_OPTIONS:
            if l in label.lower():
                session["length"] = label
                break

    # handle 'more'
    if intent == "more" and session["results"] is not None:
        start = session["pointer"]
        end = start + 5
        next_batch = session["results"].iloc[start:end]
        session["pointer"] = end
        if next_batch.empty:
            return jsonify({"response": "😕 That’s all I’ve got for now. Try another genre or mood!"})
        return jsonify(format_movie_cards(next_batch))

    # if no genre from text, guess by mood
    if not session["genre"]:
        session["genre"] = guess_genre_from_mood(user_msg)

    # if still missing info
    if not session["genre"]:
        return jsonify({"response": "[[ASK_GENRE]]"})
    if not session["length"]:
        return jsonify({"response": "[[ASK_LENGTH]]"})

    # filter and recommend
    genre = session["genre"].lower()
    min_len, max_len = LENGTH_OPTIONS[session["length"]]

    filtered = df[
        df["genres"].str.lower().str.contains(genre) &
        df["runtime"].between(min_len, max_len)
    ]

    if filtered.empty:
        return jsonify({"response": "😕 I couldn’t find any movies with that combo. Want to try a different vibe or length?"})

    cluster_id = filtered["cluster_id"].mode().iloc[0]
    result_df = df[
        (df["cluster_id"] == cluster_id) &
        df["runtime"].between(min_len, max_len)
    ].copy()

    result_df = result_df.sample(n=min(40, len(result_df)), weights=result_df["final_score"], random_state=random.randint(1, 9999))
    session["results"] = result_df.reset_index(drop=True)
    session["pointer"] = 5

    intro = f"🍿 Awesome! Since you're into *{session['genre']}* and prefer *{session['length']}* movies, here are 5 picks I think you'll enjoy:"
    return jsonify({"response": intro, **format_movie_cards(session["results"].iloc[:5])})

@app.route("/genres", methods=["GET"])
def get_genres():
    return jsonify(sorted(GENRE_OPTIONS))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
