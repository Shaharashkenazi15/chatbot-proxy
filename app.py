from flask import Flask, request, jsonify
import openai
import os
import pandas as pd
import random
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

    # שלב 1: בקש מ-GPT לסווג את השאלה
    try:
        gpt_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "אתה מסווג בקשות לסרטים. "
                        "ענה רק בז'אנר אחד או מילת מפתח שמתארת את סוג הסרט שהמשתמש רוצה "
                        "(למשל: קומדיה, דרמה, אקשן, מרגש, מותחן, קליל, מפחיד). "
                        "אל תמליץ על סרט, אל תסביר, רק כתוב את הסיווג."
                    )
                },
                {
                    "role": "user",
                    "content": user_message
                }
            ]
        )
        category = gpt_response.choices[0].message.content.strip()
        print("🎯 קטגוריה ש-GPT זיהה:", category)
    except Exception as e:
        print("⚠️ שגיאה בתקשורת עם OpenAI:", e)
        return jsonify({"error": "שגיאה בזיהוי הבקשה"}), 500

    # שלב 2: חפש סרט מתאים בקובץ
    filtered = df[df["Genre"].str.contains(category, case=False, na=False)]

    if filtered.empty:
        selected = df.sample(n=1).iloc[0]
        note = f"לא נמצאו סרטים בז'אנר '{category}', מוצג סרט אקראי אחר:\n"
    else:
        selected = filtered.sample(n=1).iloc[0]
        note = ""

    # שלב 3: בנה תגובה
    final_text = (
        f"{note}"
        f"🎬 ממליץ על הסרט: **{selected['Series_Title']}** ({selected['Released_Year']})\n"
        f"ז'אנר: {selected['Genre']} | דירוג: {selected['Rating']}\n"
        f"{selected['Overview']}"
    )

    return jsonify({"response": final_text})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
