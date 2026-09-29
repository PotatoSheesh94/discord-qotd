import os
import json
import html
import random
import hashlib
import time
from pathlib import Path

import requests


# ============================================================
# CONFIGURATION
# ============================================================

WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]

WEBHOOK_NAME = "Nickolas Lilly Assistant"

ANSWER_DELAY_SECONDS = 10 * 60

API_URL = "https://opentdb.com/api.php"

USED_FILE = Path("data/used_questions.json")

# Random categories
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
    31,  # Anime & Manga
    32,  # Cartoon & Animations
]


# ============================================================
# CATEGORY NAMES
# ============================================================

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
    32: "Cartoon & Animations",
}


# ============================================================
# DIFFICULTY
# ============================================================

DIFFICULTY_NAMES = {
    "easy": "Easy",
    "medium": "Medium",
    "hard": "Hard",
}


# ============================================================
# LOAD USED QUESTIONS
# ============================================================

def load_used_questions():
    if not USED_FILE.exists():
        return set()

    try:
        with USED_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, list):
            return set(data)

    except Exception as error:
        print(f"Could not read used question database: {error}")

    return set()


# ============================================================
# SAVE USED QUESTIONS
# ============================================================

def save_used_questions(used_questions):
    USED_FILE.parent.mkdir(parents=True, exist_ok=True)

    with USED_FILE.open("w", encoding="utf-8") as file:
        json.dump(
            sorted(used_questions),
            file,
            indent=2,
            ensure_ascii=False,
        )


# ============================================================
# CREATE QUESTION ID
# ============================================================

def question_id(question_text):
    normalized = " ".join(question_text.lower().split())

    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()


# ============================================================
# GET RANDOM QUESTION
# ============================================================

def get_question():
    used_questions = load_used_questions()

    # Try several times to find an unused question.
    for attempt in range(5):
        category = random.choice(CATEGORIES)

        params = {
            "amount": 20,
            "category": category,
            "type": "multiple",
        }

        response = requests.get(
            API_URL,
            params=params,
            timeout=20,
        )

        response.raise_for_status()

        data = response.json()

        if data.get("response_code") != 0:
            raise RuntimeError(
                f"Open Trivia DB returned response code "
                f"{data.get('response_code')}"
            )

        questions = data.get("results", [])

        random.shuffle(questions)

        for item in questions:
            question_text = html.unescape(
                item["question"]
            )

            qid = question_id(question_text)

            if qid in used_questions:
                continue

            correct_answer = html.unescape(
                item["correct_answer"]
            )

            incorrect_answers = [
                html.unescape(answer)
                for answer in item["incorrect_answers"]
            ]

            answers = incorrect_answers + [correct_answer]

            random.shuffle(answers)

            used_questions.add(qid)

            save_used_questions(used_questions)

            return {
                "id": qid,
                "question": question_text,
                "correct_answer": correct_answer,
                "answers": answers,
                "category": CATEGORY_NAMES.get(
                    category,
                    "Trivia",
                ),
                "difficulty": DIFFICULTY_NAMES.get(
                    item.get("difficulty", ""),
                    item.get("difficulty", "Unknown").title(),
                ),
            }

    raise RuntimeError(
        "Could not find an unused question."
    )


# ============================================================
# DISCORD WEBHOOK
# ============================================================

def webhook_request(method, url, **kwargs):
    response = requests.request(
        method,
        url,
        timeout=20,
        **kwargs,
    )

    if response.status_code >= 400:
        print(
            f"Discord returned HTTP {response.status_code}: "
            f"{response.text}"
        )

    response.raise_for_status()

    return response


# ============================================================
# RENAME WEBHOOK
# ============================================================

def rename_webhook():
    payload = {
        "name": WEBHOOK_NAME
    }

    try:
        webhook_request(
            "PATCH",
            WEBHOOK_URL,
            json=payload,
        )

        print(
            f"Webhook name updated to: {WEBHOOK_NAME}"
        )

    except Exception as error:
        # Do not stop the entire QOTD if renaming fails.
        print(
            f"Could not rename webhook: {error}"
        )


# ============================================================
# FORMAT ANSWERS
# ============================================================

def format_answers(answers):
    letters = ["A", "B", "C", "D"]

    lines = []

    for letter, answer in zip(letters, answers):
        lines.append(
            f"**{letter}.** {answer}"
        )

    return "\n".join(lines)


# ============================================================
# SEND QUESTION
# ============================================================

def send_question(question):
    description = (
        f"## 🧠 Question of the Day\n\n"
        f"**{question['question']}**\n\n"
        f"{format_answers(question['answers'])}\n\n"
        "💬 **What do you think the answer is?**\n"
        "You have **10 minutes** to answer!"
    )

    embed = {
        "title": "🧠 Question of the Day",
        "description": description,
        "color": 65413,
        "fields": [
            {
                "name": "📚 Category",
                "value": question["category"],
                "inline": True,
            },
            {
                "name": "🎯 Difficulty",
                "value": question["difficulty"],
                "inline": True,
            },
        ],
        "footer": {
            "text": "Nickolas Lilly Assistant • Daily QOTD"
        },
    }

    payload = {
        "username": WEBHOOK_NAME,
        "embeds": [embed],
        "allowed_mentions": {
            "parse": [],
        },
    }

    webhook_request(
        "POST",
        WEBHOOK_URL,
        json=payload,
    )

    print("Question successfully sent.")


# ============================================================
# SEND ANSWER
# ============================================================

def send_answer(question):
    answer_embed = {
        "title": "💡 The Answer",
        "description": (
            f"The correct answer was:\n\n"
            f"## ✅ {question['correct_answer']}\n\n"
            "Thanks for participating in today's "
            "Question of the Day!"
        ),
        "color": 5763719,
        "fields": [
            {
                "name": "📚 Category",
                "value": question["category"],
                "inline": True,
            },
            {
                "name": "🎯 Difficulty",
                "value": question["difficulty"],
                "inline": True,
            },
        ],
        "footer": {
            "text": "Nickolas Lilly Assistant • Answer Reveal"
        },
    }

    payload = {
        "username": WEBHOOK_NAME,
        "embeds": [answer_embed],
        "allowed_mentions": {
            "parse": [],
        },
    }

    webhook_request(
        "POST",
        WEBHOOK_URL,
        json=payload,
    )

    print("Correct answer successfully sent.")


# ============================================================
# MAIN
# ============================================================

def main():
    print("Starting Nickolas Lilly Assistant QOTD...")

    # Keep the actual Discord webhook name updated.
    rename_webhook()

    # Get a new question.
    question = get_question()

    print()
    print("Question:")
    print(question["question"])

    print()
    print("Correct answer:")
    print(question["correct_answer"])

    print()
    print(
        f"Waiting {ANSWER_DELAY_SECONDS // 60} minutes "
        "before revealing the answer..."
    )

    # Send the question first.
    send_question(question)

    # Wait 10 minutes.
    time.sleep(ANSWER_DELAY_SECONDS)

    # Reveal the answer.
    send_answer(question)

    print()
    print("QOTD completed successfully.")


if __name__ == "__main__":
    main()
