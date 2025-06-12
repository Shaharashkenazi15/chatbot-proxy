from flask import Flask, request, jsonify
import pandas as pd
import openai
import os
import json
import ast
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

openai.api_key = os.getenv("OPENAI_API_KEY")

# Load and prepare data
movies_df = pd.read_csv("movies.csv")
movies_df = movies_df.dropna(subset=["title", "genres", "runtime", "overview", "release_year", "final_score"])
movies_df = movies_df[movies_df["adult"] == 0]
movies_df["genres"] = movies_df["genres"].astype(str)
movies_df["genre_list"] = movies_df["genres"].apply(lambda x: [g.strip().lower() for g in ast.literal_eval(x)])
movies_df["runtime"] = movies_df["runtime"].astype(float)

# RATING by quartiles
quantiles = movies_df["final_score"].quantile([0.25, 0.5, 0.75])
def rating_label(score):
    if score >= quantiles[0.75]:
        return ("RATING: VERY HIGH!", "green")
    elif score >= quantiles[0.5]:
        return ("RATING: HIGH", "darkgreen")
    elif score >= quantiles[0.25]:
        return ("RATING: GOOD", "orange")
    else:
        return ("RATING: NICE", "lightcoral")

# Options
LENGTH_OPTIONS = {
    "Up to 90 minutes": (0, 90),
    "Over 90 minutes": (91, 1000),
    "Any length is fine": None
}
GENRE_LIST = sorted(set(g for sublist in movies_df["genre_list"] for g in sublist if g != "adventure"))
MOOD_GENRE_MAP = {
    "sad": ["comedy", "fantasy", "animation"],
    "happy": ["action", "comedy", "adventure"],
    "angry": ["thriller", "action", "crime"],
    "romantic": ["romance", "drama"],
    "bored": ["mystery", "adventure", "fantasy"],
    "excited": ["sci-fi", "action", "adventure"]
}
MOOD_ALIAS = {"mad": "angry", "furious": "angry", "glad": "happy"}
SESSIONS = {}

# Helpers
def is_english(text):
    return all(ord(c) < 128 for c in text)

def text_to_length(text):
    text = text.lower()
    if any(w in text for w in ["short", "quick", "under 90", "chill", "relaxed"]):
        return "Up to 90 minutes"
    if any(w in text for w in ["long", "epic", "over 90"]):
        return "Over 90 minutes"
    return None

def gpt_analyze(text):
    prompt = f"""
Given the message: "{text}"
Classify the intent and extract:
- intent: greeting, movie_request, mood_description, unrelated
- mood: if relevant (like sad, happy), else null
- genre: if mentioned (like action, comedy), else null
- length: "Up to 90 minutes", "Over 90 minutes", "Any length is fine" or null
Respond in JSON like:
{{"intent": "...", "mood": "...", "genre": "...", "length": "..."}}
"""
    try:
        res = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        return json.loads(res.choices[0].message.content.strip())
    except:
        return {"intent": "unrelated", "mood": None, "genre": None, "length": None}

def format_cards(df, session):
    cards = []
    for _, row in df.iterrows():
        label, color = rating_label(row["final_score"])
        chosen_genre = next((g.capitalize() for g in session["genres"] if g in row["genre_list"]), row["genre_list"][0].capitalize())
        cards.append({
            "title": row["title"],
            "year": int(row["release_year"]),
            "score": label,
            "genre": chosen_genre,
            "duration": int(row["runtime"]),
            "color": color
        })
    return cards

def recommend_movies(session):
    genres = session["genres"]
    length_range = LENGTH_OPTIONS[session["length"]]
    filtered = movies_df[movies_df["genre_list"].apply(lambda lst: any(g in lst for g in genres))]
    if length_range:
        filtered = filtered[filtered["runtime"].between(*length_range)]
    if filtered.empty:
        return jsonify({"response": "😕 No movies found for that mood and length.", "typing": False})
    session["results"] = filtered.sample(frac=1).reset_index(drop=True)
    session["pointer"] = 5
    return jsonify({
        "response": "🎬 Here are a few movies we think you'll enjoy:",
        "cards": format_cards(session["results"].iloc[:5], session),
        "typing": False
    })

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    messages = data.get("messages", [])
    session_id = data.get("session_id", "default")
    user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "").strip()

    if not is_english(user_msg):
        return jsonify({"response": "⚠️ Please write in English only.", "typing": False})

    if session_id not in SESSIONS:
        SESSIONS[session_id] = {"genres": None, "length": None, "results": None, "pointer": 0}
    session = SESSIONS[session_id]

    if any(kw in user_msg.lower() for kw in ["something else", "another option", "change it", "different movie"]):
        session["genres"] = None
        session["length"] = None
        session["results"] = None
        session["pointer"] = 0
        return jsonify({"response": "[[ASK_GENRE]]", "typing": False})

    if user_msg.lower() in GENRE_LIST:
        session["genres"] = [user_msg.lower()]
        if session["length"]:
            return recommend_movies(session)
        return jsonify({"response": "[[ASK_LENGTH]]", "typing": False})

    guessed = text_to_length(user_msg)
    analysis = gpt_analyze(user_msg)

    mood = (analysis["mood"] or "").lower()
    if mood in MOOD_ALIAS:
        mood = MOOD_ALIAS[mood]

    if mood in MOOD_GENRE_MAP:
        session["genres"] = MOOD_GENRE_MAP[mood]
        session["length"] = None
        return jsonify({
            "response": f"💡 Feeling {mood}? Let's find you something great! 🎬\nChoose the duration for your movie below 👇",
            "followup": "[[ASK_LENGTH]]",
            "typing": False
        })

    if analysis["genre"]:
        session["genres"] = [analysis["genre"].lower()]
        if session["length"] or guessed:
            session["length"] = session["length"] or guessed
            return recommend_movies(session)
        return jsonify({"response": "[[ASK_LENGTH]]", "typing": False})

    if not session["length"]:
        session["length"] = analysis["length"] or guessed

    if analysis["intent"] == "greeting":
        return jsonify({
            "response": "👋 Hey there! Tell me how you're feeling or what kind of movie you're in the mood for.",
            "typing": False
        })

    if not session["genres"]:
        return jsonify({"response": "[[ASK_GENRE]]", "typing": False})
    if not session["length"]:
        return jsonify({"response": "[[ASK_LENGTH]]", "typing": False})

    return recommend_movies(session)

@app.route("/more", methods=["POST"])
def more():
    session_id = request.get_json().get("session_id", "default")
    session = SESSIONS.get(session_id)
    if not session or session.get("results") is None:
        return jsonify({"response": "❌ No session found.", "typing": False})
    start, end = session["pointer"], session["pointer"] + 5
    batch = session["results"].iloc[start:end]
    session["pointer"] = end
    if batch.empty:
        return jsonify({"response": "📭 No more movies!", "typing": False})
    return jsonify({
        "response": "🎥 Here's more:",
        "cards": format_cards(batch, session),
        "typing": False
    })

@app.route("/summary", methods=["POST"])
def summary():
    title = request.get_json().get("title", "").lower()
    match = movies_df[movies_df["title"].str.lower() == title]
    if match.empty:
        return jsonify({"response": "❌ Couldn't find that movie.", "typing": False})
    return jsonify({"response": match.iloc[0]["overview"], "typing": False})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
