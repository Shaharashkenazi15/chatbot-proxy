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
recommendation_keywords = ["תמליץ", "סרטים", "מה לראות", "סרט", "ממליץ", "מומלץ", "רוצה לראות"]

def detect_mood(message):
    message = message.lower()
    if any(word in message for word in ["רע", "עצוב", "בדיכאון", "בוכה", "נורא"]):
        return "עצוב"
    if any(word in message for word in ["כועס", "עצבני", "מתוסכל", "מרוגז"]):
        return "כועס"
    if any(word in message for word in ["כיף", "שמח", "מאושר", "טוב לי", "מצוין"]):
        return "שמח"
    if any(word in message for word in ["לחוץ", "חרד", "עומס", "בלחץ"]):
        return "לחוץ"
    return "רגיל"

def extract_number_of_movies(message):
    match = re.search(r'(\d+)\s*סרט', message)
    if match:
        return min(int(match.group(1)), 5)
    return 1

def build_movies_text(df_movies):
    movies_text = ""
    for m in df_movies[['Series_Title', 'Released_Year', 'Genre', 'Rating', 'Overview', 'Star1', 'Runtime']].to_dict(orient='records'):
        star1 = m['Star1'] if pd.notna(m['Star1']) else "לא ידוע"
        runtime = re.search(r'\d+', str(m['Runtime']))
        runtime = f"{runtime.group()} דקות" if runtime else "לא ידוע"

        movies_text += (
            f"{m['Series_Title']} – {m['Released_Year']}\n"
            f"תקציר: {m['Overview']}\n"
            f"שחקן ראשי: {star1}\n"
            f"ז'אנר: {m['Genre']}\n"
            f"אורך: {runtime}\n\n"
        )
    return movies_text

@app.route("/chat", methods=["POST"])
def chat():
    if df.empty:
        return jsonify({"response": "לא ניתן לטעון את רשימת הסרטים כרגע. נסה שוב מאוחר יותר."}), 500

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

    high_rating_df = df[df['Rating'] >= 8.5]

    if len(high_rating_df) < num_movies:
        needed = num_movies - len(high_rating_df)
        other_movies = df[~df.index.isin(high_rating_df.index)].sample(n=needed)
        selected_movies = pd.concat([high_rating_df, other_movies]).sample(n=num_movies)
    else:
        selected_movies = high_rating_df.sample(n=num_movies)

    movies_text = build_movies_text(selected_movies)
    mood = detect_mood(user_message)

    prompt = (
        f"המשתמש כתב: {user_message} (מצב רוח: {mood})\n\n"
        f"הנה רשימת הסרטים:\n\n{movies_text}\n\n"
        f"בחר סרטים שמתאימים לבקשה ולמצב הרוח של המשתמש. "
        f"ענה בעברית בצורה חמה וחברית. עבור כל סרט כתוב את כל המידע בפסקה אחת רציפה וברורה, "
        f"כולל שם הסרט באנגלית בלבד, שנה, ז'אנר, תקציר באנגלית בלבד, שחקן ראשי ואורך הסרט. "
        f"הפרד בין סרט לסרט על ידי שורה ריקה בלבד. "
        f"תסביר למה דווקא בחרת בסרט הזה בצורה חמה וידידותית. "
        f"אל תמציא סרטים – השתמש רק באלו שסיפקתי."
    )

    try:
        response = openai.ChatCompletion.create(
            temperature=0.7,
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": (
                    "ענה בעברית בצורה חמה וחברית. "
                    "עבור כל סרט כתוב פסקה אחת שמכילה: "
                    "שם הסרט באנגלית בלבד, שנת יציאה, ז'אנר, תקציר באנגלית בלבד, שחקן ראשי ואורך הסרט. "
                    "אל תמציא מידע או סרטים – השתמש רק ברשימה שסופקה. "
                    "הצג כל סרט כבלוק עצמאי, והפרד בין סרטים בעזרת שורה ריקה בלבד."
                )},
                {"role": "user", "content": prompt}
            ]
        )
        return jsonify({"response": response.choices[0].message.content})

    except Exception as e:
        print("⚠️ שגיאה:", e)
        return jsonify({"response": "אירעה שגיאה בעת עיבוד ההמלצה. נסה שוב מאוחר יותר."}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
