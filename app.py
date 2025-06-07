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

# ז'אנרים לפי מצב רוח
mood_genres = {
    "עצוב": ["Comedy", "Animation", "Adventure", "Fantasy"],
    "כועס": ["Action", "Thriller", "Adventure"],
    "שמח": ["Comedy", "Musical", "Romance", "Adventure"],
    "לחוץ": ["Drama", "Sci-Fi", "Fantasy"],
}

def detect_mood(message):
    message = message.lower()
    if any(word in message for word in ["רע", "עצוב", "בדיכאון", "בוכה"]):
        return "עצוב"
    if any(word in message for word in ["כועס", "עצבני", "מתוסכל"]):
        return "כועס"
    if any(word in message for word in ["כיף", "שמח", "מאושר", "טוב לי"]):
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
    mood = detect_mood(user_message)
    high_rating_df = df[df['Rating'] >= 8.5]

    if said_greeting and not wants_recommendation:
        return jsonify({
            "response": "שלום! אני אשמח להמליץ לך על סרטים. כתוב לי איך אתה מרגיש או איזה סוג סרט בא לך לראות."
        })

    if wants_recommendation:
        if mood != "רגיל":
            # יש מצב רוח – בחר סרטים לפי ז'אנרים
            genres = mood_genres.get(mood, [])
            mood_movies = high_rating_df[high_rating_df['Genre'].str.contains('|'.join(genres), case=False, na=False)]
            if len(mood_movies) < 10:
                mood_movies = pd.concat([mood_movies, high_rating_df]).drop_duplicates()
            selected_movies = mood_movies.sample(n=min(30, len(mood_movies)))
            num_movies = 3  # מספר סופי לבחירה ב־GPT
        else:
            # אין מצב רוח – המלצה רגילה
            num_movies = extract_number_of_movies(user_message)
            if said_greeting:
                num_movies = max(num_movies, 3)

            if len(high_rating_df) < num_movies:
                needed = num_movies - len(high_rating_df)
                other_movies = df[~df.index.isin(high_rating_df.index)]
                selected_movies = pd.concat([high_rating_df, other_movies.sample(n=needed)])
            else:
                selected_movies = high_rating_df.sample(n=num_movies)
    else:
        return jsonify({
            "response": "שלום! אני פה בשביל להמליץ לך על סרטים שמתאימים בדיוק למצב הרוח שלך. תכתוב לי איך אתה מרגיש, או פשוט תבקש המלצה!"
        })

    movies_text = ""
    for m in selected_movies[['Series_Title', 'Released_Year', 'Genre', 'Rating', 'Overview', 'Star1', 'Runtime']].to_dict(orient='records'):
        star1 = m['Star1'] if pd.notna(m['Star1']) else "לא ידוע"
        runtime = f"{m['Runtime']} דקות" if pd.notna(m['Runtime']) else "לא ידוע"
        movies_text += (
            f"{m['Series_Title']} – {m['Released_Year']}\n"
            f"תקציר: {m['Overview']}\n"
            f"שחקן ראשי: {star1}\n"
            f"ז'אנר: {m['Genre']}\n"
            f"אורך: {runtime}\n\n"
        )

    prompt = (
        f"המשתמש כתב: {user_message} (מצב רוח: {mood})\n\n"
        f"הנה רשימת הסרטים:\n\n{movies_text}\n\n"
        f"בחר {num_movies} סרטים שמתאימים לבקשה ולמצב הרוח של המשתמש. "
        f"ענה בעברית, בצורה חמה וחברית. עבור כל סרט כתוב את כל המידע בפסקה אחת רציפה וברורה, "
        f"כולל שם הסרט באנגלית בלבד, שנה, ז'אנר, תקציר באנגלית בלבד, שחקן ראשי ואורך הסרט. "
        f"הפרד בין סרט לסרט על ידי שורה ריקה בלבד. "
        f"תסביר למה דווקא בחרת בסרט הזה בצורה חמה וידידותית. "
        f"אל תמציא סרטים – השתמש רק באלו שסיפקתי."
    )

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "ענה בעברית. שם הסרט והתקציר שלו באנגלית בלבד. אל תמציא סרטים. הצג כל סרט בפסקה מופרדת."},
                {"role": "user", "content": prompt}
            ]
        )
        raw_response = response.choices[0].message.content
        return jsonify({"response": raw_response})
    except Exception as e:
        print("⚠️ שגיאה:", e)
        return jsonify({"response": "אירעה שגיאה בעת עיבוד ההמלצה. נסה שוב מאוחר יותר."}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
