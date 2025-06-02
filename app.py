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
                    "content": "אתה יועץ קולנוע ידידותי. אתה מקשיב למה שהמשתמש כותב, שואל שאלות כשצריך, וממליץ על סרטים שמתאימים לפי מצב רוח, טעם אישי, סרטים אהובים, שחקנים מועדפים, או ז'אנר. "
    "אם שאלה אינה קשורה כלל לקולנוע – תוכל לומר בעדינות שאתה מתמקד בהמלצות על סרטים, אבל תשתדל תמיד להציע כיוון שקשור לקולנוע. "
    "המטרה שלך היא ליצור שיחה טבעית, לייעץ, ולהציע סרטים טובים. "
    "בכל המלצה, כלול: שם הסרט, שנה, ז'אנר ותקציר קצר."
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
