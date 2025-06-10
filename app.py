from flask import Flask, request, jsonify
import pandas as pd
import openai
import os
import re
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

openai.api_key = os.getenv("OPENAI_API_KEY")

# Load dataset
df = pd.read_csv("movies.csv")
df.dropna(subset=["title", "genres", "runtime", "adult", "final_score"], inplace=True)

# Prepare options
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

sessions = {}

def is_english(text):
    return bool(re.match(r'^[\x00-\x7F\s.,!?\'"-]+$', text))

def classify_text(text, category):
    prompt = f"""
You are a classifier. Analyze this message: "{text}"

Classify the {category} of movie the user might want.
Options for genre: {', '.join(GENRE_OPTIONS)}
Options for length: Short, Medium, Long
Options for audience: Adults Only, All Audiences

Respond ONLY with the one word that matches the value, or "Unknown" if you're not sure.
"""
    try:
        res = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            temperature=0,
            messages=[{"role": "system", "content": prompt}]
        )
        result = res.choices[0].message.content.strip()
        return result
    except:
        return "Unknown"

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    messages = data.get("messages", [])
    user_message = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    session_id = data.get("session_id", "default")

    # Init session if needed
    if session_id not in sessions:
        sessions[session_id] = {"genre": None, "length": None, "adult": None}
    session = sessions[session_id]

    if not is_english(user_message):
        return jsonify({"response": "❌ English only please."})

    # Check if this is a button reply:
    if user_message in GENRE_OPTIONS:
        session["genre"] = user_message
    elif user_message in LENGTH_OPTIONS:
        session["length"] = user_message
    elif user_message in ADULT_OPTIONS:
        session["adult"] = ADULT_OPTIONS[user_message]

    # Try classify missing
    if not session["genre"]:
        result = classify_text(user_message, "genre")
        if result in GENRE_OPTIONS:
            session["genre"] = result
    if not session["length"]:
        result = classify_text(user_message, "length").lower()
        for label in LENGTH_OPTIONS:
            if result in label.lower():
                session["length"] = label
                break
    if session["adult"] is None:
        result = classify_text(user_message, "audience")
        if result.lower().startswith("adult"):
            session["adult"] = True
        elif result.lower().startswith("all"):
            session["adult"] = False

    # Ask if missing
    if not session["genre"]:
        return jsonify({"response": "[[ASK_GENRE]]"})
    if not session["length"]:
        return jsonify({"response": "[[ASK_LENGTH]]"})
    if session["adult"] is None:
        return jsonify({"response": "[[ASK_ADULT]]"})

    # All present – filter by cluster
    genre = session["genre"].lower()
    min_len, max_len = LENGTH_OPTIONS[session["length"]]
    is_adult = session["adult"]

    filtered = df[
        df["genres"].str.lower().str.contains(genre) &
        df["runtime"].between(min_len, max_len) &
        (df["adult"] == is_adult)
    ]

    if filtered.empty:
        return jsonify({"response": "😕 Sorry, no movies found. Try different preferences."})

    top_movies = filtered.sort_values("final_score", ascending=False).head(5)

    reply = "\n\n".join([
        f"🎬 {row['title']} ({int(row['release_year'])})\n"
        f"Genre: {row['genres']}\n"
        f"Length: {int(row['runtime'])} min\n"
        f"Score: {round(row['final_score'], 2)}\n"
        f"Overview: {row['overview']}"
        for _, row in top_movies.iterrows()
    ])

    return jsonify({"response": reply})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
