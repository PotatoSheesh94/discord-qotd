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
MAX_ATTEMPTS = 4

# Gemini connection/read timeout.
#
# 15 seconds = connection timeout
# 90 seconds = maximum time waiting for Gemini
#
# This prevents the previous 30-second ReadTimeout problem.
GEMINI_TIMEOUT = (15, 90)

# Discord timeout
DISCORD_TIMEOUT = (10, 30)


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
        with open(
            HISTORY_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        if not isinstance(data, list):
            return []

        converted = []

        for item in data:

            # New format
            if isinstance(item, dict):

                question = item.get(
                    "question",
                    ""
                ).strip()

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

        return converted[-MAX_HISTORY:]

    except (
        json.JSONDecodeError,
        OSError
    ):

        print(
            "Could not read question history. "
            "Starting with empty history."
        )

        return []


def save_history(history):

    os.makedirs(
        "data",
        exist_ok=True
    )

    history = history[-MAX_HISTORY:]

    with open(
        HISTORY_FILE,
        "w",
        encoding="utf-8"
    ) as file:

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

            question = item.get(
                "question",
                ""
            )

        elif isinstance(item, str):

            question = item

        else:

            question = ""

        if question:
            recent_text.append(
                f"- {question}"
            )

    if recent_text:

        history_text = "\n".join(
            recent_text
        )

    else:

        history_text = (
            "(No previous questions.)"
        )

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
        "https://generativelanguage.googleapis.com/"
        "v1beta/models/"
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

    last_error = None

    # ========================================================
    # GEMINI RETRY LOOP
    # ========================================================

    for attempt in range(
        1,
        MAX_ATTEMPTS + 1
    ):

        print(
            f"Gemini request "
            f"attempt {attempt}/{MAX_ATTEMPTS}..."
        )

        try:

            response = requests.post(
                url,
                params={
                    "key": GEMINI_API_KEY
                },
                json=payload,
                timeout=GEMINI_TIMEOUT
            )

            # =================================================
            # RATE LIMIT / QUOTA
            # =================================================

            if response.status_code == 429:

                print(
                    "Gemini API returned HTTP 429."
                )

                try:

                    error_data = response.json()

                    print(
                        json.dumps(
                            error_data,
                            indent=2
                        )
                    )

                except Exception:

                    print(
                        response.text
                    )

                last_error = RuntimeError(
                    "Gemini API quota/rate limit."
                )

                if attempt < MAX_ATTEMPTS:

                    wait_time = (
                        5 * attempt
                    )

                    print(
                        f"Waiting {wait_time} "
                        "seconds before retrying..."
                    )

                    time.sleep(
                        wait_time
                    )

                    continue

                raise last_error

            # =================================================
            # TEMPORARY GOOGLE SERVER ERRORS
            # =================================================

            if response.status_code in (
                500,
                502,
                503,
                504
            ):

                print(
                    "Gemini temporary server error: "
                    f"HTTP {response.status_code}"
                )

                last_error = RuntimeError(
                    "Gemini temporary server error: "
                    f"{response.status_code}"
                )

                if attempt < MAX_ATTEMPTS:

                    wait_time = (
                        5 * attempt
                    )

                    print(
                        f"Waiting {wait_time} "
                        "seconds before retrying..."
                    )

                    time.sleep(
                        wait_time
                    )

                    continue

                raise last_error

            # =================================================
            # OTHER API ERRORS
            # =================================================

            if response.status_code != 200:

                print(
                    "Gemini API response:"
                )

                print(
                    response.text
                )

                response.raise_for_status()

            # =================================================
            # PARSE RESPONSE
            # =================================================

            data = response.json()

            try:

                candidates = data[
                    "candidates"
                ]

                if not candidates:

                    raise RuntimeError(
                        "Gemini returned no candidates."
                    )

                parts = candidates[0][
                    "content"
                ][
                    "parts"
                ]

                if not parts:

                    raise RuntimeError(
                        "Gemini returned no content."
                    )

                question = parts[0][
                    "text"
                ]

            except (
                KeyError,
                IndexError,
                TypeError
            ):

                print(
                    "Unexpected Gemini response:"
                )

                print(
                    json.dumps(
                        data,
                        indent=2
                    )
                )

                raise RuntimeError(
                    "Gemini returned an invalid response."
                )

            # =================================================
            # CLEAN QUESTION
            # =================================================

            question = question.strip()

            # Remove accidental quotation marks.
            question = question.strip('"')
            question = question.strip("'")
            question = question.strip()

            # Remove accidental markdown code blocks.
            question = question.replace(
                "```",
                ""
            ).strip()

            # Remove accidental "Question:" prefix.
            if question.lower().startswith(
                "question:"
            ):

                question = question[
                    9:
                ].strip()

            print(
                f"Gemini generated: {question}"
            )

            return question

        # =====================================================
        # TIMEOUT
        # =====================================================

        except requests.exceptions.Timeout as error:

            last_error = error

            print(
                "Gemini request timed out."
            )

            print(
                f"Details: {error}"
            )

            if attempt < MAX_ATTEMPTS:

                wait_time = (
                    3 * attempt
                )

                print(
                    f"Waiting {wait_time} "
                    "seconds before retrying..."
                )

                time.sleep(
                    wait_time
                )

                continue

            break

        # =====================================================
        # CONNECTION ERROR
        # =====================================================

        except requests.exceptions.ConnectionError as error:

            last_error = error

            print(
                "Gemini connection error."
            )

            print(
                f"Details: {error}"
            )

            if attempt < MAX_ATTEMPTS:

                wait_time = (
                    3 * attempt
                )

                print(
                    f"Waiting {wait_time} "
                    "seconds before retrying..."
                )

                time.sleep(
                    wait_time
                )

                continue

            break

        # =====================================================
        # REQUEST ERROR
        # =====================================================

        except requests.exceptions.RequestException as error:

            last_error = error

            print(
                "Gemini request error."
            )

            print(
                f"Details: {error}"
            )

            if attempt < MAX_ATTEMPTS:

                wait_time = (
                    3 * attempt
                )

                print(
                    f"Waiting {wait_time} "
                    "seconds before retrying..."
                )

                time.sleep(
                    wait_time
                )

                continue

            break

        # =====================================================
        # OTHER GENERATION ERRORS
        # =====================================================

        except RuntimeError as error:

            last_error = error

            print(
                f"Generation error: {error}"
            )

            if attempt < MAX_ATTEMPTS:

                wait_time = (
                    3 * attempt
                )

                print(
                    f"Waiting {wait_time} "
                    "seconds before retrying..."
                )

                time.sleep(
                    wait_time
                )

                continue

            break

    raise RuntimeError(
        "Gemini failed after "
        f"{MAX_ATTEMPTS} attempts. "
        f"Last error: {last_error}"
    )


# =========================
# VALIDATE QUESTION
# =========================

def is_valid_question(
    question,
    history
):

    if not question:

        print(
            "Rejected: empty question."
        )

        return False

    # Prevent tiny incomplete responses.
    if len(question) < 15:

        print(
            "Rejected: question is too short."
        )

        return False

    # Prevent excessively long responses.
    if len(question) > 300:

        print(
            "Rejected: question is too long."
        )

        return False

    # Must contain exactly one question mark.
    if question.count("?") != 1:

        print(
            "Rejected: invalid question mark count."
        )

        return False

    # Must end with a question mark.
    if not question.endswith("?"):

        print(
            "Rejected: question does not "
            "end with '?'."
        )

        return False

    # ========================================================
    # BLOCK MULTIPLE CHOICE / TRIVIA
    # ========================================================

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

    lower_question = (
        question.lower()
    )

    for pattern in blocked_patterns:

        if pattern.lower() in lower_question:

            print(
                "Rejected: blocked pattern "
                f"'{pattern}'."
            )

            return False

    # ========================================================
    # BLOCK YES/NO QUESTIONS
    # ========================================================

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

    if lower_question.startswith(
        yes_no_starts
    ):

        print(
            "Rejected: yes/no style question."
        )

        return False

    # ========================================================
    # DUPLICATE CHECK
    # ========================================================

    current_hash = question_hash(
        question
    )

    for item in history:

        if isinstance(item, dict):

            if item.get(
                "hash"
            ) == current_hash:

                print(
                    "Rejected: duplicate question."
                )

                return False

        elif isinstance(item, str):

            if question_hash(
                item
            ) == current_hash:

                print(
                    "Rejected: duplicate question."
                )

                return False

    return True


# =========================
# GET NEW QUESTION
# =========================

def get_new_question(history):

    for attempt in range(
        1,
        MAX_ATTEMPTS + 1
    ):

        print(
            f"Generating question, "
            f"attempt {attempt}/{MAX_ATTEMPTS}..."
        )

        try:

            question = generate_question(
                history
            )

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

        except (
            RuntimeError,
            requests.exceptions.RequestException
        ) as error:

            print(
                f"Generation error: {error}"
            )

            if attempt < MAX_ATTEMPTS:

                print(
                    "Waiting 5 seconds "
                    "before retrying..."
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
    ).strftime(
        "%B %d, %Y"
    )

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
                "Nickolas Lilly Assistant • "
                f"{today}"
            )
        }
    }

    payload = {
        "username": (
            "Nickolas Lilly Assistant"
        ),

        "embeds": [
            embed
        ],

        "allowed_mentions": {
            "parse": []
        }
    }

    print(
        "Sending question to Discord..."
    )

    try:

        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json=payload,
            timeout=DISCORD_TIMEOUT
        )

        # =====================================================
        # DISCORD RATE LIMIT
        # =====================================================

        if response.status_code == 429:

            print(
                "Discord webhook was rate limited."
            )

            retry_after = 5

            try:

                data = response.json()

                retry_after = float(
                    data.get(
                        "retry_after",
                        5
                    )
                )

            except Exception:
                pass

            print(
                f"Waiting {retry_after} seconds..."
            )

            time.sleep(
                retry_after
            )

            response = requests.post(
                DISCORD_WEBHOOK_URL,
                json=payload,
                timeout=DISCORD_TIMEOUT
            )

        # =====================================================
        # DISCORD ERROR
        # =====================================================

        if response.status_code not in (
            200,
            204
        ):

            print(
                "Discord response:"
            )

            print(
                response.text
            )

            response.raise_for_status()

        print(
            "Question successfully "
            "posted to Discord."
        )

    except requests.exceptions.Timeout as error:

        print(
            f"Discord webhook timed out: {error}"
        )

        raise

    except requests.exceptions.RequestException as error:

        print(
            f"Discord webhook failed: {error}"
        )

        raise


# =========================
# MAIN
# =========================

def main():

    print(
        "Starting Question of the Day..."
    )

    history = load_history()

    print(
        f"Loaded {len(history)} "
        "previous questions."
    )

    # ========================================================
    # GENERATE
    # ========================================================

    question = get_new_question(
        history
    )

    # ========================================================
    # DISCORD
    # ========================================================

    post_to_discord(
        question
    )

    # ========================================================
    # SAVE HISTORY
    #
    # Only save after Discord successfully
    # receives the question.
    # ========================================================

    history.append({
        "question": question,

        "hash": question_hash(
            question
        ),

        "date": datetime.now(
            timezone.utc
        ).strftime(
            "%Y-%m-%d"
        )
    })

    history = history[
        -MAX_HISTORY:
    ]

    save_history(
        history
    )

    print(
        "Question history updated."
    )

    print(
        "QOTD completed successfully."
    )


# =========================
# ENTRY POINT
# =========================

if __name__ == "__main__":
    main()
