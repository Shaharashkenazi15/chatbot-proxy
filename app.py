from flask import Flask, request, jsonify
import pandas as pd
import openai
import os

app = Flask(__name__)

openai.api_key = os.getenv("OPENAI_API_KEY")

movies_df = pd.read_csv("movies.csv")

SYSTEM_PROMPT = """
אתה עוזר אישי שממליץ על סרטים מתוך רשימת סרטים שהוזנה. אם זו שאלה כללית, ענה בצורה ידידותית.
אם זו בקשה לסרט, על סמך מצב רוח או תיאור של המשתמש, בחר סרט אחד מתוך הרשימה לפי ההתאמה הטובה ביותר.
כתוב את המלצתך בעברית, וכתוב את שם הסרט באנגלית בדיוק כפי שהוא מופיע ברשימה.
הנה רשימת הסרטים (כותרות: Series_Title, Released_Year, Runtime, Genre, Rating, Overview, Director):
"""

def get_movies_list_text():
    lines = []
    for idx, row in movies_df.iterrows():
        # נשלח שורה קצרה עם שם, שנה, ז'אנר ותיאור
        lines.append(
            f"{row['Series_Title']} ({row['Released_Year']}), ז'אנר: {row['Genre']}, תקציר: {row['Overview'][:100]}..."
        )
    return "\n".join(lines)

@app.route("/recommend", methods=["POST"])
def recommend():
    data = request.get_json()
    if not data or "mood" not in data:
        return jsonify({"error": "Missing 'mood' parameter in JSON body"}), 400
    
    mood = data["mood"].strip()
    if mood == "":
        return jsonify({"error": "Empty 'mood' parameter"}), 400

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT + get_movies_list_text()},
        {"role": "user", "content": mood},
    ]

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=300,
        )
        answer = response.choices[0].message.content.strip()
        return jsonify({"recommendation": answer})
    except Exception as e:
        return jsonify({"error": f"Error from OpenAI API: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(debug=True)
