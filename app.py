from flask import Flask, request, jsonify
import openai
import os
import pandas as pd
import random
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

# ביטויי שיחה כללית
general_phrases = ["שלום", "מה נשמע", "מה קורה", "מה שלומך", "היי", "אהלן"]

# זיהוי מצב רוח פשוט
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

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    messages = data.get("messages", [])
    user_message = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")

    # תגובה לשיחה כללית
    if any(p in user_message.lower() for p in general_phrases):
        return jsonify({"response": "שלום! אני יכול להמליץ לך על סרטים לפי מצב רוח או סגנון. ספר לי איך אתה מרגיש או מה מתחשק לך לראות."})

    # זיהוי מצב רוח
    mood = detect_mood(user_message)

    # שלוף 30-50 סרטים אקראיים
    sample_size = min(50, len(df))
    selected_movies = df.sample(n=sample_size)

    movie_list = selected_movies[['Series_Title', 'Released_Year', 'Genre', 'Rating', 'Overview']].to_string(index=False)

    prompt = (
        f"המשתמש כתב: {user_message} (מצב רוח: {mood})\n\n"
        f"הנה רשימת הסרטים:\n\n{movie_list}\n\n"
        "בחר סרט אחד בלבד שמתאים לבקשה או למצב הרוח. ענה בעברית בלבד. "
        "הצג את שם הסרט באנגלית, ואז את שנת היציאה, הז'אנר, הדירוג והתקציר – כולם בעברית. "
        "בחר רק מתוך הרשימה. אל תמציא סרטים חדשים או מידע נוסף."
    )

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "ענה בעברית בלבד. בחר סרט רק מתוך הרשימה. אל תמציא מידע."},
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
