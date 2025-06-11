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

# Load data
movies_df = pd.read_csv("movies.csv")
movies_df = movies_df.dropna(subset=["title", "genres", "runtime", "overview", "release_year", "final_score"])
movies_df = movies_df[movies_df["adult"] == 0]
movies_df["genres"] = movies_df["genres"].astype(str)
movies_df["genre_list"] = movies_df["genres"].apply(lambda x: [g.strip().lower() for g in ast.literal_eval(x)])
movies_df["runtime"] = movies_df["runtime"].astype(float)

# Normalize rating to max = 10
max_score = movies_df["final_score"].max()
def normalize_score(score):
    return f"{round((score / max_score) * 10, 1)}/10"

LENGTH_OPTIONS = {
    "Up to 90 minutes": (0, 90),
    "Over 90 minutes": (91, 1000),
    "Any length is fine": None
}
GENRE_LIST = sorted(set(g for sublist in movies_df["genre_list"] for g in sublist if g != "adventure"))
SESSIONS = {}

MOOD_GENRE_MAP = {
    "sad": [
        ("Comedy", "A comedy can bring some joy."),
        ("Fantasy", "Fantasy might help you escape for a while."),
        ("Animation", "Animation is often light and uplifting.")
    ],
    "happy": [
        ("Action", "Action fits your energetic vibe!"),
        ("Comedy", "Even more laughs for your good mood."),
        ("Adventure", "Let’s go on an adventure with you!")
    ],
    "angry": [
        ("Thriller", "A thriller can match your intense mood."),
        ("Action", "Channel that energy into an action-packed ride."),
        ("Crime", "Something gritty might hit the spot.")
    ]
}

def is_english(text):
    return all(ord(c) < 128 for c in text)

def text_to_length(text):
    text = text.lower()
    if any(word in text for word in ["short", "quick", "not long", "under 90", "קצר", "קליל", "רגוע"]):
        return "Up to 90 minutes"
    elif any(word in text for word in ["long", "epic", "over 90", "ארוך"]):
        return "Over 90 minutes"
    return None

def mood_to_genre(mood):
    mood = (mood or "").lower()
    if mood in MOOD_GENRE_MAP:
        genre, message = random.choice(MOOD_GENRE_MAP[mood])
        return genre, f"💡 You seem {mood}. {message}"
    return None, None

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
            temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )
        return json.loads(res.choices[0].message.content.strip())
    except Exception as e:
        print("GPT Error:", e)
        return {"intent": "unrelated", "mood": None, "genre": None, "length": None}

def format_cards(df, genre=None):
    cards = []
    for _, row in df.iterrows():
        cards.append({
            "title": row["title"],
            "year": int(row["release_year"]),
            "score": normalize_score(row["final_score"]),
            "genre": genre.title() if genre else row["genre_list"][0].capitalize(),
            "duration": int(row["runtime"])
        })
    return cards

def recommend_movies(session):
    genre = session["genre"].lower()
    length_range = LENGTH_OPTIONS[session["length"]]

    filtered = movies_df[movies_df["genre_list"].apply(lambda genres: genre in genres)]
    if length_range:
        filtered = filtered[filtered["runtime"].between(length_range[0], length_range[1])]

    if filtered.empty:
        count = movies_df[movies_df["genre_list"].apply(lambda g: genre in g)].shape[0]
        return jsonify({"response": f"😕 Couldn't find matching movies. There are {count} movies with the genre '{genre}', but none matching your length filter."})

    session["results"] = filtered.sample(frac=1, random_state=random.randint(1,999)).reset_index(drop=True)
    session["pointer"] = 5

    response_text = f"🎬 Here are some *{session['genre']}* movies {session['length']}:"
    if session.get("mood_message"):
        response_text = f"{session['mood_message']}\n\n" + response_text
        session["mood_message"] = None

    return jsonify({
        "response": response_text,
        "cards": format_cards(session["results"].iloc[:5], genre=session["genre"])
    })

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    messages = data.get("messages", [])
    session_id = data.get("session_id", "default")
    user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "").strip()

    if not is_english(user_msg):
        return jsonify({"response": "⚠️ Please write in English only."})

    if session_id not in SESSIONS:
        SESSIONS[session_id] = {"genre": None, "length": None, "results": None, "pointer": 0}
    session = SESSIONS[session_id]

    if user_msg.lower() in GENRE_LIST:
        session["genre"] = user_msg.title()
        session["mood_message"] = None
    if user_msg in LENGTH_OPTIONS:
        session["length"] = user_msg

    analysis = gpt_analyze(user_msg)

    if not session["length"]:
        text_length = text_to_length(user_msg)
        if text_length:
            session["length"] = text_length

    if analysis["intent"] == "unrelated":
        if session["genre"] and session["length"]:
            return recommend_movies(session)
        return jsonify({"response": "🤖 I'm here to help with movie recommendations. Tell me your mood or genre!"})

    if analysis["intent"] == "greeting":
        return jsonify({"response": "👋 Hey there! Tell me how you're feeling or what kind of movie you're in the mood for."})

    if not session["genre"]:
        mood_genre, mood_message = mood_to_genre(analysis["mood"])
        if mood_genre:
            session["genre"] = mood_genre
            session["mood_message"] = mood_message

    if analysis["genre"]:
        session["genre"] = analysis["genre"].strip().title()
        session["mood_message"] = None

    if not session["length"] and analysis["length"] in LENGTH_OPTIONS:
        session["length"] = analysis["length"]

    if not session["genre"]:
        return jsonify({"response": "[[ASK_GENRE]]"})
    if not session["length"]:
        return jsonify({"response": "[[ASK_LENGTH]]"})

    return recommend_movies(session)

@app.route("/more", methods=["POST"])
def more():
    session_id = request.get_json().get("session_id", "default")
    session = SESSIONS.get(session_id)
    if not session or session.get("results") is None:
        return jsonify({"response": "❌ No session found. Start by telling me your mood."})

    start, end = session["pointer"], session["pointer"] + 5
    next_batch = session["results"].iloc[start:end]
    session["pointer"] = end

    if next_batch.empty:
        return jsonify({"response": "📭 No more movies in this batch."})

    return jsonify({
        "response": "🎥 Here's more:",
        "cards": format_cards(next_batch, genre=session["genre"])
    })

@app.route("/summary", methods=["POST"])
def summary():
    title = request.get_json().get("title", "").lower()
    match = movies_df[movies_df["title"].str.lower() == title]
    if match.empty:
        return jsonify({"response": "❌ Sorry, I couldn’t find that movie."})
    return jsonify({"response": match.iloc[0]['overview']})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
