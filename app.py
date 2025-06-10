# Updated Flask backend for Smart Movie Chat with smarter greeting handling
from flask import Flask, request, jsonify
import pandas as pd
import openai
import os
import re
import random
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Load dataset
df = pd.read_csv("movies.csv")
df.dropna(subset=["title", "genres", "runtime", "adult", "final_score", "cluster_id"], inplace=True)

df["adult"] = df["adult"].astype(bool)
openai.api_key = os.getenv("OPENAI_API_KEY")

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

SESSIONS = {}

def is_english(text):
    return bool(re.match(r'^[\x00-\x7F\s.,!?\'"-]+$', text))

def detect_intent(user_input):
    prompt = f"""Classify the user intent from this message:
"{user_input}"
Respond only with:
- greeting
- movie_request
- unrelated"""
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
Respond only with one word or 'Unknown'"""
    try:
        res = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )
        return res.choices[0].message.content.strip()
    except:
        return "Unknown"

def suggest_genre_by_mood(text):
    prompt = f"""Based on the user's mood in this message: "{text}"
Which movie genre might help them feel better or match their vibe?
Choose ONLY from: {', '.join(GENRE_OPTIONS)}. Respond with one word only."""
    try:
        res = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}]
        )
        result = res.choices[0].message.content.strip()
        return result if result in GENRE_OPTIONS else None
    except:
        return None

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    messages = data.get("messages", [])
    session_id = data.get("session_id", "default")
    user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "").strip()

    if not is_english(user_msg):
        return jsonify({"response": "❌ English only please."})

    if session_id not in SESSIONS:
        SESSIONS[session_id] = {"genre": None, "length": None, "adult": None}
    session = SESSIONS[session_id]

    intent = detect_intent(user_msg)
    if intent == "unrelated":
        return jsonify({"response": "🤖 I'm here to help you discover great movies. Tell me how you're feeling or what you're in the mood for!"})
    if intent == "greeting":
        greeting_msg = "👋 Hey! I'm here to help you find the perfect movie. What's your vibe today?"
        # Continue processing even after greeting
        genre = classify(user_msg, "genre")
        if genre in GENRE_OPTIONS:
            session["genre"] = genre
        else:
            mood_based = suggest_genre_by_mood(user_msg)
            if mood_based:
                session["genre"] = mood_based
        return jsonify({"response": greeting_msg})

    # Handle button replies
    if user_msg in GENRE_OPTIONS:
        session["genre"] = user_msg
    elif user_msg in LENGTH_OPTIONS:
        session["length"] = user_msg
    elif user_msg in ADULT_OPTIONS:
        session["adult"] = ADULT_OPTIONS[user_msg]

    # Try to classify if not already known
    if not session["genre"]:
        genre = classify(user_msg, "genre")
        if genre in GENRE_OPTIONS:
            session["genre"] = genre
        else:
            mood_based = suggest_genre_by_mood(user_msg)
            if mood_based:
                session["genre"] = mood_based

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

    # Ask for missing info
    if not session["genre"]:
        return jsonify({"response": "[[ASK_GENRE]]"})
    if not session["length"]:
        return jsonify({"response": "[[ASK_LENGTH]]"})
    if session["adult"] is None:
        return jsonify({"response": "[[ASK_ADULT]]"})

    # Filter and recommend from cluster
    genre = session["genre"].lower()
    min_len, max_len = LENGTH_OPTIONS[session["length"]]
    is_adult = session["adult"]

    filtered = df[
        df["genres"].str.lower().str.contains(genre) &
        df["runtime"].between(min_len, max_len) &
        (df["adult"] == is_adult)
    ]

    if filtered.empty:
        return jsonify({"response": "😕 No movies found for your preferences. Try another combo."})

    cluster_id = filtered["cluster_id"].mode().iloc[0]
    result_df = df[df["cluster_id"] == cluster_id].copy()
    sample_size = min(40, len(result_df))
    result_df = result_df.sample(n=sample_size, weights=result_df["final_score"], random_state=random.randint(1,10000))

    response = []
    for _, row in result_df.iterrows():
        response.append(
            f"🎬 {row['title']} ({int(row['release_year'])})\n"
            f"Genre: {row['genres']}\n"
            f"Length: {int(row['runtime'])} min\n"
            f"Score: {round(row['final_score'], 2)}\n"
            f"Overview: {row['overview']}"
        )

    return jsonify({"response": "\n\n".join(response)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
