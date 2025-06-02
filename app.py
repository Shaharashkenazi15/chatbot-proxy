from flask import Flask, request, jsonify
import openai
import os
import pandas as pd
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

openai.api_key = os.getenv("OPENAI_API_KEY")

# טען את קובץ הסרטים עם סינון לסרטים בלבד (ללא סדרות)
try:
    df = pd.read_csv("movies.csv")
    df = df[~df["Series_Title"].str.contains("TV|Series", case=False, na=False)]
except Exception as e:
    print("⚠️ שגיאה בטעינת קובץ הסרטים:", e)
    df = pd.DataFrame()

# מילות מפתח לזיהוי בקשה לסרט
movie_keywords = [
    "סרט", "המלצה", "קומדיה", "דרמה", "אקשן", "מותחן", "מפחיד", "מתח",
    "מרגש", "עצב", "שמח", "עצוב", "סיפור אמיתי", "מבוסס", "קליל",
    "טרגדיה", "מרומם", "בא לי", "תן לי משהו", "תרגש אותי", "סרט כבד"
]

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    message = data.get("message", "")
    print("📩 שאלה מהמשתמש:", message)

    # זיהוי אם מדובר בשאלה על סרט
    is_movie_question = any(word in message for word in movie_keywords)

    if is_movie_question:
        # סינון לפי ז'אנר או הקשר רגשי
        if any(word in message for word in ["דרמה", "מרגש", "כבד", "לבכות"]):
            filtered = df[df["Genre"].str.contains("Drama", case=False)]

        elif any(word in message for word in ["אקשן", "מתח", "מפחיד", "מותחן"]):
            filtered = df[df["Genre"].str.contains("Action|Thriller|Horror", case=False)]

        elif any(word in message for word in ["קומדיה", "צחוק", "קליל", "שמח", "אני עצוב", "באסה", "מעונן", "דיכאון"]):
            filtered = df[df["Genre"].str.contains("Comedy", case=False)]

        else:
            filtered = df.sort_values(by="Rating", ascending=False)

        user_prompt = (
            f"המשתמש כתב: {message}\n\n"
            f"הנה רשימת הסרטים מתוך הקובץ:\n\n{movie_list}\n\n"
            "אם זו בקשה לסרט – בחר סרט מתאים מהרשימה והמלץ עליו לפי ההנחיות."
        )
    else:
        user_prompt = (
            f"המשתמש כתב: {message}\n\n"
            "זו שאלה כללית. אנא ענה בצורה ידידותית, בלי להציע סרטים."
        )

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "אתה עוזר אישי חכם שממליץ על סרטים בלבד מתוך טבלת סרטים שנשלחת אליך. "
                        "אם המשתמש שואל על סרטים – ענה רק לפי הסרטים שמופיעים בטבלה. "
                        "אל תמציא שמות סרטים, תקצירים או פרטים שלא קיימים. "
                        "אם אין סרט מתאים – הסבר זאת בקצרה והצע סרט כללי מתוך הטבלה עם דירוג גבוה. "
                        "אם התקציר באנגלית – תרגם אותו לעברית. "
                        "שם הסרט תמיד יופיע באנגלית בלבד, בדיוק כפי שהוא מופיע בטבלה. "
                        "אל תתייחס לסדרות טלוויזיה. "
                        "אם השאלה כללית – כמו 'מה שלומך?' או 'תספר בדיחה' – תגיב בצורה נעימה וידידותית. "
                        "ענה תמיד בעברית, בצורה קצרה, קלילה וברורה, כאילו אתה חבר טוב שממליץ על סרט."
                    )
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ]
        )
        return jsonify({"response": response.choices[0].message.content})
    except Exception as e:
        print("⚠️ שגיאה בתקשורת עם OpenAI:", e)
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
