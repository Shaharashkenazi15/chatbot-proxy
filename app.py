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

# דירוג מילולי לפי שלישים
q33 = movies_df["final_score"].quantile(0.33)
q66 = movies_df["final_score"].quantile(0.66)
def rating_level(score):
    if score >= q66:
        return "RATING: VERY HIGH!"
    elif score >= q33:
        return "RATING: GOOD"
    else:
        return "RATING: LOW"

LENGTH_OPTIONS = {
    "Up to 90 minutes": (0, 90),
    "Over 90 minutes": (91, 1000),
    "Any length is fine": None
}
GENRE_LIST = sorted(set(g for sublist in movies_df["genre_list"] for g in sublist if g != "adventure"))
SESSIONS = {}

MOOD_GENRE_MAP = {
    "sad": [("Comedy", "A comedy can bring some joy."),
            ("Fantasy", "Fantasy might help you escape for a while."),
            ("Animation", "Animation is often light and uplifting.")],
    "happy": [("Action", "Action fits your energetic vibe!"),
              ("Comedy", "Even more laughs for your good mood.")],
    "angry": [("Thriller", "A thriller can match your intense mood."),
              ("Action", "Channel that energy into an action-packed ride."),
              ("Crime", "Something gritty might hit the spot.")]
}

def is_english(text):
    return all(ord(c) < 128 for c in text)

def text_to_length(text):
    text = text.lower()
    if any(w in text for w in ["short", "quick", "under 90", "easy", "chill", "קצר", "קליל", "רגוע"]):
        return "Up to 90 minutes"
    if any(w in text for w in ["long", "epic", "over 90", "ארוך"]):
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
Analyze this user message even with grammar issues: "{text}"
Return JSON with:
- intent: greeting, movie_request, mood_description, unrelated
- mood: if relevant (like sad, happy, angry, bored), else null
- genre: if mentioned (like action, comedy), else null
- length: "Up to 90 minutes", "Over 90 minutes", "Any length is fine" or null
Format:
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

def format_cards(df, genre=None):
    return [{
        "title": row["title"],
        "year": int(row["release_year"]),
        "score": rating_level(row["final_score"]),
        "genre": genre.title() if genre else row["genre_list"][0].capitalize(),
        "duration": int(row["runtime"])
    } for _, row in df.iterrows()]

def recommend_movies(session):
    genre = session["genre"].lower()
    length_range = LENGTH_OPTIONS[session["length"]]
    filtered = movies_df[movies_df["genre_list"].apply(lambda g: genre in g)]
    if length_range:
        filtered = filtered[filtered["runtime"].between(*length_range)]
    if filtered.empty:
        return jsonify({"response": f"😕 No movies found for genre '{genre}' with that length."})
    session["results"] = filtered.sample(frac=1).reset_index(drop=True)
    session["pointer"] = 5
    response_text = f"🎬 Here are some *{session['genre']}* movies {session['length']}:"
    if session.get("mood_message"):
        response_text = f"{session['mood_message']}\n\n" + response_text
        session["mood_message"] = None
    return jsonify({
        "response": response_text,
        "cards": format_cards(session["results"].iloc[:5], session["genre"])
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
        guessed = text_to_length(user_msg)
        if guessed:
            session["length"] = guessed

    if analysis["intent"] == "unrelated":
        if session["genre"] and session["length"]:
            return recommend_movies(session)
        return jsonify({"response": "🤖 Tell me your mood or movie style!"})

    if analysis["intent"] == "greeting":
        return jsonify({"response": "👋 Hey there! What kind of movie are you in the mood for?"})

    # Always react to mood (even if genre already set)
    mood = analysis.get("mood")
    if mood:
        new_genre, mood_msg = mood_to_genre(mood)
        if new_genre:
            session["genre"] = new_genre
            session["mood_message"] = mood_msg
            session["results"] = None
            if not session.get("length"):
                return jsonify({
                    "response": mood_msg,
                    "followup": "[[ASK_LENGTH]]"
                })
            else:
                response = recommend_movies(session).get_json()
                response["response"] = f"{mood_msg}\n\n{response['response']}"
                return jsonify(response)

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
        "cards": format_cards(batch, session["genre"])
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
