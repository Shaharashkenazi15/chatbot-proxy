from flask import Flask, request, jsonify
import openai
import os
import pandas as pd
import re
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

openai.api_key = os.getenv("OPENAI_API_KEY")

# טען את קובץ הסרטים וסנן סדרות
try:
    df = pd.read_csv("movies.csv")
    df = df[~df["Series_Title"].str.contains("TV|Series", case=False, na=False)]
except Exception as e:
    print("⚠️ שגיאה בטעינת movies.csv:", e)
    df = pd.DataFrame()

def extract_number_of_movies(message):
    match = re.search(r'(\d+)', message)
    if match:
        return min(int(match.group(1)), 5)
    return 1

SYSTEM_PROMPT = """
אתה עוזר אישי שממליץ על סרטים מתוך רשימת סרטים שהוזנה.
אם זו בקשה לסרט, על סמך מצב רוח או תיאור של המשתמש, בחר סרט אחד או יותר מתוך הרשימה לפי ההתאמה הטובה ביותר.
כתוב את המלצתך בעברית, וכתוב את שם הסרט באנגלית בדיוק כפי שהוא מופיע ברשימה.
הנה רשימת הסרטים (כותרות: Series_Title, Released_Year, Runtime, Genre, Rating, Overview, Director):
"""

def get_movies_list_text():
    lines = []
    for idx, row in df.iterrows():
        # נשלח שורה קצרה עם שם, שנה, ז'אנר ותיאור
        lines.append(
            f"{row['Series_Title']} ({row['Released_Year']}), ז'אנר: {row['Genre']}, דירוג: {row['Rating']}, תקציר: {row['Overview'][:100]}..."
        )
    return "\n".join(lines)

@app.route("/recommend", methods=["POST"])
def recommend():
    data = request.get_json()
    if not data or "mood" not in data:
        return jsonify({"error": "Missing 'mood' parameter in JSON body"}), 400
    
    mood = data["mood"].strip()
    if not mood:
        return jsonify({"error": "Empty 'mood' parameter"}), 400

    # כמה סרטים לבקש? חפש מספר בהודעה (למשל "3 סרטים")
    num_movies = extract_number_of_movies(mood)

    # בחר סרטים עם דירוג גבוה
    high_rating_df = df[df['Rating'] >= 8.5]

    if len(high_rating_df) < num_movies:
        needed = num_movies - len(high_rating_df)
        other_movies = df[~df.index.isin(high_rating_df.index)]
        selected_movies = pd.concat([high_rating_df, other_movies.sample(n=needed)])
    else:
        selected_movies = high_rating_df.sample(n=num_movies)

    movies_text = ""
    for m in selected_movies[['Series_Title', 'Released_Year', 'Genre', 'Rating', 'Overview']].to_dict(orient='records'):
        movies_text += f"{m['Series_Title']} ({m['Released_Year']}), ז'אנר: {m['Genre']}, דירוג: {m['Rating']}\nתקציר: {m['Overview']}\n\n"

    prompt = (
        f"המשתמש כתב: {mood}\n\n"
        f"הנה רשימת הסרטים:\n\n{movies_text}\n\n"
        f"בחר {num_movies} סרטים שמתאימים לבקשה ולמצב הרוח של המשתמש. "
        f"ענה בעברית בלבד, בצורה חמה וחברית. עבור כל סרט כתוב את כל המידע בפסקה אחת רציפה וברורה, "
        f"כולל שם הסרט באנגלית, שנה, ז'אנר, דירוג, תקציר באנגלית, ומשפט הסבר למה בחרת דווקא אותו. "
        f"אל תשתמש במספרים, כותרות או רשימות ממוספרות. "
        f"הפרד בין סרט לסרט על ידי שורה ריקה בלבד. "
        f"אל תמציא סרטים – השתמש רק באלו שסיפקתי."
    )

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "ענה בעברית בלבד. אל תמציא מידע."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=300,
        )
        answer = response.choices[0].message.content.strip()
        return jsonify({"recommendation": answer})

    except Exception as e:
        print("⚠️ שגיאה מ־OpenAI:", e)
        return jsonify({"error": "אירעה שגיאה בעת עיבוד ההמלצה. נסה שוב מאוחר יותר."}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
