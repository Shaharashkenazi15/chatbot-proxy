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
    user_message = data.get("message", "")

    # בחר 50 סרטים אקראיים מהטבלה
    sample_df = df.sample(n=50) if not df.empty else pd.DataFrame()
    movie_list = sample_df[['Series_Title', 'Released_Year', 'Genre', 'Rating', 'Overview']].to_string(index=False)

    # בנה את ה-prompt
    prompt = (
    f"הודעת המשתמש:\n{user_message}\n\n"
    "אם זו שאלה כללית – הגיב בצורה ידידותית בלבד, בלי לבחור סרט."
    "שים לב: ייתכן שזו שאלה כללית ולא בקשה לסרט.\n"
    "אם זו בקשה להמלצה, השתמש ברשימת הסרטים הבאה בלבד לבחירת סרט מתאים:\n\n"
    f"{movie_list}\n\n"
    "אל תמציא סרטים. אל תענה באנגלית. אל תתייחס לשמות שלא נמצאים ברשימה.\n"
            )


    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "אתה עוזר אישי חכם שממליץ על סרטים מתוך רשימה שנשלחת אליך. "
                        "אם זו שאלה כללית – תגיב בנימוס ובחברותיות בלבד. "
                        "אם זו בקשת המלצה – בחר סרט מתוך הרשימה בלבד. "
                        "ענה תמיד בעברית. אל תמציא שמות סרטים."
                        "תמיד תרשום את שם הסרט בשפה האנגלית"
                        "אם שואלים אותך על שחקנים של סהרט תציין לפי הרשימה או הטבלה"
                        "אם שואלים אותך אותה שאלה פעם נוספת , תגיב בהתאם "
                    
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
