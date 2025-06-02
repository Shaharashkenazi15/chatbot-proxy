from flask import Flask, request, jsonify
import openai
import os
import pandas as pd
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

openai.api_key = os.getenv("OPENAI_API_KEY")

# טען את קובץ הסרטים
df = pd.read_csv("movies.csv")

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    message = data.get("message", "")
    print("📩 שאלה מהמשתמש:", message)

    # סינון בסיסי לפי ז'אנר – לפי מילים נפוצות בהודעה
    if "דרמה" in message:
        filtered = df[df["Genre"].str.contains("Drama", case=False)]
    elif "אקשן" in message or "אקשן" in message:
        filtered = df[df["Genre"].str.contains("Action", case=False)]
    elif "קומדיה" in message:
        filtered = df[df["Genre"].str.contains("Comedy", case=False)]
    else:
        filtered = df.sort_values(by="Rating", ascending=False)

    # קח עד 5 סרטים רלוונטיים
    top = filtered.head(5)

    # בנה רשימת סרטים לשליחה ל-GPT
    movie_list = top[['Series_Title', 'Released_Year', 'Genre', 'Rating', 'Overview']].to_string(index=False)
    prompt = (
        f"המשתמש ביקש המלצה על סרט. הנה מידע מתוך מאגר הסרטים שלנו:\n\n"
        f"{movie_list}\n\n"
        "בחר סרט אחד שמתאים לבקשה, והמלץ עליו בצורה מעניינת. כלול את שם הסרט, שנה, ז'אנר, דירוג ותקציר. אל תמציא מידע חדש."
    )

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": "ענה אך ורק על סמך הסרטים שנשלחו אליך. אל תמציא שמות או מידע שלא מופיע בטבלה."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
        return jsonify({"response": response.choices[0].message.content})
    except Exception as e:
        print("⚠️ שגיאה:", e)
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
