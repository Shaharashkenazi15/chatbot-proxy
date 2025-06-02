from flask import Flask, request, jsonify
import openai
import os
import pandas as pd
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# מפתח OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# טען את קובץ הסרטים וסנן סדרות
try:
    df = pd.read_csv("movies.csv")
    df = df[~df["Series_Title"].str.contains("TV|Series", case=False, na=False)]
except Exception as e:
    print("⚠️ שגיאה בטעינת movies.csv:", e)
    df = pd.DataFrame()

# רשימת ביטויים לשיחה כללית
general_phrases = ["שלום", "מה נשמע", "מה קורה", "מה שלומך", "היי", "אהלן", "הכל טוב", "הכול טוב"]

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_message = data.get("message", "").lower()

    # שלב 1: אם זו שאלה כללית – מחזירים תגובה ידידותית
    if any(phrase in user_message for phrase in general_phrases):
        return jsonify({
            "response": "היי! 😊 אני כאן כדי לעזור לך למצוא סרט טוב. תכתוב לי מה בא לך לראות 🎬"
        })

    # שלב 2: השתמש ב-GPT כדי לזהות ז'אנר רצוי
    try:
        genre_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "אתה מזהה כוונה של בקשות לסרטים. ענה תמיד במילה אחת שמתארת את סוג הסרט שהמשתמש מחפש. "
                        "לדוגמה: קומדיה, דרמה, פעולה, מתח, הרפתקאות, מרגש, קליל. "
                        "אם לא ברור, ענה 'כללי'. אל תענה משפטים שלמים."
                        "תענה תמיד בשם של הסרט בשפה האנגלית"
                        "תמיד תגיב בנחמדות"
                        "תמיד תענה תשובה שקשורה לשאלה של המשתמש"
                    )
                },
                {
                    "role": "user",
                    "content": user_message
                }
            ]
        )
        category = genre_response.choices[0].message.content.strip().lower()
    except Exception as e:
        print("⚠️ שגיאה עם GPT:", e)
        category = "כללי"

    # מיפוי מילות מפתח לעברית → אנגלית כפי שמופיע בז'אנר ב-CSV
    genre_map = {
        "קומדיה": "Comedy",
        "דרמה": "Drama",
        "אקשן": "Action",
        "מתח": "Thriller",
        "הרפתקאות": "Adventure",
        "מרגש": "Drama",
        "קליל": "Comedy",
        "מפחיד": "Horror",
        "כללי": ""
    }

    genre_to_search = genre_map.get(category, "")

    # שלב 3: חפש סרטים לפי הז'אנר
    if genre_to_search:
        filtered = df[df["Genre"].str.contains(genre_to_search, case=False, na=False)]
    else:
        filtered = df

    if filtered.empty:
        return jsonify({"response": "מצטער, לא מצאתי סרטים תואמים. נסה לנסח שוב 😊"})

    # שלב 4: בחר סרט אקראי
    selected = filtered.sample(n=1).iloc[0]

    # שלב 5: בנה תשובה בעברית
    reply = (
        f"🎬 ממליץ על הסרט **{selected['Series_Title']}** ({selected['Released_Year']})\n"
        f"ז'אנר: {selected['Genre']} | דירוג: {selected['Rating']}\n"
        f"{selected['Overview']}"
    )

    return jsonify({"response": reply})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
