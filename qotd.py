import os
import json
import html
import random
import hashlib
from pathlib import Path

import requests


# ============================================================
# CONFIGURATION
# ============================================================

WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]

WEBHOOK_NAME = "Nickolas Lilly Assistant"

API_URL = "https://opentdb.com/api.php"

DATA_DIR = Path("data")
CURRENT_QUESTION_FILE = DATA_DIR / "current_question.json"
USED_QUESTIONS_FILE = DATA_DIR / "used_questions.json"


# ============================================================
# TRIVIA CATEGORIES
# ============================================================

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
    32,  # Cartoon & Animations
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
    32: "Cartoon & Animations",
}


DIFFICULTY_NAMES = {
    "easy": "Easy",
    "medium": "Medium",
    "hard": "Hard",
}


# ============================================================
# FILE HELPERS
# ============================================================

def ensure_data_directory():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_json(path, default):
    if not path.exists():
        return default

    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except Exception as error:
        print(f"Could not read {path}: {error}")
        return default


def save_json(path, data):
    ensure_data_directory()

    with path.open("w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False,
        )


# ============================================================
# QUESTION ID
# ============================================================

def create_question_id(question):
    normalized = " ".join(question.lower().split())

    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()


# ============================================================
# GET RANDOM QUESTION
# ============================================================

def get_random_question():
    used_questions = set(
        load_json(USED_QUESTIONS_FILE, [])
    )

    # Try several categories and batches.
    for attempt in range(10):
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
            print(
                "Open Trivia DB response code:",
                data.get("response_code"),
            )
            continue

        questions = data.get("results", [])

        random.shuffle(questions)

        for item in questions:
            question_text = html.unescape(
                item["question"]
            )

            question_id = create_question_id(
                question_text
            )

            if question_id in used_questions:
                continue

            correct_answer = html.unescape(
                item["correct_answer"]
            )

            incorrect_answers = [
                html.unescape(answer)
                for answer in item["incorrect_answers"]
            ]

            answers = incorrect_answers + [
                correct_answer
            ]

            random.shuffle(answers)

            question = {
                "id": question_id,
                "question": question_text,
                "correct_answer": correct_answer,
                "answers": answers,
                "category": CATEGORY_NAMES.get(
                    category,
                    "Trivia",
                ),
                "difficulty": DIFFICULTY_NAMES.get(
                    item.get("difficulty"),
                    "Unknown",
                ),
            }

            used_questions.add(question_id)

            save_json(
                USED_QUESTIONS_FILE,
                sorted(used_questions),
            )

            return question

    # If the database eventually contains almost everything,
    # allow a fresh question instead of completely failing.
    print(
        "Could not find an unused question. "
        "Requesting a fresh random question."
    )

    category = random.choice(CATEGORIES)

    params = {
        "amount": 1,
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
            "Open Trivia DB could not provide a question."
        )

    item = data["results"][0]

    question_text = html.unescape(
        item["question"]
    )

    correct_answer = html.unescape(
        item["correct_answer"]
    )

    incorrect_answers = [
        html.unescape(answer)
        for answer in item["incorrect_answers"]
    ]

    answers = incorrect_answers + [
        correct_answer
    ]

    random.shuffle(answers)

    return {
        "id": create_question_id(question_text),
        "question": question_text,
        "correct_answer": correct_answer,
        "answers": answers,
        "category": CATEGORY_NAMES.get(
            category,
            "Trivia",
        ),
        "difficulty": DIFFICULTY_NAMES.get(
            item.get("difficulty"),
            "Unknown",
        ),
    }


# ============================================================
# DISCORD WEBHOOK
# ============================================================

def discord_request(method, url, **kwargs):
    response = requests.request(
        method,
        url,
        timeout=20,
        **kwargs,
    )

    if response.status_code >= 400:
        print(
            f"Discord HTTP {response.status_code}: "
            f"{response.text}"
        )

    response.raise_for_status()

    return response


def rename_webhook():
    try:
        discord_request(
            "PATCH",
            WEBHOOK_URL,
            json={
                "name": WEBHOOK_NAME
            },
        )

        print(
            f"Webhook name set to: {WEBHOOK_NAME}"
        )

    except Exception as error:
        print(
            f"Webhook rename failed: {error}"
        )


# ============================================================
# ANSWER FORMAT
# ============================================================

def format_answers(answers):
    letters = ["A", "B", "C", "D"]

    return "\n".join(
        f"**{letter}.** {answer}"
        for letter, answer in zip(
            letters,
            answers,
        )
    )


# ============================================================
# SEND QUESTION
# ============================================================

def send_question(question):
    embed = {
        "title": "🧠 Question of the Day",
        "description": (
            f"**{question['question']}**\n\n"
            f"{format_answers(question['answers'])}\n\n"
            "💬 **What do you think the answer is?**\n"
            "You have **10 minutes** to answer!"
        ),
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
            "text": (
                "Nickolas Lilly Assistant • "
                "Daily QOTD • Answer in 10 minutes"
            )
        },
    }

    payload = {
        "username": WEBHOOK_NAME,
        "embeds": [embed],
        "allowed_mentions": {
            "parse": [],
        },
    }

    discord_request(
        "POST",
        WEBHOOK_URL,
        json=payload,
    )

    print("Question sent successfully.")


# ============================================================
# SEND ANSWER
# ============================================================

def send_answer(question):
    embed = {
        "title": "💡 Question of the Day Answer",
        "description": (
            "The 10-minute answer period is over!\n\n"
            f"## ✅ {question['correct_answer']}\n\n"
            "Thanks to everyone who participated! 🎉"
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
            "text": (
                "Nickolas Lilly Assistant • "
                "Answer Reveal"
            )
        },
    }

    payload = {
        "username": WEBHOOK_NAME,
        "embeds": [embed],
        "allowed_mentions": {
            "parse": [],
        },
    }

    discord_request(
        "POST",
        WEBHOOK_URL,
        json=payload,
    )

    print("Answer sent successfully.")


# ============================================================
# QUESTION JOB
# ============================================================

def question_job():
    print(
        "Starting Question of the Day..."
    )

    rename_webhook()

    question = get_random_question()

    print()
    print("Question:", question["question"])
    print("Answer:", question["correct_answer"])
    print("Category:", question["category"])
    print("Difficulty:", question["difficulty"])

    save_json(
        CURRENT_QUESTION_FILE,
        question,
    )

    send_question(question)

    print(
        "Question saved for the answer-reveal job."
    )


# ============================================================
# ANSWER JOB
# ============================================================

def answer_job():
    print(
        "Starting Question of the Day answer reveal..."
    )

    if not CURRENT_QUESTION_FILE.exists():
        raise RuntimeError(
            "No current question was found."
        )

    question = load_json(
        CURRENT_QUESTION_FILE,
        None,
    )

    if not question:
        raise RuntimeError(
            "Current question file is empty."
        )

    rename_webhook()

    send_answer(question)

    print(
        "Answer reveal completed successfully."
    )


# ============================================================
# MAIN
# ============================================================

def main():
    mode = os.environ.get(
        "QOTD_MODE",
        "question",
    )

    if mode == "question":
        question_job()

    elif mode == "answer":
        answer_job()

    else:
        raise ValueError(
            f"Unknown QOTD_MODE: {mode}"
        )


if __name__ == "__main__":
    main()
