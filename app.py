from flask import Flask, request, jsonify
import openai
import os
import pandas as pd
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

openai.api_key = os.getenv("OPENAI_API_KEY")

# טען את קובץ הסרטים (למעט סדרות)
try:
    df = pd.read_csv("movies.csv")
    df = df[~df["Series_Title"].str.contains("TV|Series", case=False, na=False)]
except Exception as e:
    print("⚠️ שגיאה בטעינת movies.csv:", e)
    df = pd.DataFrame()

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    message = data.get("message", "")

    # בחר 50 סרטים לדוגמה
    examples = df[['Series_Title', 'Released_Year', 'Genre', 'Rating', 'Overview']].sample(n=50).to_string(index=False)

    prompt = (
        f"המשתמש כתב: {message}\n\n"
        f"הנה רשימת סרטים לדוגמה מתוך מאגר הסרטים שלנו:\n\n{examples}\n\n"
        "בחר סרט אחד שמתאים לבקשה והמלץ עליו בעברית – כולל שם הסרט באנגלית, שנה, ז'אנר, דירוג ותקציר. "
        "אל תמציא סרטים שלא נמצאים ברשימה."
    )

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
"content": (
    "אתה ממליץ על סרטים רק מתוך רשימת הסרטים שנשלחת אליך. "
    "ענה תמיד בעברית בלבד. "
    "אל תמציא סרטים, שמות, תקצירים או מידע שלא מופיע ברשימה. "
    "אם הבקשה אינה קשורה לסרטים – תגיב באופן ידידותי בלבד, בלי להמליץ על סרט."
)

                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
        return jsonify({"response": response.choices[0].message.content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
