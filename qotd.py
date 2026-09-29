import os
import json
import hashlib
from datetime import datetime, timezone

import requests


# =========================
# CONFIGURATION
# =========================

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

HISTORY_FILE = "data/used_questions.json"

# Keep the most recent questions.
MAX_HISTORY = 500

# Gemini model with a current free API tier.
GEMINI_MODEL = "gemini-3-flash-preview"


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

def load_history():
    os.makedirs("data", exist_ok=True)

    if not os.path.exists(HISTORY_FILE):
        return []

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, list):
            return data

    except (json.JSONDecodeError, OSError):
        pass

    return []


def save_history(history):
    os.makedirs("data", exist_ok=True)

    with open(HISTORY_FILE, "w", encoding="utf-8") as file:
        json.dump(history, file, indent=2, ensure_ascii=False)


def question_hash(question):
    normalized = " ".join(question.lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


# =========================
# GEMINI
# =========================

def generate_question(previous_questions):
    recent_questions = previous_questions[-100:]

    history_text = "\n".join(
        f"- {item.get('question', '')}"
        for item in recent_questions
        if item.get("question")
    )

    prompt = f"""
Generate ONE original Question of the Day for a friendly creative Discord community.

The community is interested in:
- voice acting
- singing
- writing
- art
- animation
- editing
- music
- gaming
- creativity
- friendships and community

The question must:

- Be open-ended.
- Encourage people to explain their answer.
- Be something people can discuss with each other.
- Ask about opinions, experiences, preferences, feelings, creativity, or hypothetical situations.
- Be interesting enough to start a conversation.
- Sound natural and casual.
- Be appropriate for a general Discord community.
- Be understandable without additional context.

Do NOT:

- Make it trivia.
- Ask for a factual answer.
- Give multiple-choice answers.
- Include A/B/C/D choices.
- Ask for a correct answer.
- Use a countdown or game mechanic.
- Ask for sensitive personal information.
- Make it overly serious or depressing.
- Start with "What is your favorite..." every time.
- Repeat or closely imitate previous questions.

Return ONLY the question itself.

Previous questions to avoid repeating:

{history_text}
"""

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
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
            "maxOutputTokens": 100
        }
    }

    response = requests.post(
        url,
        json=payload,
        timeout=30
    )

    if response.status_code != 200:
        print("Gemini API response:")
        print(response.text)
        response.raise_for_status()

    data = response.json()

    try:
        question = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("Gemini returned an invalid response.")

    question = question.strip()

    # Remove accidental quotation marks.
    question = question.strip('"').strip("'").strip()

    # Remove accidental markdown.
    if question.startswith("```"):
        question = question.replace("```", "").strip()

    return question


# =========================
# VALIDATION
# =========================

def is_valid_question(question, history):
    if not question:
        return False

    if len(question) < 15:
        return False

    if len(question) > 500:
        return False

    # We only want one question.
    if question.count("?") != 1:
        return False

    # Reject obvious multiple-choice output.
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
    ]

    for pattern in blocked_patterns:
        if pattern in question:
            return False

    current_hash = question_hash(question)

    for item in history:
        if item.get("hash") == current_hash:
            return False

    return True


# =========================
# GENERATE A UNIQUE QUESTION
# =========================

def get_new_question(history):
    for attempt in range(5):
        print(f"Generating question, attempt {attempt + 1}/5...")

        question = generate_question(history)

        print(f"Generated: {question}")

        if is_valid_question(question, history):
            return question

        print("Question failed validation. Trying again...")

    raise RuntimeError(
        "Could not generate a valid unique question after 5 attempts."
    )


# =========================
# DISCORD
# =========================

def post_to_discord(question):
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")

    embed = {
        "title": "💭 Question of the Day",
        "description": f"**{question}**\n\n💬 Share your thoughts below and see what everyone else thinks!",
        "color": 65413,
        "footer": {
            "text": f"Daily Question • {today}"
        }
    }

    payload = {
        "username": "Nickolas Lilly Assistant",
        "embeds": [embed]
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

    print("Question successfully posted to Discord.")


# =========================
# MAIN
# =========================

def main():
    print("Starting Question of the Day...")

    history = load_history()

    question = get_new_question(history)

    post_to_discord(question)

    # Save the question only after Discord successfully receives it.
    history.append({
        "question": question,
        "hash": question_hash(question),
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d")
    })

    # Keep the file from becoming unnecessarily large.
    history = history[-MAX_HISTORY:]

    save_history(history)

    print("Question history updated.")
    print("QOTD completed successfully.")


if __name__ == "__main__":
    main()
