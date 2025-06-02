from flask import Flask, request, jsonify
import openai
import os
import pandas as pd
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

openai.api_key = os.getenv("OPENAI_API_KEY")

# טען את קובץ הסרטים תוך סינון סדרות
try:
    df = pd.read_csv("movies.csv")
    df = df[~df["Series_Title"].str.contains("TV|Series", case=False, na=False)]
except Exception as e:
    print("⚠️ שגיאה בטעינת קובץ הסרטים:", e)
    df = pd.DataFrame()

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_message = data.get("message", "")

    # שלח ל-GPT כדי להבין איזה ז'אנר המשתמש רוצה
    try:
        gpt_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "אתה מסווג בקשות לסרטים. "
                        "בהתאם להודעת המשתמש, ענה רק בז'אנר אחד או מילת מפתח שמתארת את סוג הסרט שהוא מחפש – "
                        "כמו קומדיה, דרמה, פעולה, מתח, מרגש, קליל, מפחיד. "
                        "ענה במילה אחת בלבד, בלי משפטים, בלי הסברים. "
                        "אם לא ברור – החזר את המילה 'כללי'."
                    )
                },
                {
                    "role": "user",
                    "content": user_message
                }
            ]
        )
        category = gpt_response.choices[0].message.content.strip()
        print("🎯 GPT סיווג את הבקשה כ:", category)
    except Exception as e:
        print("⚠️ שגיאה בתקשורת עם OpenAI:", e)
        return jsonify({"error": "שגיאה בסיווג הבקשה"}), 500

    # סנן את הדאטה לפי הקטגוריה ש-GPT זיהה
    filtered = df[df["Genre"].str.contains(category, case=False, na=False)]

    if filtered.empty:
        selected = df.sample(n=1).iloc[0]
        note = f"לא נמצאו סרטים בז'אנר '{category}', מוצג סרט אקראי אחר:\n"
    else:
        selected = filtered.sample(n=1).iloc[0]
        note = ""

    # בנה את ההמלצה
    response_text = (
        f"{note}"
        f"🎬 ממליץ לך על הסרט **{selected['Series_Title']}** ({selected['Released_Year']})\n"
        f"ז'אנר: {selected['Genre']} | דירוג: {selected['Rating']}\n"
        f"{selected['Overview']}"
    )

    return jsonify({"response": response_text})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
