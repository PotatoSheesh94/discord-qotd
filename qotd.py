import os
import json
import html
import random
import hashlib
import re
import time
from pathlib import Path

import requests


# ============================================================
# CONFIGURATION
# ============================================================

WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]
BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
CHANNEL_ID = os.environ["DISCORD_CHANNEL_ID"]

WEBHOOK_NAME = "Nickolas Lilly Assistant"

API_URL = "https://opentdb.com/api.php"
DISCORD_API = "https://discord.com/api/v10"

# This now comes from GitHub Actions
DURATION_MINUTES = int(os.environ.get("QOTD_DURATION", "10"))
COUNTDOWN_SECONDS = DURATION_MINUTES * 60

# Check Discord messages every 5 seconds
POLL_INTERVAL = 5

# Update the visible countdown every 10 seconds
COUNTDOWN_UPDATE_INTERVAL = 10

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

CURRENT_FILE = DATA_DIR / "current_question.json"
USED_FILE = DATA_DIR / "used_questions.json"
LEADERBOARD_FILE = DATA_DIR / "leaderboard.json"


CATEGORIES = [
    9,   # General Knowledge
    10,  # Books
    11,  # Film
    12,  # Music
    14,  # Television
    15,  # Video Games
    16,  # Board Games
    17,  # Science & Nature
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
    32,  # Cartoons & Animation
]


# ============================================================
# FILE HELPERS
# ============================================================

def load_json(path, default):
    if not path.exists():
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ============================================================
# DISCORD API
# ============================================================

def bot_headers():
    return {
        "Authorization": f"Bot {BOT_TOKEN}",
        "Content-Type": "application/json",
    }


def rename_webhook():
    try:
        response = requests.patch(
            WEBHOOK_URL,
            json={"name": WEBHOOK_NAME},
            timeout=20,
        )

        if response.status_code not in (200, 204):
            print(
                "Webhook rename failed:",
                response.status_code,
                response.text,
            )

    except Exception as e:
        print("Webhook rename error:", e)


def send_webhook(payload, wait_for_message=False):
    url = WEBHOOK_URL

    if wait_for_message:
        separator = "&" if "?" in url else "?"
        url += separator + "wait=true"

    response = requests.post(
        url,
        json=payload,
        timeout=30,
    )

    if response.status_code not in (200, 204):
        raise RuntimeError(
            f"Discord webhook error "
            f"{response.status_code}: {response.text}"
        )

    if wait_for_message and response.text:
        return response.json()

    return None


def edit_webhook_message(message_id, payload):
    response = requests.patch(
        f"{WEBHOOK_URL}/messages/{message_id}",
        json=payload,
        timeout=30,
    )

    if response.status_code not in (200, 204):
        print(
            "Webhook message edit failed:",
            response.status_code,
            response.text,
        )

    return response


def send_bot_message(
    content=None,
    embed=None,
    allowed_users=None,
):
    payload = {}

    if content:
        payload["content"] = content

    if embed:
        payload["embeds"] = [embed]

    if allowed_users:
        payload["allowed_mentions"] = {
            "users": allowed_users
        }

    response = requests.post(
        f"{DISCORD_API}/channels/{CHANNEL_ID}/messages",
        headers=bot_headers(),
        json=payload,
        timeout=30,
    )

    if response.status_code not in (200, 201):
        print(
            "Bot message failed:",
            response.status_code,
            response.text,
        )

    return response


def get_messages_after(message_id):
    response = requests.get(
        f"{DISCORD_API}/channels/{CHANNEL_ID}/messages",
        headers=bot_headers(),
        params={
            "after": message_id,
            "limit": 100,
        },
        timeout=30,
    )

    if response.status_code != 200:
        print(
            "Message fetch failed:",
            response.status_code,
            response.text,
        )
        return []

    return response.json()


# ============================================================
# QUESTION SYSTEM
# ============================================================

def question_hash(question):
    return hashlib.sha256(
        question.strip().lower().encode("utf-8")
    ).hexdigest()


def get_random_question():
    used_questions = load_json(USED_FILE, [])

    for _ in range(10):
        category = random.choice(CATEGORIES)

        response = requests.get(
            API_URL,
            params={
                "amount": 20,
                "category": category,
                "type": "multiple",
            },
            timeout=30,
        )

        response.raise_for_status()

        data = response.json()

        if data.get("response_code") != 0:
            continue

        questions = data.get("results", [])
        random.shuffle(questions)

        for item in questions:
            question = html.unescape(item["question"])
            q_hash = question_hash(question)

            if q_hash in used_questions:
                continue

            correct = html.unescape(
                item["correct_answer"]
            )

            incorrect = [
                html.unescape(answer)
                for answer in item["incorrect_answers"]
            ]

            answers = incorrect + [correct]
            random.shuffle(answers)

            correct_index = answers.index(correct)

            used_questions.append(q_hash)

            if len(used_questions) > 5000:
                used_questions = used_questions[-5000:]

            save_json(
                USED_FILE,
                used_questions,
            )

            return {
                "question": question,
                "answers": answers,
                "correct_index": correct_index,
                "category": html.unescape(
                    item["category"]
                ),
                "difficulty": item["difficulty"].capitalize(),
                "hash": q_hash,
            }

    raise RuntimeError(
        "Could not find a new question."
    )


def letter_for_index(index):
    return chr(ord("A") + index)


# ============================================================
# ANSWER PARSING
# ============================================================

def parse_answer(content):
    text = content.strip()

    match = re.fullmatch(
        r"(?:answer\s*[:\-]?\s*)?([ABCD])[\.\)]?",
        text,
        re.IGNORECASE,
    )

    if match:
        return match.group(1).upper()

    return None


# ============================================================
# LEADERBOARD
# ============================================================

def load_leaderboard():
    return load_json(
        LEADERBOARD_FILE,
        {},
    )


def save_leaderboard(board):
    save_json(
        LEADERBOARD_FILE,
        board,
    )


def add_point(board, user):
    user_id = str(user["id"])

    if user_id not in board:
        board[user_id] = {
            "username": (
                user.get("global_name")
                or user.get("username")
                or "Unknown User"
            ),
            "points": 0,
        }

    board[user_id]["username"] = (
        user.get("global_name")
        or user.get("username")
        or board[user_id]["username"]
    )

    board[user_id]["points"] += 1


def leaderboard_text(board):
    if not board:
        return "No points have been earned yet."

    sorted_users = sorted(
        board.items(),
        key=lambda item: item[1]["points"],
        reverse=True,
    )

    lines = []

    for position, (user_id, data) in enumerate(
        sorted_users[:10],
        start=1,
    ):
        points = data["points"]

        lines.append(
            f"**{position}.** <@{user_id}> • "
            f"**{points} point"
            f"{'s' if points != 1 else ''}**"
        )

    return "\n".join(lines)


# ============================================================
# EMBEDS
# ============================================================

def build_question_embed(
    question_data,
    remaining_seconds,
):
    minutes = remaining_seconds // 60
    seconds = remaining_seconds % 60

    timer = f"{minutes:02d}:{seconds:02d}"

    answers = "\n".join(
        f"**{letter_for_index(i)}.** {answer}"
        for i, answer in enumerate(
            question_data["answers"]
        )
    )

    return {
        "title": "🧠 Question of the Day",
        "description": (
            f"**{question_data['question']}**\n\n"
            f"{answers}\n\n"
            f"⏱️ **Time remaining: {timer}**\n\n"
            "Reply with **A, B, C, or D** to submit "
            "your answer."
        ),
        "color": 65413,
        "fields": [
            {
                "name": "📚 Category",
                "value": question_data["category"],
                "inline": True,
            },
            {
                "name": "🎯 Difficulty",
                "value": question_data["difficulty"],
                "inline": True,
            },
        ],
        "footer": {
            "text": (
                "Nickolas Lilly Assistant • "
                "Question of the Day"
            )
        },
    }


def build_closed_embed(question_data):
    answers = "\n".join(
        f"**{letter_for_index(i)}.** {answer}"
        for i, answer in enumerate(
            question_data["answers"]
        )
    )

    return {
        "title": "🧠 Question of the Day",
        "description": (
            f"**{question_data['question']}**\n\n"
            f"{answers}\n\n"
            "⏱️ **Time remaining: 00:00**\n\n"
            "🔒 **Answers are now closed.**"
        ),
        "color": 65413,
        "fields": [
            {
                "name": "📚 Category",
                "value": question_data["category"],
                "inline": True,
            },
            {
                "name": "🎯 Difficulty",
                "value": question_data["difficulty"],
                "inline": True,
            },
        ],
        "footer": {
            "text": (
                "Nickolas Lilly Assistant • "
                "Question of the Day"
            )
        },
    }


def build_answer_embed(question_data):
    correct = question_data["answers"][
        question_data["correct_index"]
    ]

    letter = letter_for_index(
        question_data["correct_index"]
    )

    return {
        "title": "💡 Question of the Day Answer",
        "description": (
            "The correct answer was:\n\n"
            f"**{letter}. {correct}**"
        ),
        "color": 5763719,
        "footer": {
            "text": "Thanks for participating!"
        },
    }


# ============================================================
# MAIN QOTD
# ============================================================

def run_qotd():
    print(
        f"Starting QOTD with a "
        f"{DURATION_MINUTES}-minute countdown."
    )

    rename_webhook()

    question_data = get_random_question()

    # --------------------------------------------------------
    # Post question
    # --------------------------------------------------------

    question_message = send_webhook(
        {
            "username": WEBHOOK_NAME,
            "embeds": [
                build_question_embed(
                    question_data,
                    COUNTDOWN_SECONDS,
                )
            ],
        },
        wait_for_message=True,
    )

    if not question_message:
        raise RuntimeError(
            "Discord did not return the QOTD message."
        )

    question_message_id = question_message["id"]

    # Save current question
    save_json(
        CURRENT_FILE,
        {
            **question_data,
            "message_id": question_message_id,
            "duration_minutes": DURATION_MINUTES,
        },
    )

    print(
        f"Question posted: {question_message_id}"
    )

    # --------------------------------------------------------
    # Start countdown
    # --------------------------------------------------------

    start_time = time.monotonic()
    end_time = start_time + COUNTDOWN_SECONDS

    last_message_id = question_message_id

    leaderboard = load_leaderboard()

    already_awarded = set()

    last_countdown_update = 0

    print(
        f"Countdown started for "
        f"{DURATION_MINUTES} minute(s)."
    )

    while True:
        now = time.monotonic()

        remaining = max(
            0,
            int(end_time - now)
        )

        # ----------------------------------------------------
        # Update visible countdown
        # ----------------------------------------------------

        if (
            last_countdown_update == 0
            or now - last_countdown_update
            >= COUNTDOWN_UPDATE_INTERVAL
            or remaining <= 0
        ):
            print(
                f"Updating countdown: "
                f"{remaining // 60:02d}:"
                f"{remaining % 60:02d}"
            )

            edit_webhook_message(
                question_message_id,
                {
                    "embeds": [
                        build_question_embed(
                            question_data,
                            remaining,
                        )
                    ]
                },
            )

            last_countdown_update = now

        # ----------------------------------------------------
        # Check Discord answers
        # ----------------------------------------------------

        messages = get_messages_after(
            last_message_id
        )

        for message in messages:
            last_message_id = message["id"]

            author = message.get(
                "author",
                {},
            )

            # Ignore bots
            if author.get("bot"):
                continue

            answer = parse_answer(
                message.get("content", "")
            )

            if not answer:
                continue

            correct_letter = letter_for_index(
                question_data["correct_index"]
            )

            if answer != correct_letter:
                continue

            user_id = str(author["id"])

            # Only one point per user
            if user_id in already_awarded:
                continue

            already_awarded.add(user_id)

            add_point(
                leaderboard,
                author,
            )

            save_leaderboard(
                leaderboard
            )

            print(
                f"Correct answer: "
                f"{author.get('username')} "
                f"({user_id})"
            )

            send_bot_message(
                content=(
                    f"🎉 <@{user_id}> got it correct! "
                    f"**+1 point!**"
                ),
                allowed_users=[user_id],
            )

        # ----------------------------------------------------
        # Countdown finished
        # ----------------------------------------------------

        if remaining <= 0:
            break

        time.sleep(
            min(
                POLL_INTERVAL,
                remaining,
            )
        )

    # --------------------------------------------------------
    # Force final 00:00 message
    # --------------------------------------------------------

    print("Countdown reached 00:00.")

    edit_webhook_message(
        question_message_id,
        {
            "embeds": [
                build_closed_embed(
                    question_data
                )
            ]
        },
    )

    # --------------------------------------------------------
    # Reveal answer
    # --------------------------------------------------------

    print("Sending correct answer...")

    send_bot_message(
        embed=build_answer_embed(
            question_data
        )
    )

    # --------------------------------------------------------
    # Winners
    # --------------------------------------------------------

    if already_awarded:
        mentions = " ".join(
            f"<@{user_id}>"
            for user_id in already_awarded
        )

        send_bot_message(
            content=(
                "🏆 **Today's correct answers:**\n"
                f"{mentions}\n\n"
                "Each correct user earned "
                "**+1 point**."
            ),
            allowed_users=list(
                already_awarded
            ),
        )
    else:
        send_bot_message(
            content=(
                "😅 **Nobody got today's question "
                "correct.**\n"
                "Better luck next time!"
            )
        )

    # --------------------------------------------------------
    # Leaderboard
    # --------------------------------------------------------

    send_bot_message(
        embed={
            "title": "🏆 QOTD Leaderboard",
            "description": leaderboard_text(
                leaderboard
            ),
            "color": 65413,
            "footer": {
                "text": (
                    "Top 10 Question of the Day scores"
                )
            },
        }
    )

    save_leaderboard(
        leaderboard
    )

    print("QOTD completed successfully.")


if __name__ == "__main__":
    run_qotd()
