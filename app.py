from flask import Flask, request, jsonify
import pandas as pd
import openai
import os
import random
import re
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

openai.api_key = os.getenv("OPENAI_API_KEY")
df = pd.read_csv("movies.csv")

user_state = {}

def is_relevant_via_gpt(message: str):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            temperature=0,
            messages=[
                {"role": "system", "content": "You determine if a message is relevant to movie recommendation, including if it contains mood, situation or genre."},
                {"role": "user", "content": f'Does the user seem to want a movie recommendation, or is the message about mood, situation or preference that can guide a movie suggestion?\nAnswer "yes" or "no".\n"{message}"'}
            ]
        )
        reply = response.choices[0].message.content.strip().lower()
        return reply.startswith("yes")
    except:
        return False

def contains_non_english(text):
    return bool(re.search(r'[א-ת]|[^\x00-\x7F]', text))

def reset_user(session_id):
    user_state[session_id] = {"mood": None, "length": None, "genre": None}

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    messages = data.get("messages", [])
    user_message = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "").strip()

    session_id = request.remote_addr or str(random.randint(1000, 9999))
    if session_id not in user_state:
        reset_user(session_id)

    # Reject non-English input
    if contains_non_english(user_message):
        return jsonify({"response": "❌ This assistant only supports English. Please write in English only."})

    # Reject messages with just numbers or symbols
    if not re.search(r'[a-zA-Z]', user_message):
        return jsonify({"response": "❌ Please write a meaningful message in English."})

    if not is_relevant_via_gpt(user_message):
        return jsonify({"response": "🎬 I can only help with movie recommendations. Please tell me what kind of movie you're looking for."})

    state = user_state[session_id]

    # Try to extract mood or genre or length
    if state["mood"] is None:
        if any(w in user_message.lower() for w in ["sad", "down", "depressed"]):
            state["mood"] = "uplifting"
        elif any(w in user_message.lower() for w in ["happy", "excited", "fun"]):
            state["mood"] = "fun"
        elif any(w in user_message.lower() for w in ["angry", "frustrated"]):
            state["mood"] = "calming"
        elif any(w in user_message.lower() for w in ["anxious", "stressed"]):
            state["mood"] = "relaxing"

    if state["length"] is None:
        if "short" in user_message.lower():
            state["length"] = "short"
        elif "medium" in user_message.lower():
            state["length"] = "medium"
        elif "long" in user_message.lower():
            state["length"] = "long"

    if state["genre"] is None:
        genres = ["comedy", "drama", "action", "romance", "thriller", "horror", "adventure"]
        for genre in genres:
            if genre in user_message.lower():
                state["genre"] = genre
                break

    # If still missing info, ask for it
    if not state["genre"]:
        return jsonify({"response": "🎬 What genre are you in the mood for? (e.g. comedy, action, drama...)"})
    if not state["length"]:
        return jsonify({"response": "⏱️ What movie length do you prefer?\n- Short (up to 90 min)\n- Medium (up to 120 min)\n- Long (over 120 min)"})

    # Match length to minutes
    if state["length"] == "short":
        length_range = (0, 90)
    elif state["length"] == "medium":
        length_range = (90, 120)
    else:
        length_range = (120, 500)

    cluster_df = df[
        (df["genres"].str.lower().str.contains(state["genre"])) &
        (df["runtime_minutes"].between(length_range[0], length_range[1]))
    ]

    if cluster_df.empty:
        return jsonify({"response": "😕 Sorry, I couldn't find matching movies. Try a different genre or length."})

    sample = cluster_df.sort_values(by="final_score", ascending=False).head(25)

    prompt = (
        f"You are a helpful movie assistant. The user is in the mood: {state['mood'] or 'unknown'}, "
        f"and prefers genre: {state['genre']}, and length: {state['length']}.\n"
        "Here are 25 movie options from the dataset. Pick 1-3 movies that best match the user's needs.\n"
        "Only choose from the list. Don't invent. Respond in clear, warm English.\n\n"
        "Format for each movie:\n"
        "<Title>\n<Release Year>\n<Genre>\n<Overview>\n<Main Actor>\n<Runtime in minutes>\n"
        "<Explain briefly why this movie suits the user>\n\n"
        "Separate each movie block with an empty line.\n\n"
        "Movies:\n" +
        sample[["title", "release_year", "genres", "overview", "main_actor", "runtime_minutes"]]
        .to_string(index=False)
    )

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            temperature=0.7,
            messages=[
                {"role": "system", "content": "You are a movie assistant. Recommend movies based only on the provided data. Never make up any movie."},
                {"role": "user", "content": prompt}
            ]
        )
        reply = response.choices[0].message.content.strip()
        return jsonify({"response": reply})
    except Exception as e:
        return jsonify({"response": f"⚠️ Error processing request: {str(e)}"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
