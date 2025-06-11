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

# Normalize scores to 6–10
min_score = movies_df["final_score"].min()
max_score = movies_df["final_score"].max()
def normalize_score(score):
    norm = (score - min_score) / (max_score - min_score)
    return f"{round(norm * 4 + 6, 1)}/10"

# Length options
LENGTH_OPTIONS = {
    "Up to 90 minutes": (0, 90),
    "Over 90 minutes": (91, 1000),
    "Any length is fine": None
}
GENRE_LIST = sorted(set(g for sublist in movies_df["genre_list"] for g in sublist))

SESSIONS = {}

# GPT analysis function
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
        content = res.choices[0].message.content.strip()
        return json.loads(content)
    except Exception as e:
        print("GPT Error:", e)
        return {"intent": "unrelated", "mood": None, "genre": None, "length": None}

def format_cards(df):
    cards = []
    for _, row in df.iterrows():
        cards.append({
            "title": row["title"],
            "year": int(row["release_year"]),
            "score": normalize_score(row["final_score"]),
            "genre": row["genre_list"][0].capitalize() if row["genre_list"] else "Unknown"
        })
    return cards

def recommend_movies(session):
    genre = session["genre"].lower()
    length_range = LENGTH_OPTIONS[session["length"]]

    filtered = movies_df[movies_df["genre_list"].apply(lambda genres: genre in genres)]
    if length_range:
        filtered = filtered[filtered["runtime"].between(length_range[0], length_range[1])]

    if filtered.empty:
        return jsonify({"response": "😕 Couldn't find movies with that combo. Try another mood or genre."})

    session["results"] = filtered.sample(frac=1, random_state=random.randint(1,999)).reset_index(drop=True)
    session["pointer"] = 5

    return jsonify({
        "response": f"🎬 Here are some *{session['genre']}* movies {session['length']}:",
        "cards": format_cards(session["results"].iloc[:5])
    })

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    messages = data.get("messages", [])
    session_id = data.get("session_id", "default")
    user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "").strip()

    if session_id not in SESSIONS:
        SESSIONS[session_id] = {"genre": None, "length": None, "results": None, "pointer": 0}
    session = SESSIONS[session_id]

    # Detect button click genre or length
    if user_msg.lower() in GENRE_LIST:
        session["genre"] = user_msg.title()
    if user_msg in LENGTH_OPTIONS:
        session["length"] = user_msg

    analysis = gpt_analyze(user_msg)

    if analysis["intent"] == "unrelated":
        if session["genre"] and session["length"]:
            return recommend_movies(session)
        else:
            return jsonify({"response": "🤖 I'm here to help with movie recommendations. Tell me your mood or genre!"})

    if analysis["intent"] == "greeting":
        return jsonify({"response": "👋 Hey there! Tell me how you're feeling or what kind of movie you're in the mood for."})

    if not session["genre"] and analysis["genre"]:
        session["genre"] = analysis["genre"].strip().title()
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

    return jsonify({"response": "🎥 Here's more:", "cards": format_cards(next_batch)})

@app.route("/summary", methods=["POST"])
def summary():
    title = request.get_json().get("title", "").lower()
    match = movies_df[movies_df["title"].str.lower() == title]
    if match.empty:
        return jsonify({"response": "❌ Sorry, I couldn’t find that movie."})
    return jsonify({"response": f"📝 *{title.title()}* – {match.iloc[0]['overview']}"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
