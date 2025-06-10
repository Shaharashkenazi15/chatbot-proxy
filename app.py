from flask import Flask, request, jsonify
import pandas as pd
import openai
import os
import random
import json
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

df = pd.read_csv("movies.csv")
openai.api_key = os.getenv("OPENAI_API_KEY")

user_state = {}

def is_relevant_via_gpt(message: str):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            temperature=0,
            messages=[
                {"role": "system", "content": "You determine if a message is related to movies or watching movies."},
                {"role": "user", "content": f'Does this message imply the user wants to watch or get a movie recommendation?\nAnswer "yes" or "no".\n"{message}"'}
            ]
        )
        reply = response.choices[0].message.content.strip().lower()
        return reply.startswith("yes")
    except:
        return True

def get_mood_and_context_via_gpt(message: str):
    prompt = f"""
Analyze the sentence: "{message}"

If the user mentioned a genre (e.g., comedy, action...), return:
{{"mood": "genre-based", "context": "genre-based"}}
Else, classify:
- mood: normal / happy / sad / angry / tired
- context: alone / with friends / couple / family

Return as JSON only.
"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            temperature=0,
            messages=[
                {"role": "system", "content": "You analyze mood and social context for movie watching."},
                {"role": "user", "content": prompt}
            ]
        )
        reply = response.choices[0].message.content.strip()
        mood_context = json.loads(reply)
        return mood_context.get("mood", "normal"), mood_context.get("context", "alone")
    except:
        return "normal", "alone"

def map_context_to_cluster(mood, context):
    if mood == "genre-based" or context == "genre-based":
        return None
    if mood == "happy" and context == "with friends":
        return 1
    elif mood == "sad" and context == "alone":
        return 3
    elif mood == "tired":
        return 2
    elif context == "family":
        return 2
    elif context == "with friends":
        return 1
    elif context == "couple":
        return 3
    return random.choice(df["cluster_id"].unique())

def get_movies_from_cluster(cluster_id):
    cluster_df = df[df["cluster_id"] == cluster_id]
    return cluster_df.sample(n=min(25, len(cluster_df)), random_state=42).sort_values("final_score", ascending=False)

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    messages = data.get("messages", [])
    user_message = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "").strip()
    session_id = request.remote_addr

    if len(messages) == 1:
        user_state[session_id] = {}

    state = user_state.get(session_id, {})

    if not is_relevant_via_gpt(user_message):
        return jsonify({"response": "I'm here to help with movie recommendations only 🎬 What kind of movie are you looking for?"})

    if "mood" not in state or "context" not in state:
        mood, context = get_mood_and_context_via_gpt(user_message)
        state["mood"] = mood
        state["context"] = context
        user_state[session_id] = state

    if "length" not in state:
        if any(word in user_message.lower() for word in ["short", "medium", "long"]):
            if "short" in user_message.lower():
                state["length"] = "short"
            elif "medium" in user_message.lower():
                state["length"] = "medium"
            elif "long" in user_message.lower():
                state["length"] = "long"
            user_state[session_id] = state
        else:
            return jsonify({"response": "Do you prefer a short, medium, or long movie?"})

    cluster_id = map_context_to_cluster(state["mood"], state["context"])
    if cluster_id is None:
        return jsonify({"response": "Could you tell me which genre you're in the mood for?"})

    movies_df = get_movies_from_cluster(cluster_id)
    movie_blocks = ""
    for _, row in movies_df.iterrows():
        movie_blocks += (
            f"{row['title']}\n"
            f"Year: {row['release_year']}\n"
            f"Genre: {row['genres']}\n"
            f"Overview: {row['overview']}\n"
            f"Length: {int(row['runtime'])} minutes\n\n"
        )

    prompt = (
        f"User message: {user_message}\n"
        f"Mood: {state['mood']}, Context: {state['context']}, Length: {state['length']}\n\n"
        f"Here are 25 movies:\n\n{movie_blocks}\n\n"
        f"Pick 3 movies only. Use this format:\n"
        f"<Movie Title>\n<Year>\n<Genre>\n<Overview>\n<Length in minutes>\nExplain in English why you chose this movie\n\n"
        f"Separate each movie with a blank line. Don't invent movies."
    )

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            temperature=0.5,
            messages=[
                {"role": "system", "content": "Respond ONLY based on the given data. Use the exact format. Do not make up content."},
                {"role": "user", "content": prompt}
            ]
        )
        answer = response.choices[0].message.content
        return jsonify({"response": answer})
    except Exception as e:
        print("Error:", e)
        return jsonify({"response": "An error occurred. Please try again later."}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
