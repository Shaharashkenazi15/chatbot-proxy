from flask import Flask, request, jsonify
import pandas as pd
import openai
import os
import random
import re
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

openai.api_key = os.getenv("OPENAI_API_KEY")

# Load and clean dataset
df = pd.read_csv("movies.csv")
df = df[df["adult"] == 0]
df = df.dropna(subset=["title", "genres", "runtime", "overview", "release_year", "final_score"])
df["genres"] = df["genres"].astype(str)
df["runtime"] = df["runtime"].astype(float)
df["final_score"] = df["final_score"].astype(float)

# Normalize scores to 6–10
min_score, max_score = df["final_score"].min(), df["final_score"].max()
def normalize_score(s): return f"{round((s - min_score) / (max_score - min_score) * 4 + 6, 1)}/10"

# Mood → genres (לוקאלי)
MOOD_GENRES = {
    "sad": ["Comedy", "Romance"],
    "happy": ["Action", "Comedy"],
    "angry": ["Thriller", "Action"],
    "bored": ["Adventure", "Fantasy"],
    "tired": ["Animation", "Short"],
    "romantic": ["Romance", "Drama"],
    "upset": ["Comedy"]
}

LENGTH_OPTIONS = {
    "Up to 90 minutes": (0, 90),
    "Over 90 minutes": (91, 1000),
    "Any length is fine": None
}

SESSIONS = {}

# GPT: Classify intent of the message
def detect_intent(text):
    prompt = f"""
Message: "{text}"
Classify the user's intent into one of the following:
- greeting
- mood_description
- movie_request
- unrelated
Respond with one word only.
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

# Try to detect mood locally
def detect_mood(text):
    text = text.lower()
    for mood in MOOD_GENRES:
        if mood in text:
            return mood
    return None

def format_cards(df_part):
    cards = []
    for _, row in df_part.iterrows():
        genre = row["genres"].split(",")[0].strip()
        cards.append({
            "title": row["title"],
            "year": int(row["release_year"]),
            "score": normalize_score(row["final_score"]),
            "genre": genre
        })
    return cards

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    messages = data.get("messages", [])
    session_id = data.get("session_id", "default")
    user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "").strip()

    if session_id not in SESSIONS:
        SESSIONS[session_id] = {"genre": None, "length": None, "results": None, "pointer": 0}
    session = SESSIONS[session_id]

    intent = detect_intent(user_msg)

    if intent == "unrelated":
        return jsonify({"response": "🤖 I'm here to help with movie recommendations. Try telling me your mood or genre!"})

    if intent == "greeting":
        return jsonify({"response": "👋 Hey there! Tell me how you're feeling or what kind of movie you're in the mood for."})

    if intent == "mood_description" and not session["genre"]:
        mood = detect_mood(user_msg)
        if mood:
            session["genre"] = random.choice(MOOD_GENRES[mood])
            return jsonify({
                "response": f"💛 I hear you. Let’s lift your mood with a great *{session['genre']}* movie. What length do you prefer?",
                "ask_length": True
            })

    if user_msg in LENGTH_OPTIONS:
        session["length"] = user_msg

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
        return jsonify({"response": "😕 Couldn't find anything with that combo. Try a different vibe or time length."})

    session["results"] = filtered.sample(frac=1, random_state=random.randint(1,999)).reset_index(drop=True)
    session["pointer"] = 5

    return jsonify({
        "response": f"🎬 Here's a list of *{session['genre']}* movies {session['length']} just for you!",
        "cards": format_cards(session["results"].iloc[:5])
    })

@app.route("/more", methods=["POST"])
def more():
    session_id = request.get_json().get("session_id", "default")
    session = SESSIONS.get(session_id)
    if not session or not session.get("results") is not None:
        return jsonify({"response": "❌ No movies found yet. Please start with your mood or genre first."})

    start = session["pointer"]
    end = start + 5
    batch = session["results"].iloc[start:end]
    session["pointer"] = end

    if batch.empty:
        return jsonify({"response": "📭 No more movies found in this batch."})
    
    return jsonify({
        "response": "🎥 More movies coming right up:",
        "cards": format_cards(batch)
    })

@app.route("/summary", methods=["POST"])
def summary():
    title = request.get_json().get("title", "").lower()
    match = df[df["title"].str.lower() == title]
    if match.empty:
        return jsonify({"response": "❌ Couldn't find that movie."})
    return jsonify({"response": f"📝 *{title.title()}* – {match.iloc[0]['overview']}"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
