import os
import json
import hashlib
import time
from datetime import datetime, timezone

import requests


# =========================
# CONFIGURATION
# =========================

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

HISTORY_FILE = "data/used_questions.json"

# Keep up to 500 previous questions.
MAX_HISTORY = 500

# Gemini model
GEMINI_MODEL = "gemini-3.5-flash-lite"

# Maximum Gemini attempts for one QOTD
MAX_ATTEMPTS = 2


# =========================
# CHECK CONFIGURATION
# =========================

if not DISCORD_WEBHOOK_URL:
    raise RuntimeError("Missing DISCORD_WEBHOOK_URL secret.")

if not GEMINI_API_KEY:
    raise RuntimeError("Missing GEMINI_API_KEY secret.")


# =========================
# QUESTION HISTORY
# =========================

def question_hash(question):
    normalized = " ".join(question.lower().split())

    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()


def load_history():
    os.makedirs("data", exist_ok=True)

    if not os.path.exists(HISTORY_FILE):
        return []

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, list):
            return []

        converted = []

        for item in data:

            # New format
            if isinstance(item, dict):
                question = item.get("question", "").strip()

                if question:
                    converted.append({
                        "question": question,
                        "hash": item.get(
                            "hash",
                            question_hash(question)
                        ),
                        "date": item.get(
                            "date",
                            "unknown"
                        )
                    })

            # Old format
            elif isinstance(item, str):
                question = item.strip()

                if question:
                    converted.append({
                        "question": question,
                        "hash": question_hash(question),
                        "date": "unknown"
                    })

        return converted

    except (json.JSONDecodeError, OSError):
        print("Could not read question history. Starting with empty history.")
        return []


def save_history(history):
    os.makedirs("data", exist_ok=True)

    with open(HISTORY_FILE, "w", encoding="utf-8") as file:
        json.dump(
            history,
            file,
            indent=2,
            ensure_ascii=False
        )


# =========================
# GEMINI QUESTION GENERATION
# =========================

def generate_question(previous_questions):

    recent_questions = previous_questions[-100:]

    recent_text = []

    for item in recent_questions:

        if isinstance(item, dict):
            question = item.get("question", "")

        elif isinstance(item, str):
            question = item

        else:
            question = ""

        if question:
            recent_text.append(f"- {question}")

    if recent_text:
        history_text = "\n".join(recent_text)
    else:
        history_text = "(No previous questions.)"

    prompt = f"""
Generate ONE original Question of the Day for a friendly creative Discord community.

The community includes people interested in:

- voice acting
- singing
- writing
- art
- animation
- editing
- music
- gaming
- creativity
- friendships
- community

The question should encourage people to actually discuss their answer.

Good topics include:

- opinions
- personal preferences
- everyday experiences
- creative interests
- funny situations
- hypothetical situations
- things people would choose or change
- things people enjoy
- community discussions

IMPORTANT:

The question MUST be open-ended.

It MUST NOT be trivia.

It MUST NOT have a correct answer.

It MUST NOT be multiple choice.

It MUST NOT contain A/B/C/D options.

It MUST NOT be a yes/no question.

It MUST NOT ask for sensitive personal information.

It MUST be natural and casual.

It MUST be between 10 and 30 words.

It MUST end with a question mark.

Do not repeatedly use "What is your favorite..."

Return ONLY one complete question.

Do not include:
- explanations
- headings
- quotation marks
- bullet points
- answer choices
- extra text

Avoid repeating or closely rephrasing these previous questions:

{history_text}
"""

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent"
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 1.0,
            "maxOutputTokens": 50
        }
    }

    response = requests.post(
        url,
        params={
            "key": GEMINI_API_KEY
        },
        json=payload,
        timeout=30
    )

    # =========================
    # RATE LIMIT
    # =========================

    if response.status_code == 429:

        print("Gemini API quota/rate limit reached.")

        try:
            error_data = response.json()
            print(json.dumps(
                error_data,
                indent=2
            ))
        except Exception:
            print(response.text)

        raise RuntimeError(
            "Gemini API quota was exceeded. "
            "Please wait for the quota to reset."
        )

    # =========================
    # OTHER API ERRORS
    # =========================

    if response.status_code != 200:

        print("Gemini API response:")
        print(response.text)

        response.raise_for_status()

    data = response.json()

    try:
        candidates = data["candidates"]

        if not candidates:
            raise RuntimeError(
                "Gemini returned no candidates."
            )

        parts = candidates[0]["content"]["parts"]

        if not parts:
            raise RuntimeError(
                "Gemini returned no content."
            )

        question = parts[0]["text"]

    except (KeyError, IndexError, TypeError):
        print("Unexpected Gemini response:")
        print(json.dumps(
            data,
            indent=2
        ))

        raise RuntimeError(
            "Gemini returned an invalid response."
        )

    question = question.strip()

    # Remove accidental quotation marks.
    question = question.strip('"')
    question = question.strip("'")
    question = question.strip()

    # Remove accidental markdown code blocks.
    question = question.replace("```", "").strip()

    # Remove accidental "Question:" prefix.
    if question.lower().startswith("question:"):
        question = question[9:].strip()

    return question


# =========================
# VALIDATE QUESTION
# =========================

def is_valid_question(question, history):

    if not question:
        print("Rejected: empty question.")
        return False

    # Prevent tiny incomplete responses such as "If"
    if len(question) < 15:
        print("Rejected: question is too short.")
        return False

    # Prevent excessively long responses.
    if len(question) > 300:
        print("Rejected: question is too long.")
        return False

    # Must contain exactly one question mark.
    if question.count("?") != 1:
        print("Rejected: invalid question mark count.")
        return False

    # Must end with a question mark.
    if not question.endswith("?"):
        print("Rejected: question does not end with '?'.")
        return False

    # Reject obvious multiple-choice formatting.
    blocked_patterns = [
        "A)",
        "B)",
        "C)",
        "D)",
        "A.",
        "B.",
        "C.",
        "D.",
        "1.",
        "2.",
        "3.",
        "4.",
        "multiple choice",
        "correct answer",
        "trivia",
        "quiz"
    ]

    lower_question = question.lower()

    for pattern in blocked_patterns:

        if pattern.lower() in lower_question:
            print(
                f"Rejected: blocked pattern '{pattern}'."
            )

            return False

    # Reject obvious yes/no questions.
    yes_no_starts = (
        "do you ",
        "does ",
        "did you ",
        "would you ",
        "could you ",
        "can you ",
        "will you ",
        "is your ",
        "are you ",
        "have you "
    )

    if lower_question.startswith(yes_no_starts):
        print("Rejected: yes/no style question.")
        return False

    # Check for exact duplicate.
    current_hash = question_hash(question)

    for item in history:

        if isinstance(item, dict):

            if item.get("hash") == current_hash:
                print("Rejected: duplicate question.")
                return False

        elif isinstance(item, str):

            if question_hash(item) == current_hash:
                print("Rejected: duplicate question.")
                return False

    return True


# =========================
# GET NEW QUESTION
# =========================

def get_new_question(history):

    for attempt in range(1, MAX_ATTEMPTS + 1):

        print(
            f"Generating question, "
            f"attempt {attempt}/{MAX_ATTEMPTS}..."
        )

        try:

            question = generate_question(history)

            print(
                f"Generated: {question}"
            )

            if is_valid_question(
                question,
                history
            ):
                return question

            print(
                "Question failed validation."
            )

        except RuntimeError as error:

            print(
                f"Generation error: {error}"
            )

            # Don't immediately spam the API.
            if attempt < MAX_ATTEMPTS:
                print(
                    "Waiting 5 seconds before retrying..."
                )

                time.sleep(5)

    raise RuntimeError(
        "Could not generate a valid QOTD."
    )


# =========================
# DISCORD WEBHOOK
# =========================

def post_to_discord(question):

    today = datetime.now(
        timezone.utc
    ).strftime("%B %d, %Y")

    embed = {
        "title": "💭 Question of the Day",

        "description": (
            f"**{question}**"
            "\n\n"
            "💬 Share your thoughts below "
            "and see what everyone else thinks!"
        ),

        "color": 65413,

        "footer": {
            "text": (
                f"Nickolas Lilly Assistant • "
                f"{today}"
            )
        }
    }

    payload = {
        "username": "Nickolas Lilly Assistant",

        "embeds": [
            embed
        ],

        "allowed_mentions": {
            "parse": []
        }
    }

    response = requests.post(
        DISCORD_WEBHOOK_URL,
        json=payload,
        timeout=30
    )

    if response.status_code not in (200, 204):

        print("Discord response:")
        print(response.text)

        response.raise_for_status()

    print(
        "Question successfully posted to Discord."
    )


# =========================
# MAIN
# =========================

def main():

    print(
        "Starting Question of the Day..."
    )

    history = load_history()

    print(
        f"Loaded {len(history)} previous questions."
    )

    question = get_new_question(
        history
    )

    post_to_discord(
        question
    )

    # Only save the question after
    # Discord successfully receives it.
    history.append({
        "question": question,

        "hash": question_hash(
            question
        ),

        "date": datetime.now(
            timezone.utc
        ).strftime("%Y-%m-%d")
    })

    history = history[-MAX_HISTORY:]

    save_history(
        history
    )

    print(
        "Question history updated."
    )

    print(
        "QOTD completed successfully."
    )


if __name__ == "__main__":
    main()
