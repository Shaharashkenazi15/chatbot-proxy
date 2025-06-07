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

general_phrases = ["שלום", "מה נשמע", "מה קורה", "מה שלומך", "היי", "אהלן"]
recommendation_keywords = ["תמליץ", "סרטים", "מה לראות", "סרט", "ממליץ"]

def detect_mood(message):
    message = message.lower()
    if any(word in message for word in ["עצוב", "בדיכאון", "בוכה"]):
        return "עצוב"
    if any(word in message for word in ["כועס", "עצבני", "מתוסכל"]):
        return "כועס"
    if any(word in message for word in ["שמח", "מאושר", "טוב לי"]):
        return "שמח"
    if any(word in message for word in ["לחוץ", "חרד", "עומס"]):
        return "לחוץ"
    return "רגיל"

def extract_number_of_movies(message):
    match = re.search(r'(\d+)\s*סרט', message)
    if match:
        return min(int(match.group(1)), 5)
    return 1

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    messages = data.get("messages", [])
    user_message = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "").lower()

    wants_recommendation = any(k in user_message for k in recommendation_keywords)
    said_greeting = any(p in user_message for p in general_phrases)

    if said_greeting and not wants_recommendation:
        return jsonify({
            "response": "שלום! אני אשמח להמליץ לך על סרטים. כתוב לי איך אתה מרגיש או איזה סוג סרט בא לך לראות."
        })

    num_movies = extract_number_of_movies(user_message) if wants_recommendation else 1
    if said_greeting and wants_recommendation:
        num_movies = max(num_movies, 3)

    # בחר סרטים עם דירוג גבוה או דגימה מהשאר
    high_rating_df = df[df['Rating'] >= 8.5]

    if len(high_rating_df) < num_movies:
        needed = num_movies - len(high_rating_df)
        other_movies = df[~df.index.isin(high_rating_df.index)]
        selected_movies = pd.concat([high_rating_df, other_movies.sample(n=needed, random_state=42)])
    else:
        selected_movies = high_rating_df.sample(n=num_movies, random_state=42)

    movies_text = ""
    for m in selected_movies[['Series_Title', 'Released_Year', 'Genre', 'Rating', 'Overview']].to_dict(orient='records'):
        movies_text += f"{m['Series_Title']} ({m['Released_Year']}), ז'אנר: {m['Genre']}, דירוג: {m['Rating']}\nתקציר: {m['Overview']}\n\n"

    prompt = (
        f"המשתמש כתב: {user_message} (מצב רוח: {detect_mood(user_message)})\n\n"
        f"הנה רשימת הסרטים:\n\n{movies_text}\n\n"
        f"בחר {num_movies} סרטים שמתאימים לבקשה ולמצב הרוח של המשתמש. "
        f"ענה בעברית בלבד, בצורה חמה וחברית. עבור כל סרט כתוב:\n"
        f"1. שם הסרט באנגלית\n2. שנה\n3. ז'אנר\n4. דירוג\n5. תקציר בעברית\n6. משפט הסבר למה בחרת דווקא אותו.\n"
        f"תכתוב כל סרט כבלוק נפרד, ללא הקדמות או סיכומים כלליים. רק הרשימה.\n"
        f"אם אין בקשת המלצה, ענה באופן כללי וידידותי."
    )

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "אתה עוזר שממליץ על סרטים בעברית מתוך רשימה שניתנה."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500,
            temperature=0.7,
        )
        answer = response.choices[0].message.content.strip()
    except Exception as e:
        answer = "מצטער, קרתה שגיאה בשרת. אנא נסה שוב."

    return jsonify({"response": answer})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
