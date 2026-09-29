import os
import json
import html
import random
import hashlib
import re
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

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

COUNTDOWN_SECONDS = 10 * 60
POLL_INTERVAL = 10

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

CURRENT_FILE = DATA_DIR / "current_question.json"
USED_FILE = DATA_DIR / "used_questions.json"
LEADERBOARD_FILE = DATA_DIR / "leaderboard.json"


# Broad selection of Open Trivia DB categories
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
# DISCORD
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
            f"Discord webhook error {response.status_code}: {response.text}"
        )

    if wait_for_message and response.text:
        return response.json()

    return None


def send_bot_message(content=None, embed=None, allowed_users=None):
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


def edit_webhook_message(message_id, payload):
    url = f"{WEBHOOK_URL}/messages/{message_id}"

    response = requests.patch(
        url,
        json=payload,
        timeout=30,
    )

    if response.status_code not in (200, 204):
        print(
            "Webhook message edit failed:",
            response.status_code,
            response.text,
        )


# ============================================================
# QUESTION SYSTEM
# ============================================================

def question_hash(question):
    return hashlib.sha256(
        question.strip().lower().encode("utf-8")
    ).hexdigest()


def get_random_question():
    used_questions = load_json(USED_FILE, [])

    for attempt in range(10):
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

            correct = html.unescape(item["correct_answer"])

            incorrect = [
                html.unescape(answer)
                for answer in item["incorrect_answers"]
            ]

            answers = incorrect + [correct]
            random.shuffle(answers)

            correct_index = answers.index(correct)

            used_questions.append(q_hash)

            # Keep database reasonably sized
            if len(used_questions) > 5000:
                used_questions = used_questions[-5000:]

            save_json(USED_FILE, used_questions)

            return {
                "question": question,
                "answers": answers,
                "correct_index": correct_index,
                "category": html.unescape(item["category"]),
                "difficulty": item["difficulty"].capitalize(),
                "hash": q_hash,
            }

    raise RuntimeError("Could not find a new question.")


def letter_for_index(index):
    return chr(ord("A") + index)


# ============================================================
# ANSWER PARSING
# ============================================================

def parse_answer(content):
    text = content.strip()

    # Accept:
    # A
    # A.
    # A)
    # Answer A
    # Answer: A

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
    return load_json(LEADERBOARD_FILE, {})


def save_leaderboard(board):
    save_json(LEADERBOARD_FILE, board)


def add_point(board, user):
    user_id = str(user["id"])

    if user_id not in board:
        board[user_id] = {
            "username": user.get("global_name")
            or user.get("username")
            or "Unknown User",
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
        lines.append(
            f"**{position}.** <@{user_id}> • "
            f"**{data['points']} point"
            f"{'s' if data['points'] != 1 else ''}**"
        )

    return "\n".join(lines)


# ============================================================
# QOTD
# ============================================================

def create_question_embed(question_data, countdown_timestamp):
    answers = question_data["answers"]

    choices = "\n".join(
        f"**{letter_for_index(i)}.** {answer}"
        for i, answer in enumerate(answers)
    )

    return {
        "title": "🧠 Question of the Day",
        "description": (
            f"**{question_data['question']}**\n\n"
            f"{choices}\n\n"
            "⏱️ **Time remaining:** "
            f"<t:{countdown_timestamp}:R>\n\n"
            "Reply with **A, B, C, or D** to submit your answer."
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
            "text": "Nickolas Lilly Assistant • Question of the Day"
        },
    }


def create_answer_embed(question_data):
    correct = question_data["answers"][
        question_data["correct_index"]
    ]

    letter = letter_for_index(
        question_data["correct_index"]
    )

    return {
        "title": "💡 Question of the Day Answer",
        "description": (
            f"The correct answer was:\n\n"
            f"**{letter}. {correct}**"
        ),
        "color": 5763719,
        "footer": {
            "text": "Thanks for participating!"
        },
    }


# ============================================================
# MAIN QOTD PROCESS
# ============================================================

def run_qotd():
    print("Starting Question of the Day...")

    rename_webhook()

    question_data = get_random_question()

    now = datetime.now(timezone.utc)
    end_time = now + timedelta(seconds=COUNTDOWN_SECONDS)

    countdown_timestamp = int(end_time.timestamp())

    # Save current question
    current = {
        **question_data,
        "started_at": now.isoformat(),
        "ends_at": end_time.isoformat(),
    }

    save_json(CURRENT_FILE, current)

    # --------------------------------------------------------
    # Send question
    # --------------------------------------------------------

    question_message = send_webhook(
        {
            "username": WEBHOOK_NAME,
            "embeds": [
                create_question_embed(
                    question_data,
                    countdown_timestamp,
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

    current["message_id"] = question_message_id
    save_json(CURRENT_FILE, current)

    print(
        f"Question posted. Message ID: {question_message_id}"
    )

    # --------------------------------------------------------
    # Monitor answers for 10 minutes
    # --------------------------------------------------------

    leaderboard = load_leaderboard()

    already_awarded = set()

    last_message_id = question_message_id

    end_timestamp = time.time() + COUNTDOWN_SECONDS

    print("Monitoring answers for 10 minutes...")

    while time.time() < end_timestamp:

        messages = get_messages_after(last_message_id)

        # Discord returns oldest first when using "after"
        for message in messages:
            last_message_id = message["id"]

            author = message.get("author", {})

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

            # One point per user for this QOTD
            if user_id in already_awarded:
                continue

            already_awarded.add(user_id)

            add_point(
                leaderboard,
                author,
            )

            print(
                f"Correct answer from "
                f"{author.get('username')} ({user_id})"
            )

            # Save immediately in case something fails later
            save_leaderboard(leaderboard)

            # Mention the winner
            send_bot_message(
                content=(
                    f"🎉 <@{user_id}> got it correct! "
                    f"**+1 point!**"
                ),
                allowed_users=[user_id],
            )

        remaining = max(
            0,
            int(end_timestamp - time.time())
        )

        print(
            f"Time remaining: "
            f"{remaining // 60:02d}:{remaining % 60:02d}"
        )

        if remaining <= 0:
            break

        time.sleep(
            min(POLL_INTERVAL, remaining)
        )

    # --------------------------------------------------------
    # Countdown finished
    # --------------------------------------------------------

    print("10 minutes are over.")

    # Edit the original question to show 00:00
    final_embed = create_question_embed(
        question_data,
        int(time.time()),
    )

    final_embed["description"] = (
        f"**{question_data['question']}**\n\n"
        + "\n".join(
            f"**{letter_for_index(i)}.** {answer}"
            for i, answer in enumerate(
                question_data["answers"]
            )
        )
        + "\n\n"
        "⏱️ **Time remaining: 00:00**\n\n"
        "🔒 **Answers are now closed.**"
    )

    edit_webhook_message(
        question_message_id,
        {
            "embeds": [final_embed]
        },
    )

    # --------------------------------------------------------
    # Reveal answer
    # --------------------------------------------------------

    send_bot_message(
        embed=create_answer_embed(question_data)
    )

    # --------------------------------------------------------
    # Leaderboard
    # --------------------------------------------------------

    if already_awarded:
        winners = " ".join(
            f"<@{user_id}>"
            for user_id in already_awarded
        )

        send_bot_message(
            content=(
                f"🏆 **Today's correct answers:**\n"
                f"{winners}\n\n"
                f"Each correct user earned **+1 point**."
            ),
            allowed_users=list(already_awarded),
        )
    else:
        send_bot_message(
            content=(
                "😅 **Nobody got today's question correct.**\n"
                "Better luck on the next Question of the Day!"
            )
        )

    send_bot_message(
        embed={
            "title": "🏆 QOTD Leaderboard",
            "description": leaderboard_text(leaderboard),
            "color": 65413,
            "footer": {
                "text": "Top 10 Question of the Day scores"
            },
        }
    )

    save_leaderboard(leaderboard)

    print("QOTD finished successfully.")


if __name__ == "__main__":
    run_qotd()
