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

# GitHub Actions provides this value.
# If it is missing, the default is 10 minutes.
try:
    DURATION_MINUTES = float(
        os.environ.get("QOTD_DURATION", "10").strip()
    )
except ValueError:
    DURATION_MINUTES = 10

if DURATION_MINUTES <= 0:
    DURATION_MINUTES = 10

COUNTDOWN_SECONDS = int(DURATION_MINUTES * 60)

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

CURRENT_FILE = DATA_DIR / "current_question.json"
USED_FILE = DATA_DIR / "used_questions.json"
LEADERBOARD_FILE = DATA_DIR / "leaderboard.json"


# Open Trivia DB categories
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
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception as error:
        print(f"Could not read {path}: {error}")
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False
        )


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
            json={
                "name": WEBHOOK_NAME
            },
            timeout=20
        )

        if response.status_code not in (200, 204):
            print(
                "Webhook rename failed:",
                response.status_code,
                response.text
            )

    except Exception as error:
        print(
            "Webhook rename error:",
            error
        )


def send_webhook(
    payload,
    wait_for_message=False
):
    url = WEBHOOK_URL

    if wait_for_message:
        separator = "&" if "?" in url else "?"
        url += separator + "wait=true"

    response = requests.post(
        url,
        json=payload,
        timeout=30
    )

    if response.status_code not in (200, 204):
        raise RuntimeError(
            f"Discord webhook error "
            f"{response.status_code}: "
            f"{response.text}"
        )

    if wait_for_message and response.text:
        return response.json()

    return None


def edit_webhook_message(
    message_id,
    payload
):
    try:
        response = requests.patch(
            f"{WEBHOOK_URL}/messages/{message_id}",
            json=payload,
            timeout=30
        )

        if response.status_code not in (200, 204):
            print(
                "Webhook message edit failed:",
                response.status_code,
                response.text
            )

        return response

    except Exception as error:
        print(
            "Webhook message edit error:",
            error
        )

        return None


def send_bot_message(
    content=None,
    embed=None,
    allowed_users=None
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

    try:
        response = requests.post(
            f"{DISCORD_API}/channels/{CHANNEL_ID}/messages",
            headers=bot_headers(),
            json=payload,
            timeout=30
        )

        if response.status_code not in (200, 201):
            print(
                "Bot message failed:",
                response.status_code,
                response.text
            )

        return response

    except Exception as error:
        print(
            "Bot message error:",
            error
        )

        return None


def get_messages_after(message_id):
    try:
        response = requests.get(
            f"{DISCORD_API}/channels/"
            f"{CHANNEL_ID}/messages",
            headers=bot_headers(),
            params={
                "after": message_id,
                "limit": 100
            },
            timeout=30
        )

        if response.status_code != 200:
            print(
                "Message fetch failed:",
                response.status_code,
                response.text
            )
            return []

        messages = response.json()

        # Discord normally returns oldest first
        # for the "after" parameter.
        messages.reverse()

        return messages

    except Exception as error:
        print(
            "Message fetch error:",
            error
        )

        return []


# ============================================================
# QUESTION SYSTEM
# ============================================================

def question_hash(question):
    return hashlib.sha256(
        question.strip()
        .lower()
        .encode("utf-8")
    ).hexdigest()


def get_random_question():
    used_questions = load_json(
        USED_FILE,
        []
    )

    for attempt in range(10):
        category = random.choice(
            CATEGORIES
        )

        print(
            f"Getting questions from "
            f"category {category}..."
        )

        response = requests.get(
            API_URL,
            params={
                "amount": 20,
                "category": category,
                "type": "multiple"
            },
            timeout=30
        )

        response.raise_for_status()

        data = response.json()

        if data.get("response_code") != 0:
            continue

        questions = data.get(
            "results",
            []
        )

        random.shuffle(questions)

        for item in questions:
            question = html.unescape(
                item["question"]
            )

            q_hash = question_hash(
                question
            )

            if q_hash in used_questions:
                continue

            correct = html.unescape(
                item["correct_answer"]
            )

            incorrect = [
                html.unescape(answer)
                for answer in item[
                    "incorrect_answers"
                ]
            ]

            answers = incorrect + [
                correct
            ]

            random.shuffle(answers)

            correct_index = answers.index(
                correct
            )

            used_questions.append(
                q_hash
            )

            # Keep the database from becoming huge.
            if len(used_questions) > 5000:
                used_questions = (
                    used_questions[-5000:]
                )

            save_json(
                USED_FILE,
                used_questions
            )

            return {
                "question": question,
                "answers": answers,
                "correct_index": correct_index,
                "category": html.unescape(
                    item["category"]
                ),
                "difficulty": (
                    item["difficulty"]
                    .capitalize()
                ),
                "hash": q_hash
            }

    raise RuntimeError(
        "Could not find a new question."
    )


def letter_for_index(index):
    return chr(
        ord("A") + index
    )


# ============================================================
# ANSWER PARSING
# ============================================================

def parse_answer(content):
    text = content.strip()

    # Accept:
    #
    # A
    # A.
    # A)
    # Answer A
    # Answer: A
    # answer - A

    match = re.fullmatch(
        r"(?:answer\s*[:\-]?\s*)?"
        r"([ABCD])"
        r"[\.\)]?",
        text,
        re.IGNORECASE
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
        {}
    )


def save_leaderboard(board):
    save_json(
        LEADERBOARD_FILE,
        board
    )


def add_point(
    board,
    user
):
    user_id = str(
        user["id"]
    )

    username = (
        user.get("global_name")
        or user.get("username")
        or "Unknown User"
    )

    if user_id not in board:
        board[user_id] = {
            "username": username,
            "points": 0
        }

    board[user_id]["username"] = username

    board[user_id]["points"] += 1


def leaderboard_text(board):
    if not board:
        return (
            "No points have been earned yet."
        )

    sorted_users = sorted(
        board.items(),
        key=lambda item: item[1]["points"],
        reverse=True
    )

    lines = []

    for position, (
        user_id,
        data
    ) in enumerate(
        sorted_users[:10],
        start=1
    ):
        points = data["points"]

        point_word = (
            "point"
            if points == 1
            else "points"
        )

        lines.append(
            f"**{position}.** "
            f"<@{user_id}> • "
            f"**{points} {point_word}**"
        )

    return "\n".join(lines)


# ============================================================
# EMBEDS
# ============================================================

def build_question_embed(
    question_data,
    remaining_seconds
):
    minutes = remaining_seconds // 60
    seconds = remaining_seconds % 60

    timer = (
        f"{minutes}:"
        f"{seconds:02d}"
    )

    answers = "\n".join(
        f"**{letter_for_index(i)}.** "
        f"{answer}"
        for i, answer in enumerate(
            question_data["answers"]
        )
    )

    return {
        "title": "🧠 Question of the Day",

        "description": (
            f"**{question_data['question']}**"
            f"\n\n"
            f"{answers}"
            f"\n\n"
            f"⏱️ **Time remaining: "
            f"{timer}**"
            f"\n\n"
            f"Reply with **A, B, C, or D** "
            f"to submit your answer."
        ),

        "color": 65413,

        "fields": [
            {
                "name": "📚 Category",
                "value": question_data[
                    "category"
                ],
                "inline": True
            },
            {
                "name": "🎯 Difficulty",
                "value": question_data[
                    "difficulty"
                ],
                "inline": True
            }
        ],

        "footer": {
            "text": (
                "Nickolas Lilly Assistant • "
                "Question of the Day"
            )
        }
    }


def build_closed_embed(
    question_data
):
    answers = "\n".join(
        f"**{letter_for_index(i)}.** "
        f"{answer}"
        for i, answer in enumerate(
            question_data["answers"]
        )
    )

    return {
        "title": "🧠 Question of the Day",

        "description": (
            f"**{question_data['question']}**"
            f"\n\n"
            f"{answers}"
            f"\n\n"
            f"⏱️ **Time remaining: 0:00**"
            f"\n\n"
            f"🔒 **Answers are now closed.**"
        ),

        "color": 65413,

        "fields": [
            {
                "name": "📚 Category",
                "value": question_data[
                    "category"
                ],
                "inline": True
            },
            {
                "name": "🎯 Difficulty",
                "value": question_data[
                    "difficulty"
                ],
                "inline": True
            }
        ],

        "footer": {
            "text": (
                "Nickolas Lilly Assistant • "
                "Question of the Day"
            )
        }
    }


def build_answer_embed(
    question_data
):
    correct = question_data[
        "answers"
    ][
        question_data[
            "correct_index"
        ]
    ]

    letter = letter_for_index(
        question_data[
            "correct_index"
        ]
    )

    return {
        "title": (
            "💡 Question of the Day Answer"
        ),

        "description": (
            "The correct answer was:"
            "\n\n"
            f"**{letter}. {correct}**"
        ),

        "color": 5763719,

        "footer": {
            "text": (
                "Thanks for participating!"
            )
        }
    }


# ============================================================
# MAIN QOTD
# ============================================================

def run_qotd():
    print("=" * 60)
    print("QUESTION OF THE DAY")
    print("=" * 60)

    print(
        f"Duration selected: "
        f"{DURATION_MINUTES} minute(s)"
    )

    print(
        f"Total seconds: "
        f"{COUNTDOWN_SECONDS}"
    )

    rename_webhook()

    # --------------------------------------------------------
    # Get question
    # --------------------------------------------------------

    question_data = (
        get_random_question()
    )

    # --------------------------------------------------------
    # Post question
    # --------------------------------------------------------

    initial_embed = (
        build_question_embed(
            question_data,
            COUNTDOWN_SECONDS
        )
    )

    question_message = send_webhook(
        {
            "username": WEBHOOK_NAME,
            "embeds": [
                initial_embed
            ]
        },
        wait_for_message=True
    )

    if not question_message:
        raise RuntimeError(
            "Discord did not return "
            "the QOTD message."
        )

    question_message_id = (
        question_message["id"]
    )

    print(
        f"QOTD message ID: "
        f"{question_message_id}"
    )

    # Save current question
    save_json(
        CURRENT_FILE,
        {
            **question_data,
            "message_id": (
                question_message_id
            ),
            "duration_minutes": (
                DURATION_MINUTES
            )
        }
    )

    # --------------------------------------------------------
    # Start countdown
    # --------------------------------------------------------

    start_time = time.monotonic()

    end_time = (
        start_time
        + COUNTDOWN_SECONDS
    )

    last_message_id = (
        question_message_id
    )

    leaderboard = (
        load_leaderboard()
    )

    already_awarded = set()

    print(
        "Countdown started."
    )

    print(
        "The Discord message will "
        "update every second."
    )

    # --------------------------------------------------------
    # Countdown loop
    # --------------------------------------------------------

    while True:
        current_time = (
            time.monotonic()
        )

        remaining = max(
            0,
            int(
                end_time
                - current_time
            )
        )

        minutes = (
            remaining // 60
        )

        seconds = (
            remaining % 60
        )

        timer = (
            f"{minutes}:"
            f"{seconds:02d}"
        )

        print(
            f"Time remaining: {timer}"
        )

        # ----------------------------------------------------
        # Update Discord countdown
        # ----------------------------------------------------

        edit_webhook_message(
            question_message_id,
            {
                "embeds": [
                    build_question_embed(
                        question_data,
                        remaining
                    )
                ]
            }
        )

        # ----------------------------------------------------
        # Check new Discord messages
        # ----------------------------------------------------

        messages = (
            get_messages_after(
                last_message_id
            )
        )

        for message in messages:
            last_message_id = (
                message["id"]
            )

            author = message.get(
                "author",
                {}
            )

            # Ignore bot messages
            if author.get("bot"):
                continue

            content = message.get(
                "content",
                ""
            )

            answer = parse_answer(
                content
            )

            if not answer:
                continue

            correct_letter = (
                letter_for_index(
                    question_data[
                        "correct_index"
                    ]
                )
            )

            if answer != correct_letter:
                continue

            user_id = str(
                author["id"]
            )

            # Only one point per person
            # for this question.
            if user_id in (
                already_awarded
            ):
                continue

            already_awarded.add(
                user_id
            )

            add_point(
                leaderboard,
                author
            )

            save_leaderboard(
                leaderboard
            )

            username = (
                author.get(
                    "global_name"
                )
                or author.get(
                    "username"
                )
                or "Unknown User"
            )

            print(
                f"Correct answer from "
                f"{username} "
                f"({user_id})"
            )

            # Immediately announce
            # that they earned a point.
            send_bot_message(
                content=(
                    f"🎉 <@{user_id}> "
                    f"got it correct! "
                    f"**+1 point!**"
                ),
                allowed_users=[
                    user_id
                ]
            )

        # ----------------------------------------------------
        # Check timer
        # ----------------------------------------------------

        if remaining <= 0:
            break

        # Wait one second
        time.sleep(1)

    # --------------------------------------------------------
    # Force final 0:00 state
    # --------------------------------------------------------

    print(
        "Countdown reached 0:00."
    )

    edit_webhook_message(
        question_message_id,
        {
            "embeds": [
                build_closed_embed(
                    question_data
                )
            ]
        }
    )

    # --------------------------------------------------------
    # Reveal answer
    # --------------------------------------------------------

    print(
        "Sending correct answer..."
    )

    send_bot_message(
        embed=build_answer_embed(
            question_data
        )
    )

    # --------------------------------------------------------
    # Announce winners
    # --------------------------------------------------------

    if already_awarded:
        mentions = " ".join(
            f"<@{user_id}>"
            for user_id in (
                already_awarded
            )
        )

        send_bot_message(
            content=(
                "🏆 **Today's correct "
                "answers:**\n"
                f"{mentions}\n\n"
                "Each correct user earned "
                "**+1 point**."
            ),
            allowed_users=list(
                already_awarded
            )
        )

    else:
        send_bot_message(
            content=(
                "😅 **Nobody got today's "
                "question correct.**\n"
                "Better luck next time!"
            )
        )

    # --------------------------------------------------------
    # Leaderboard
    # --------------------------------------------------------

    print(
        "Sending leaderboard..."
    )

    send_bot_message(
        embed={
            "title": (
                "🏆 QOTD Leaderboard"
            ),

            "description": (
                leaderboard_text(
                    leaderboard
                )
            ),

            "color": 65413,

            "footer": {
                "text": (
                    "Top 10 Question of "
                    "the Day scores"
                )
            }
        }
    )

    save_leaderboard(
        leaderboard
    )

    print("=" * 60)
    print("QOTD COMPLETED")
    print("=" * 60)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    run_qotd()
