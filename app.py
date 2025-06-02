from flask import Flask, request, jsonify
import openai
import os
import pandas as pd
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

openai.api_key = os.getenv("OPENAI_API_KEY")

# טען את קובץ הסרטים עם טיפול בשגיאה
try:
    df = pd.read_csv("movies.csv")
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
      "אתה עוזר אישי חכם שיודע להמליץ על סרטים מתוך רשימת סרטים שמועברת אליך. "
      "אם השאלה קשורה לסרטים – ענה רק לפי הסרטים שבטבלה. "
      "אם השאלה כללית (כמו 'מה שלומך?' או 'תספר בדיחה'), אתה יכול לענות בצורה חופשית, ידידותית וקצרה. "
      "אם התקצירים באנגלית – תרגם אותם לעברית. "
      "ענה תמיד בעברית, בצורה קלילה, נעימה וממוקדת."
  )
}
,
                {
                    "role": "user",
                    "content": (
                        f"המשתמש ביקש: {message}\n\n"
                        f"הנה רשימת הסרטים:\n\n{movie_list}\n\n"
                        "בחר סרט אחד שמתאים לבקשה, והמלץ עליו בצורה קלילה וקצרה – כולל שם הסרט, שנה, ז'אנר, דירוג ותקציר בעברית."
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
