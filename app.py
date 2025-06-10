from flask import Flask, request, jsonify
import pandas as pd
import openai
import os
import re
import random
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

openai.api_key = os.getenv("OPENAI_API_KEY")

# Load dataset
df = pd.read_csv("movies.csv")
df.dropna(subset=["title", "genres", "runtime_minutes", "adult", "final_score"], inplace=True)

# Define genre list from dataset
def extract_all_genres():
    genre_set = set()
    for genres in df["genres"].dropna():
        for g in genres.strip("[]").replace("'", "").split(","):
            genre_set.add(g.strip().title())
    return sorted(genre_set)

GENRE_OPTIONS = extract_all_genres()
LENGTH_OPTIONS = {
    "short": (0, 90),
    "medium": (91, 120),
    "long": (121, 1000)
}

# Session state
sessions = {}

# Helper: Check if English
def is_english(text):
    return bool(re.match(r'^[\x00-\x7F\s.,!?\'"-]+$', text))

# Helper: Get mood or context using GPT
def is_movie_related(user_input):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            temperature=0,
            messages=[
                {"role": "system", "content": "You are an assistant that classifies if a message is related to movies or not."},
                {"role": "user", "content": f"Is the following message about movies or movie recommendations?\n\n'{user_input}'\n\nAnswer 'yes' or 'no' only."}
            ]
        )
        reply = response.choices[0].message.content.strip().lower()
        return "yes" in reply
    except:
        return False

# Helper: Extract runtime category
def get_runtime_category(runtime):
    for label, (min_r, max_r) in LENGTH_OPTIONS.items():
        if min_r <= runtime <= max_r:
            return label
    return None

# Route
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    messages = data.get("messages", [])
    user_message = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")

    # Reject non-English input
    if not is_english(user_message):
        return jsonify({"response": "❌ This assistant only understands English. Please try again using English only."})

    # Get session ID (or use IP in real use)
    session_id = data.get("session_id", "default")

    if session_id not in sessions:
        sessions[session_id] = {"genre": None, "length": None, "adult": None}

    session = sessions[session_id]

    # Try to detect if related to movies
    if not is_movie_related(user_message):
        return jsonify({"response": "🤖 I'm here to help with movie recommendations. Try telling me your mood or what kind of movie you're looking for!"})

    # Try to extract known labels
    msg_lower = user_message.lower()

    # Detect genre
    if not session["genre"]:
        for genre in GENRE_OPTIONS:
            if genre.lower() in msg_lower:
                session["genre"] = genre
                break

    # Detect length
    if not session["length"]:
        if "short" in msg_lower:
            session["length"] = "short"
        elif "medium" in msg_lower:
            session["length"] = "medium"
        elif "long" in msg_lower:
            session["length"] = "long"

    # Detect adult
    if not session["adult"]:
        if "adult" in msg_lower:
            session["adult"] = True
        elif "family" in msg_lower or "all ages" in msg_lower or "everyone" in msg_lower:
            session["adult"] = False

    # Ask missing info
    if not session["genre"]:
        return jsonify({"response": "[[ASK_GENRE]]"})

    if not session["length"]:
        return jsonify({"response": "[[ASK_LENGTH]]"})

    if session["adult"] is None:
        return jsonify({"response": "[[ASK_ADULT]]"})

    # All info present — filter
    min_len, max_len = LENGTH_OPTIONS[session["length"]]
    genre_str = session["genre"].lower()

    filtered = df[
        df["genres"].str.lower().str.contains(genre_str) &
        (df["runtime_minutes"] >= min_len) &
        (df["runtime_minutes"] <= max_len) &
        (df["adult"] == session["adult"])
    ]

    if filtered.empty:
        return jsonify({"response": "😕 Sorry, I couldn't find matching movies. Try changing the genre or length."})

    sample = filtered.sort_values("final_score", ascending=False).head(25)
    recommendations = []

    for _, row in sample.iterrows():
        recommendations.append(
            f"🎬 {row['title']} ({int(row['release_year'])})\n"
            f"Genre: {row['genres']}\n"
            f"Duration: {int(row['runtime_minutes'])} minutes\n"
            f"⭐ Score: {round(row['final_score'], 2)}\n"
            f"Overview: {row['overview']}"
        )

    response_text = "\n\n".join(recommendations[:5])
    return jsonify({"response": response_text})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
