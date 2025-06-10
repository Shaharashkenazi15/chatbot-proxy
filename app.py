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

# Extract genre options
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

sessions = {}

def is_english(text):
    return bool(re.match(r'^[\x00-\x7F\s.,!?\'"-]+$', text))

def is_movie_related(user_input):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            temperature=0,
            messages=[
                {"role": "system", "content": "Classify if a message is related to movies or recommendations."},
                {"role": "user", "content": f"Is this message about movies?\n'{user_input}'\nAnswer 'yes' or 'no'."}
            ]
        )
        return "yes" in response.choices[0].message.content.lower()
    except:
        return False

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    messages = data.get("messages", [])
    user_message = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    session_id = data.get("session_id", "default")

    # Handle greetings like "hi"
    greetings = ["hi", "hello", "hey", "what's up", "how are you", "yo", "good morning", "good evening"]
    if user_message.lower().strip() in greetings:
        return jsonify({"response": "👋 Hey there! Looking for a movie recommendation today?"})

    if not is_english(user_message):
        return jsonify({"response": "❌ English only please."})

    if not is_movie_related(user_message):
        return jsonify({"response": "🤖 I'm here to help with movie recommendations. Please tell me what genre or type you're looking for!"})

    if session_id not in sessions:
        sessions[session_id] = {"genre": None, "length": None, "adult": None}
    session = sessions[session_id]

    # Try to extract genre
    if not session["genre"]:
        for genre in GENRE_OPTIONS:
            if genre.lower() in user_message.lower():
                session["genre"] = genre
                break

    # Try to extract length
    if not session["length"]:
        if "short" in user_message.lower():
            session["length"] = "short"
        elif "medium" in user_message.lower():
            session["length"] = "medium"
        elif "long" in user_message.lower():
            session["length"] = "long"

    # Try to extract audience
    if session["adult"] is None:
        if "adult" in user_message.lower():
            session["adult"] = True
        elif "everyone" in user_message.lower() or "family" in user_message.lower():
            session["adult"] = False

    # Ask for missing info
    if not session["genre"]:
        return jsonify({"response": "[[ASK_GENRE]]"})
    if not session["length"]:
        return jsonify({"response": "[[ASK_LENGTH]]"})
    if session["adult"] is None:
        return jsonify({"response": "[[ASK_ADULT]]"})

    # All info present – filter movies
    genre_filter = session["genre"].lower()
    min_len, max_len = LENGTH_OPTIONS[session["length"]]
    is_adult = session["adult"]

    filtered = df[
        df["genres"].str.lower().str.contains(genre_filter) &
        df["runtime"].between(min_len, max_len) &
        (df["adult"] == is_adult)
    ]

    if filtered.empty:
        return jsonify({"response": "😕 No movies found for your selection. Try a different combination."})

    top_movies = filtered.sort_values("final_score", ascending=False).head(5)
    results = []
    for _, row in top_movies.iterrows():
        results.append(
            f"🎬 {row['title']} ({int(row['release_year'])})\n"
            f"Genre: {row['genres']}\n"
            f"Duration: {int(row['runtime'])} min\n"
            f"Score: {round(row['final_score'], 2)}\n"
            f"Overview: {row['overview']}"
        )

    return jsonify({"response": "\n\n".join(results)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
