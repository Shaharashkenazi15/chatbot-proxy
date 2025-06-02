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

# ביטויים של שיחה כללית
general_phrases = ["שלום", "מה נשמע", "מה קורה", "מה שלומך", "היי", "אהלן"]

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    messages = data.get("messages", [])
    user_message = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")

    # תגובה לשאלה כללית – ללא שימוש במודל
    if any(p in user_message.lower() for p in general_phrases):
        return jsonify({"response": "היי! 😊 אני כאן כדי להמליץ לך על סרטים טובים. ספר לי מה בא לך לראות 🎬"})

    # בחר עד 50 סרטים עם דירוג גבוה
    top_movies = df.sort_values(by="Rating", ascending=False).head(50)

    # בנה רשימת סרטים לשליחה ל-GPT
    movie_list = top_movies[['Series_Title', 'Released_Year', 'Genre', 'Rating', 'Overview']].to_string(index=False)

    prompt = (
        f"המשתמש כתב: {user_message}\n\n"
        f"הנה רשימת הסרטים:\n\n{movie_list}\n\n"
        "בחר סרט אחד בלבד שמתאים לבקשה. ענה בעברית. "
        "הצג את שם הסרט באנגלית בלבד, ואז תכתוב את השנה, הז'אנר, הדירוג והתקציר בעברית. "
        "אם אין התאמה ברורה – תמליץ על סרט כללי מהרשימה. אל תמציא סרטים חדשים או מידע לא קיים."
    )

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "ענה רק לפי הסרטים שקיבלת. אל תמציא. ענה תמיד בעברית."},
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
