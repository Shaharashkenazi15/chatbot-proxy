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
    if any(word in message for word in ["רע","עצוב", "בדיכאון", "בוכה"]):
        return "עצוב"
    if any(word in message for word in ["כועס", "עצבני", "מתוסכל"]):
        return "כועס"
    if any(word in message for word in ["כיף","שמח", "מאושר", "טוב לי"]):
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

    high_rating_df = df[df['Rating'] >= 8.5]

    if len(high_rating_df) < num_movies:
        needed = num_movies - len(high_rating_df)
        other_movies = df[~df.index.isin(high_rating_df.index)]
        selected_movies = pd.concat([high_rating_df, other_movies.sample(n=needed)])
    else:
        selected_movies = high_rating_df.sample(n=num_movies)

    movies_text = ""
    for m in selected_movies[['Series_Title', 'Released_Year', 'Genre', 'Rating', 'Overview', 'Star1', 'Runtime']].to_dict(orient='records'):
        star1 = m['Star1'] if pd.notna(m['Star1']) else "לא ידוע"
        runtime = f"{int(m['Runtime'])} דקות" if pd.notna(m['Runtime']) else "לא ידוע"

        # שים לב: שדה Series_Title כנראה באנגלית, אבל במקורית שים לב למה יש בקובץ שלך
        movies_text += (
            f"{m['Series_Title']}\n"
            f"Year: {m['Released_Year']}\n"
            f"Genre: {m['Genre']}\n"
            f"Overview: {m['Overview']}\n"
            f"Star: {star1}\n"
            f"Runtime: {runtime}\n\n"
        )

    mood = detect_mood(user_message)

    prompt = (
        f"המשתמש כתב: {user_message} (מצב רוח: {mood}, מגדר: זכר)\n\n"
        f"הנה רשימת הסרטים:\n\n{movies_text}\n\n"
        "בחר סרטים שמתאימים לבקשה ולמצב הרוח של המשתמש. "
        "ענה בעברית בלבד, בלשון זכר בלבד, בצורה חמה וידידותית. "
        "כתוב כל סרט בדיוק בפורמט הבא בלבד, ללא כל סטייה:\n"
        "<שם הסרט באנגלית בלבד>\n"
        "<שנת יציאה>\n"
        "<ז'אנר בעברית>\n"
        "<תקציר באנגלית בלבד>\n"
        "<שחקן ראשי>\n"
        "<אורך הסרט בדקות>\n"
        "תסביר למשתמש למה בחרת בסרט זה \n\n"
        "הפרד בין סרטים עם שורה ריקה בלבד. "
        "אל תמציא סרטים, אל תחרוג מהפורמט."
    )

    try:
        response = openai.ChatCompletion.create(
            temperature=0,
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": (
                    "ענה בעברית בלבד, בלשון זכר בלבד, בצורה חמה וידידותית. "
                    "הקפד להיצמד לפורמט הבא בלבד:\n"
                    "<שם הסרט באנגלית בלבד>\n"
                    "<שנת יציאה>\n"
                    "<ז'אנר בעברית>\n"
                    "<תקציר באנגלית בלבד>\n"
                    "<שחקן ראשי>\n"
                    "<אורך הסרט בדקות>\n"
                    "תסביר למשתמש למה בחרת בסרט זה \n\n"
                    "הפרד בין סרטים בשורה ריקה בלבד. "
                    "אסור לחרוג מהפורמט, אל תוסיף או תשנה מידע, ואל תמציא סרטים."
                )},
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
