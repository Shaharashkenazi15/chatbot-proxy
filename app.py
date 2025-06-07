from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import pandas as pd
import re

app = Flask(__name__)  # ← זה חייב לבוא לפני כל @app.route
CORS(app)

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

    movies_list = selected_movies[['Series_Title', 'Released_Year', 'Genre', 'Rating', 'Overview']].to_dict(orient='records')

    movies_text = ""
    for m in movies_list:
        movies_text += f"{m['Series_Title']} ({m['Released_Year']}), ז'אנר: {m['Genre']}, דירוג: {m['Rating']}\nתקציר: {m['Overview']}\n\n"

    prompt = (
        f"המשתמש כתב: {user_message} (מצב רוח: {detect_mood(user_message)})\n\n"
        f"הנה רשימת הסרטים שנבחרו עבורך:\n\n{movies_text}\n\n"
        f"כתוב תיאור חם, ידידותי, ובעברית בלבד – עבור כל סרט. כל פסקה תכלול את שם הסרט באנגלית, השנה, הז'אנר, הדירוג, תקציר באנגלית (כפי שניתן), "
        f"ומשפט אחד אישי שמסביר למה הסרט מתאים לבקשה של המשתמש או למצב הרוח שלו.\n"
        f"אל תמציא סרטים ואל תוסיף סרטים אחרים. התייחס רק למה שסופק ברשימה.\n"
        f"הפרד בין סרט לסרט עם שורה ריקה בלבד. אל תשתמש במספרים או כותרות."
    )

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "ענה בעברית בלבד. הצג כל סרט כבלוק עצמאי. אל תמציא מידע."},
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


