from flask import Flask, request, jsonify
import pandas as pd
import openai
import os
import random
import json
import ast
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

openai.api_key = os.getenv("OPENAI_API_KEY")

movies_df = pd.read_csv("movies.csv")
movies_df = movies_df.dropna(subset=["title", "genres", "runtime", "overview", "release_year", "final_score"])
movies_df = movies_df[movies_df["adult"] == 0]
movies_df["genres"] = movies_df["genres"].astype(str)
movies_df["genre_list"] = movies_df["genres"].apply(lambda x: [g.strip().lower() for g in ast.literal_eval(x)])
movies_df["runtime"] = movies_df["runtime"].astype(float)

LENGTH_OPTIONS = {
    "Up to 90 minutes": (0, 90),
    "Over 90 minutes": (91, 1000),
    "Any length is fine": None
}

GENRE_LIST = sorted(set(g for sublist in movies_df["genre_list"] for g in sublist if g != "adventure"))
SESSIONS = {}

# RATING by quartiles
q1 = movies_df["final_score"].quantile(0.75)
q2 = movies_df["final_score"].quantile(0.50)
q3 = movies_df["final_score"].quantile(0.25)

def score_label(score):
    if score >= q1:
        return ("VERY HIGH!", "green")
    elif score >= q2:
        return ("HIGH", "darkgreen")
    elif score >= q3:
        return ("GOOD", "yellow")
    else:
        return ("NICE", "orange")

def is_english(text):
    return all(ord(c) < 128 for c in text)

def text_to_length(text):
    text = text.lower()
    if any(w in text for w in ["short", "quick", "under 90", "chill", "easy"]):
        return "Up to 90 minutes"
    if any(w in text for w in ["long", "epic", "over 90"]):
        return "Over 90 minutes"
    return None

MOOD_GENRE_MAP = {
    "sad": ["comedy", "fantasy", "animation"],
    "happy": ["action", "comedy", "adventure"],
    "angry": ["thriller", "action", "crime"],
    "romantic": ["romance", "drama", "music"],
    "bored": ["comedy", "adventure", "fantasy"],
    "curious": ["mystery", "sci-fi", "documentary"],
    "nostalgic": ["drama", "romance", "animation"],
    "anxious": ["animation", "family", "fantasy"]
}

MOOD_MESSAGES = {
    "sad": "🌈 You're feeling down. Let's brighten things up!",
    "happy": "😄 You're in a great mood! Let's keep the vibe going.",
    "angry": "🔥 You seem intense. Here’s something to channel that energy.",
    "romantic": "💘 In the mood for love? Let’s find the perfect match.",
    "bored": "🌀 Feeling bored? Let’s spark your curiosity!",
    "curious": "🔍 You're curious? Let's explore something intriguing.",
    "nostalgic": "📼 Feeling nostalgic? Let’s go back in time.",
    "anxious": "🧘 Feeling anxious? Here's something light and comforting."
}

def gpt_analyze(text):
    prompt = f"""
Given the message: "{text}"
Classify the intent and extract info:
- intent: greeting, movie_request, mood_description, unrelated
- mood: if relevant (like sad, happy, romantic), else null
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

def format_cards(df):
    cards = []
    for _, row in df.iterrows():
        label, _ = score_label(row["final_score"])
        cards.append({
            "title": row["title"],
            "year": int(row["release_year"]),
            "score": f"RATING: {label}",
            "genre": row["genre_list"][0].title(),
            "duration": int(row["runtime"])
        })
    return cards

def recommend_movies(session):
    genres = session["genres"]
    length_range = LENGTH_OPTIONS[session["length"]]

    filtered = movies_df[movies_df["genre_list"].apply(lambda g: any(gen in g for gen in genres))]
    if length_range:
        filtered = filtered[filtered["runtime"].between(*length_range)]

    if filtered.empty:
        return jsonify({"response": "😕 No matching movies found. Try a different vibe!"})

    session["results"] = filtered.sample(frac=1).reset_index(drop=True)
    session["pointer"] = 5
    return jsonify({
        "response": "🎬 Here are a few movies we think you'll enjoy:",
        "cards": format_cards(session["results"].iloc[:5])
    })

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    messages = data.get("messages", [])
    session_id = data.get("session_id", "default")
    user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "").strip().lower()

    if not is_english(user_msg):
        return jsonify({"response": "⚠️ English only, please."})

    if session_id not in SESSIONS:
        SESSIONS[session_id] = {"genres": None, "length": None, "results": None, "pointer": 0}
    session = SESSIONS[session_id]

    if "something else" in user_msg:
        session.update({"genres": None, "length": None, "results": None, "pointer": 0})
        return jsonify({"response": "[[ASK_GENRE]]"})

    if user_msg in GENRE_LIST:
        session["genres"] = [user_msg]
    if user_msg in LENGTH_OPTIONS:
        session["length"] = user_msg

    analysis = gpt_analyze(user_msg)

    if not session["length"]:
        guessed = text_to_length(user_msg)
        if guessed:
            session["length"] = guessed

    if analysis["intent"] == "unrelated":
        if session["genres"] and session["length"]:
            return recommend_movies(session)
        return jsonify({"response": "🤖 I'm here to recommend movies. Tell me your mood or favorite genre!"})

    if analysis["intent"] == "greeting":
        return jsonify({"response": "👋 Hey there! What kind of movie are you in the mood for?"})

    if not session["genres"] and analysis["mood"]:
        mood = analysis["mood"].lower()
        if mood in MOOD_GENRE_MAP:
            session["genres"] = MOOD_GENRE_MAP[mood]
            message = MOOD_MESSAGES[mood] + "\n🎬 Choose the duration for your movie below 👇"
            return jsonify({"response": message, "followup": "[[ASK_LENGTH]]"})

    if analysis["genre"]:
        session["genres"] = [analysis["genre"].lower()]

    if analysis["length"] in LENGTH_OPTIONS and not session["length"]:
        session["length"] = analysis["length"]

    if not session["genres"]:
        return jsonify({"response": "[[ASK_GENRE]]"})
    if not session["length"]:
        return jsonify({"response": "[[ASK_LENGTH]]"})

    return recommend_movies(session)

@app.route("/more", methods=["POST"])
def more():
    session = SESSIONS.get(request.get_json().get("session_id", "default"))
    if not session or session.get("results") is None:
        return jsonify({"response": "❌ No session found."})
    start, end = session["pointer"], session["pointer"] + 5
    batch = session["results"].iloc[start:end]
    session["pointer"] = end
    if batch.empty:
        return jsonify({"response": "📭 No more movies!"})
    return jsonify({
        "response": "🎥 Here's more:",
        "cards": format_cards(batch)
    })

@app.route("/summary", methods=["POST"])
def summary():
    title = request.get_json().get("title", "").lower()
    match = movies_df[movies_df["title"].str.lower() == title]
    if match.empty:
        return jsonify({"response": "❌ Sorry, I couldn’t find that movie."})
    return jsonify({"response": match.iloc[0]["overview"]})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
