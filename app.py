from flask import Flask, request, jsonify
import pandas as pd
import openai
import os
from flask_cors import CORS
import re

app = Flask(__name__)
CORS(app)

# Load dataset
df = pd.read_csv("movies.csv")
df.dropna(subset=["title", "genres", "runtime", "adult", "final_score", "cluster_id"], inplace=True)

# Set OpenAI key
openai.api_key = os.getenv("OPENAI_API_KEY")

# Define genre options
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
    prompt = f"""You are a smart assistant. Classify the user intent from this message:
"{user_input}"

Respond only with one of the following:
- greeting
- movie_request
- unrelated
"""
    try:
        res = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )
        return res.choices[0].message.content.strip()
    except:
        return "unrelated"

def classify(text, category):
    prompt = f"""
Message: "{text}"
Classify the user's {category}:
- For genre: {', '.join(GENRE_OPTIONS)}
- For length: Short, Medium, Long
- For audience: Adults Only, All Audiences

Respond only with one word or 'Unknown'
"""
    try:
        res = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )
        return res.choices[0].message.content.strip()
    except:
        return "Unknown"

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    messages = data.get("messages", [])
    session_id = data.get("session_id", "default")
    user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "").strip()

    if not is_english(user_msg):
        return jsonify({"response": "❌ Please use English only."})

    # Init session
    if session_id not in SESSIONS:
        SESSIONS[session_id] = {"genre": None, "length": None, "adult": None}
    session = SESSIONS[session_id]

    # Handle intent
    intent = detect_intent(user_msg)
    if intent == "greeting":
        return jsonify({"response": "👋 Hey there! Tell me what kind of movie you're in the mood for!"})
    elif intent == "unrelated":
        return jsonify({"response": "🤖 I can only help with movie recommendations. Ask me for a genre or mood!"})

    # Check if it's a reply to a button
    if user_msg in GENRE_OPTIONS:
        session["genre"] = user_msg
    elif user_msg in LENGTH_OPTIONS:
        session["length"] = user_msg
    elif user_msg in ADULT_OPTIONS:
        session["adult"] = ADULT_OPTIONS[user_msg]

    # Try classify missing
    if not session["genre"]:
        g = classify(user_msg, "genre")
        if g in GENRE_OPTIONS:
            session["genre"] = g
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

    # Ask missing info
    if not session["genre"]:
        return jsonify({"response": "[[ASK_GENRE]]"})
    if not session["length"]:
        return jsonify({"response": "[[ASK_LENGTH]]"})
    if session["adult"] is None:
        return jsonify({"response": "[[ASK_ADULT]]"})

    # All info present – filter by cluster
    genre = session["genre"].lower()
    min_len, max_len = LENGTH_OPTIONS[session["length"]]
    is_adult = session["adult"]

    matching = df[
        df["genres"].str.lower().str.contains(genre) &
        df["runtime"].between(min_len, max_len) &
        (df["adult"] == is_adult)
    ]

    if matching.empty:
        return jsonify({"response": "😕 No matching movies found. Try different preferences."})

    # Get best 25 from same cluster
    cluster_id = matching["cluster_id"].mode().iloc[0]
    final = df[df["cluster_id"] == cluster_id].sort_values("final_score", ascending=False).head(25)

    results = []
    for _, row in final.iterrows():
        results.append(
            f"🎬 {row['title']} ({int(row['release_year'])})\n"
            f"Genre: {row['genres']}\n"
            f"Length: {int(row['runtime'])} min\n"
            f"Score: {round(row['final_score'], 2)}\n"
            f"Overview: {row['overview']}"
        )

    return jsonify({"response": "\n\n".join(results)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
