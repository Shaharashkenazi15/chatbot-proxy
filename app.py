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

# Normalize score to show as X.X/10
min_score = df["final_score"].min()
max_score = df["final_score"].max()
def normalize_score(score):
    norm = (score - min_score) / (max_score - min_score)
    return f"{round(norm * 4 + 6, 1)}/10"

# Options
openai.api_key = os.getenv("OPENAI_API_KEY")
GENRE_OPTIONS = sorted({g.strip().title()
    for genre_list in df["genres"]
    for g in str(genre_list).strip("[]").replace("'", "").split(",") if g.strip()})
LENGTH_OPTIONS = {
    "Up to 90 minutes": (0, 90),
    "Over 90 minutes": (91, 1000),
    "Any length is fine": None
}
MOOD_TO_GENRES = {
    "sad": ["Comedy", "Romance"],
    "happy": ["Action", "Comedy"],
    "angry": ["Thriller", "Action"],
    "bored": ["Adventure", "Fantasy"],
    "tired": ["Animation", "Short"],
    "romantic": ["Romance", "Drama"],
    "default": ["Drama", "Adventure"]
}
SESSIONS = {}

def is_english(text):
    return bool(re.match(r'^[\x00-\x7F\s.,!?\'"-]+$', text))

def detect_intent(text):
    prompt = f"""
Message: "{text}"
Classify the user's intent:
- greeting
- movie_request
- mood_description
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
- For length: Up to 90 minutes, Over 90 minutes, Any length is fine
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
    return None

def format_movie_cards(movie_list):
    cards = []
    for _, row in movie_list.iterrows():
        cards.append({
            "title": row["title"],
            "year": int(row["release_year"]),
            "score": normalize_score(row["final_score"])
        })
    return {"cards": cards}

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    messages = data.get("messages", [])
    session_id = data.get("session_id", "default")
    user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "").strip().lower()

    if not is_english(user_msg):
        return jsonify({"response": "❌ English only please."})

    if session_id not in SESSIONS:
        SESSIONS[session_id] = {"genre": None, "length": None, "results": None, "pointer": 0}
    session = SESSIONS[session_id]

    # "More" button
    if user_msg == "more" and session.get("results") is not None:
        start = session["pointer"]
        end = start + 5
        more_movies = session["results"].iloc[start:end]
        session["pointer"] = end
        if more_movies.empty:
            return jsonify({"response": "🎬 That’s all I got for now – try a different genre or mood?"})
        return jsonify({
            "response": "📽️ Here are more picks for you!",
            **format_movie_cards(more_movies)
        })

    # Intent detection
    intent = detect_intent(user_msg)

    if intent == "unrelated":
        return jsonify({"response": "🤖 I'm here to help with movie recommendations – tell me what you're in the mood for!"})

    if intent == "greeting" or "happy" in user_msg:
        return jsonify({"response": "😄 So good to hear! Let’s find something fun to match your mood. What kind of movie or length are you in the mood for?"})

    # Mood handling
    intro = None
    if intent == "mood_description":
        guessed_genre = guess_genre_from_mood(user_msg)
        if guessed_genre:
            session["genre"] = guessed_genre
            session["length"] = "Up to 90 minutes"
            intro = f"💛 I hear you. Let’s lift your mood with a great *{session['genre']}* movie under 90 minutes."
        else:
            return jsonify({"response": "🎭 Tell me what genre you're in the mood for – I’ll match it with a movie!"})
    else:
        # Try to classify genre and length if not already defined
        if not session["genre"]:
            g = classify(user_msg, "genre")
            if g in GENRE_OPTIONS:
                session["genre"] = g

        if not session["length"]:
            l = classify(user_msg, "length")
            if l in LENGTH_OPTIONS:
                session["length"] = l

    # Handle buttons
    if user_msg.title() in GENRE_OPTIONS:
        session["genre"] = user_msg.title()
    elif user_msg in LENGTH_OPTIONS:
        session["length"] = user_msg

    # Ask missing info
    if not session["genre"]:
        return jsonify({"response": "[[ASK_GENRE]]"})
    if not session["length"]:
        return jsonify({"response": "[[ASK_LENGTH]]"})

    # Filter results
    genre = session["genre"].lower()
    length_range = LENGTH_OPTIONS[session["length"]]

    filtered = df[df["genres"].str.lower().str.contains(genre)]
    if length_range:
        filtered = filtered[filtered["runtime"].between(length_range[0], length_range[1])]

    if filtered.empty:
        return jsonify({"response": "😕 Couldn't find anything for that combo. Try a different vibe or length?"})

    result_df = filtered.copy()
    result_df = result_df.sample(n=min(40, len(result_df)), weights=result_df["final_score"], random_state=random.randint(1, 9999))

    session["results"] = result_df.reset_index(drop=True)
    session["pointer"] = 5

    intro = intro if intro else f"🎥 Based on your choice – *{session['genre']}*, {session['length']} – here are some great picks:"

    return jsonify({"response": intro, **format_movie_cards(session["results"].iloc[:5])})

@app.route("/genres", methods=["GET"])
def get_genres():
    return jsonify(sorted(GENRE_OPTIONS))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
