from flask import Flask, request, jsonify
import openai
import os
import pandas as pd
import json
import random
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

openai.api_key = os.getenv("OPENAI_API_KEY")

# טען את קובץ הסרטים
try:
    df = pd.read_csv("/mnt/data/movies.csv")
    df = df[~df["Series_Title"].str.contains("TV|Series", case=False, na=False)]
except Exception as e:
    print("⚠️ שגיאה בטעינת movies.csv:", e)
    df = pd.DataFrame()

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    messages = data.get("messages", [])
    user_message = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")

    # שלב 1: ניתוח מצב רוח / העדפה
    mood_prompt = (
        f"המשתמש כתב: {user_message}\n"
        "סכם את מצב הרוח או ההעדפה שלו לצפייה בסרט.\n"
        "ענה במבנה JSON תקני כמו:\n"
        '{ "mood": "עצוב", "desired_genres": ["Comedy", "Romance"], "keywords": ["love", "funny"] }\n'
        "אם אי אפשר להבין – החזר mood 'רגיל' ורשום genre כלליים."
    )

    try:
        mood_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "אתה מנתח כוונות וציפיות מסרטים. ענה כ-JSON בלבד."},
                {"role": "user", "content": mood_prompt}
            ]
        )
        filters = json.loads(mood_response.choices[0].message.content)
    except Exception as e:
        print("⚠️ שגיאה בניתוח JSON:", e)
        filters = {"mood": "רגיל", "desired_genres": [], "keywords": []}

    # שלב 2: סינון וסידור הסרטים
    filtered_df = df.copy()

    if filters.get("desired_genres"):
        filtered_df = filtered_df[
            filtered_df["Genre"].str.contains('|'.join(filters["desired_genres"]), case=False, na=False)
        ]

    if filters.get("keywords"):
        for kw in filters["keywords"]:
            filtered_df = filtered_df[filtered_df["Overview"].str.contains(kw, case=False, na=False)]

    # אם אין תוצאה – חזור לקובץ המלא
    if filtered_df.empty:
        filtered_df = df.copy()

    # שלב 3: בחר רנדומלית 10 סרטים שונים
    sample_movies = filtered_df.sample(n=min(10, len(filtered_df)))

    movie_list = ""
    for _, row in sample_movies.iterrows():
        movie_list += (
            f"Title: {row['Series_Title']}\n"
            f"Year: {row['Released_Year']}\n"
            f"Overview: {row['Overview']}\n\n"
        )

    # שלב 4: שלח ל־GPT לבחור סרט אחד בלבד
    final_prompt = (
        f"המשתמש כתב: {user_message}\n"
        f"הנה סרטים לבחירה:\n\n{movie_list}\n"
        "בחר סרט אחד בלבד שמתאים לבקשה או למצב הרוח. ענה בעברית בלבד. אל תמציא סרטים.\n"
        "הצג את שם הסרט באנגלית, השנה, והתקציר בעברית בלבד."
    )

    try:
        final_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "ענה רק לפי הסרטים שנשלחו. אל תמציא. ענה בעברית בלבד."},
                {"role": "user", "content": final_prompt}
            ]
        )
        return jsonify({"response": final_response.choices[0].message.content})
    except Exception as e:
        print("⚠️ שגיאה:", e)
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
