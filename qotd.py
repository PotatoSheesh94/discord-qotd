import os
import html
import random
import requests

WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]

# Random categories from Open Trivia DB.
# These are mostly general-interest categories.
CATEGORIES = [
    9,   # General Knowledge
    10,  # Books
    11,  # Film
    12,  # Music
    14,  # Television
    15,  # Video Games
    16,  # Board Games
    17,  # Science
    18,  # Computers
    19,  # Mathematics
    20,  # Mythology
    21,  # Sports
    22,  # Geography
    23,  # History
    25,  # Art
    26,  # Celebrities
    27,  # Animals
    28,  # Vehicles
    29,  # Comics
    30,  # Gadgets
    31,  # Japanese Anime & Manga
    32   # Cartoon & Animations
]

CATEGORY_NAMES = {
    9: "General Knowledge",
    10: "Books",
    11: "Film",
    12: "Music",
    14: "Television",
    15: "Video Games",
    16: "Board Games",
    17: "Science",
    18: "Computers",
    19: "Mathematics",
    20: "Mythology",
    21: "Sports",
    22: "Geography",
    23: "History",
    25: "Art",
    26: "Celebrities",
    27: "Animals",
    28: "Vehicles",
    29: "Comics",
    30: "Gadgets",
    31: "Japanese Anime & Manga",
    32: "Cartoon & Animations"
}


def get_question():
    category = random.choice(CATEGORIES)

    url = (
        "https://opentdb.com/api.php"
        f"?amount=1&category={category}&type=multiple"
    )

    response = requests.get(url, timeout=15)
    response.raise_for_status()

    data = response.json()

    if data.get("response_code") != 0:
        raise RuntimeError(
            f"Open Trivia DB returned response code "
            f"{data.get('response_code')}"
        )

    question = data["results"][0]

    return {
        "category": CATEGORY_NAMES.get(category, "Trivia"),
        "question": html.unescape(question["question"]),
        "correct_answer": html.unescape(question["correct_answer"]),
    }


def send_to_discord(question):
    embed = {
        "title": "🧠 Question of the Day",
        "description": (
            f"**{question['question']}**\n\n"
            "💬 **What do you think the answer is?**\n"
            "Reply below and see if you can get it right!"
        ),
        "color": 65413,
        "fields": [
            {
                "name": "📚 Category",
                "value": question["category"],
                "inline": True
            },
            {
                "name": "💡 Answer",
                "value": f"||{question['correct_answer']}||",
                "inline": True
            }
        ],
        "footer": {
            "text": "Daily Question • Powered by Open Trivia DB"
        }
    }

    payload = {
        "username": "Question of the Day",
        "embeds": [embed],
        "allowed_mentions": {
            "parse": []
        }
    }

    response = requests.post(
        WEBHOOK_URL,
        json=payload,
        timeout=15
    )

    response.raise_for_status()


def main():
    question = get_question()

    print("Question:")
    print(question["question"])
    print()
    print("Answer:")
    print(question["correct_answer"])

    send_to_discord(question)

    print("Successfully sent the Question of the Day!")


if __name__ == "__main__":
    main()
