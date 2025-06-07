from flask import Flask, request, jsonify
import openai
import os
import pandas as pd
import random
import re
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

openai.api_key = os.getenv("OPENAI_API_KEY")

# טען את קובץ הסרטים וסנן סדרות
try:
    df = pd.read_csv("movies.csv")
    df = df[~df["Series_Title"].str.contains("TV|Series", case=False, na=False)]
except Exception as e:
    print("⚠️ שגיאה בטעינת movies.csv:", e)
    df = pd.DataFrame()

# ביטויי פתיחה כלליים
general_phrases = ["שלום", "מה נשמע", "מה קורה", "מה שלומך", "היי", "אהלן"]

# זיהוי מצב רוח
def detect_mood(message):
    message = message.lower()
    if any(word in message for word in ["עצוב", "בדיכאון", "בוכה"]):
        return "עצוב"
    if any(word in message for word in ["כועס", "עצבני", "מתוסכל"]):
        return "כועס"
    if any(word in message for word in ["שמח", "מאושר", "טוב לי"]):
        return "שמח"
    if any(word in message for word in ["לחוץ", "חרד", "עומס"]):
        return "לחוץ"
    return "רגיל"

# ניתוח כמה סרטים המשתמש רוצה
def extract_number_of_movies(message):
    match = re.search(r'(\d+)\s*סרט', message)
    if match:
        return min(int(match.group(1)), 5)  # מגביל עד 5 מקסימום
    return 1

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    messages = data.get("messages", [])
    user_message = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")

    # תגובה לשיחה כללית
    if any(p in user_message.lower() for p in general_phrases):
        return jsonify({"response": "שלום! אני אשמח להמליץ לך על סרטים. תרגיש חופשי לכתוב איך אתה מרגיש או כמה סרטים בא לך לראות."})

    # ניתוח מצב רוח וכמות סרטים
    mood = detect_mood(user_message)
    num_movies = extract_number_of_movies(user_message)

    # שלוף סרטים רנדומליים מתוך הדאטה
    sample_size = min(60, len(df))
    selected_movies = df.sample(n=sample_size)

    # קובץ טקסט לסרטים (נשלח ל-GPT)
    movie_list = selected_movies[['Series_Title', 'Released_Year', 'Genre', 'Rating', 'Overview']].to_string(index=False)

    # יצירת הפרומפט
    prompt = (
        f"המשתמש כתב: {user_message} (מצב רוח: {mood})\n\n"
        f"הנה רשימת הסרטים:\n\n{movie_list}\n\n"
        f"בחר {num_movies} סרטים מתוך הרשימה שמתאימים לבקשה ולמצב הרוח של המשתמש. "
        f"ענה בעברית בלבד, בצורה חמה וחברית. "
        f"עבור כל סרט, הצג את השם באנגלית, ואז את שנת היציאה, הז'אנר, הדירוג והתקציר – בעברית. "
        f"כתוב גם משפט קצר שמסביר למה המלצת דווקא עליו בהתאם למצב הרוח או הסגנון שהמשתמש ביקש. "
        f"אל תמציא סרטים או מידע שלא קיים בקובץ. בחר רק מהרשימה."
    )

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "ענה בעברית בלבד, בסגנון חמים ואישי. בחר סרטים רק מהרשימה. אל תמציא."},
                {"role": "user", "content": prompt}
            ]
        )
        return jsonify({"response": response.choices[0].message.content})
    except Exception as e:
        print("⚠️ שגיאה:", e)
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
