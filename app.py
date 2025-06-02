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

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    message = data.get("message", "")
    print("📩 שאלה מהמשתמש:", message)

    # סינון לפי ז'אנר – מילים נפוצות
    if "דרמה" in message:
        filtered = df[df["Genre"].str.contains("Drama", case=False)]
    elif "אקשן" in message:
        filtered = df[df["Genre"].str.contains("Action", case=False)]
    elif "קומדיה" in message:
        filtered = df[df["Genre"].str.contains("Comedy", case=False)]
    else:
        filtered = df.sort_values(by="Rating", ascending=False)

    # קח עד 5 סרטים רלוונטיים
    top = filtered.head(5)

    # רשימת סרטים בפורמט טקסט
    movie_list = top[['Series_Title', 'Released_Year', 'Genre', 'Rating', 'Overview']].to_string(index=False)

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
                    "content": (
                        f"המשתמש כתב: {message}\n\n"
                        f"הנה רשימת הסרטים מתוך הקובץ:\n\n{movie_list}\n\n"
                        "אם זו בקשה לסרט – בחר סרט מתאים מהרשימה והמלץ עליו לפי ההנחיות. "
                        " אם זו שאלה כללית – תענה בהתאם.,ובידידות - והסבר שאתה יועץ סרטים"
                    )
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
