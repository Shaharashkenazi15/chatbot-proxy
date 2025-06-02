from flask import Flask, request, jsonify
import openai
import os
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # מאפשר בקשות מהדפדפן

openai.api_key = os.getenv("OPENAI_API_KEY")  # ייקח את המפתח מהסביבה ב-Render

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    message = data.get("message", "")
    print("📩 הודעה שהתקבלה מהצ'אט:", message)

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": "אתה צ'אטבוט שמתמקד אך ורק בהמלצות על סרטים. "
                               "אתה לא עונה על שאלות כלליות, טכניות או אחרות. "
                               "אם שואלים אותך שאלה שאינה קשורה לעולם הסרטים, אתה תגיב בנימוס: "
                               "'אני מתמקד רק בהמלצות על סרטים 😊. אפשר לשאול על ז'אנר, מצב רוח או סרטים דומים למה שאהבת.' "
                               "בכל המלצה על סרט, כלול: שם הסרט, שנה, ז'אנר ותקציר קצר."
                },
                {
                    "role": "user",
                    "content": message
                }
            ]
        )
        return jsonify({"response": response.choices[0].message.content})
    except Exception as e:
        print("⚠️ שגיאה בשרת:", e)
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
