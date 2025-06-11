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
df.dropna(subset=["title", "genres", "runtime", "adult", "final_score", "cluster_id"], inplace=True)
df["runtime"] = df["runtime"].astype(float)
df["adult"] = df["adult"].astype(bool)

# Set API key
openai.api_key = os.getenv("OPENAI_API_KEY")

# Constants
GENRE_OPTIONS = sorted({g.strip().title()
    for genre_list in df["genres"]
    for g in str(genre_list).strip("[]").replace("'", "").split(",") if g.strip()})

LENGTH_OPTIONS = {
    "Short (up to 90 min)": (0, 90),
    "Medium (91-120 min)": (91, 120),
    "Long (over 120 min)": (121, 1000)
}

ADULT_OPTIONS = {
    "All Audiences": False,
    "Adults Only": True
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

# Helpers
def is_english(text):
    return bool(re.match(r'^[\x00-\x7F\s.,!?\'"-]+$', text))

def detect_intent_gpt(text):
    prompt = f"""
Given this message: "{text}"
Classify the intent:
- greeting
- movie_request
- mood_description
- more
- unrelated
Respond with just one label.
"""
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
- For audience: Adults Only, All Audiences
Respond only with one word or 'Unknown'."""
    try:
        res = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )
        return res.choices[0].message.content.strip()
    except:
        return "Unknown"

def extract_genre_from_mood(text):
    mood_text = text.lower()
    for mood, genres in MOOD_TO_GENRES.items():
        if mood in mood_text:
            return random.choice(genres)
    return random.choice(MOOD_TO_GENRES["default"])

def format_movies(movie_list):
    response = []
    for _, row in movie_list.iterrows():
        response.append(
            f"🎬 {row['title']} ({int(row['release_year'])})\n"
            f"Genre: {row['genres']}\n"
            f"Length: {int(row['runtime'])} min\n"
            f"Score: {round(row['final_score'], 2)}\n"
            f"Overview: {row['overview']}"
        )
    return "\n\n".join(response)

# Main chat endpoint
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    messages = data.get("messages", [])
    session_id = data.get("session_id", "default")
    user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "").strip()

    if not is_english(user_msg):
        return jsonify({"response": "❌ English only please."})

    if session_id not in SESSIONS:
        SESSIONS[session_id] = {"genre": None, "length": None, "adult": None, "results": None, "pointer": 0}
    session = SESSIONS[session_id]

    # Detect intent
    intent = detect_intent_gpt(user_msg)

    if intent == "greeting":
        return jsonify({"response": "👋 Hey! I'm here to help you find the perfect movie. What's your mood or vibe today?"})

    if intent == "more" and session["results"] is not None:
        start = session["pointer"]
        end = start + 5
        next_batch = session["results"].iloc[start:end]
        session["pointer"] = end
        if next_batch.empty:
            return jsonify({"response": "🚫 No more results. Try another mood or genre!"})
        return jsonify({"response": format_movies(next_batch)})

    if not session["genre"]:
        genre = classify(user_msg, "genre")
        if genre in GENRE_OPTIONS:
            session["genre"] = genre
        else:
            session["genre"] = extract_genre_from_mood(user_msg)

    if not session["length"]:
        l = classify(user_msg, "length").lower()
        for label in LENGTH_OPTIONS:
            if l in label.lower():
                session["length"] = label
                break

    if session["adult"] is None:
        a = classify(user_msg, "audience").lower()
        if "adult" in a:
            session["adult"] = True
        elif "all" in a:
            session["adult"] = False

    # Handle direct option selections
    if user_msg in GENRE_OPTIONS:
        session["genre"] = user_msg
    elif user_msg in LENGTH_OPTIONS:
        session["length"] = user_msg
    elif user_msg in ADULT_OPTIONS:
        session["adult"] = ADULT_OPTIONS[user_msg]

    # Ask for missing
    if not session["genre"]:
        return jsonify({"response": "[[ASK_GENRE]]"})
    if not session["length"]:
        return jsonify({"response": "[[ASK_LENGTH]]"})
    if session["adult"] is None:
        return jsonify({"response": "[[ASK_ADULT]]"})

    # Filter and recommend
    genre = session["genre"].lower()
    min_len, max_len = LENGTH_OPTIONS[session["length"]]
    is_adult = session["adult"]

    filtered = df[
        df["genres"].str.lower().str.contains(genre) &
        df["runtime"].between(min_len, max_len) &
        (df["adult"] == is_adult)
    ]

    if filtered.empty:
        return jsonify({"response": "😕 No movies found for your preferences. Try another mood or genre!"})

    cluster_id = filtered["cluster_id"].mode().iloc[0]
    result_df = df[(df["cluster_id"] == cluster_id) & df["runtime"].between(min_len, max_len)].copy()

    sample_size = min(40, len(result_df))
    result_df = result_df.sample(n=sample_size, weights=result_df["final_score"], random_state=random.randint(1, 9999))

    session["results"] = result_df.reset_index(drop=True)
    session["pointer"] = 5

    return jsonify({"response": format_movies(session["results"].iloc[:5])})

# Genres API for dynamic buttons
@app.route("/genres", methods=["GET"])
def get_genres():
    return jsonify(sorted(GENRE_OPTIONS))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
