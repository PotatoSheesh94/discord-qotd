import os
import json
import random
import hashlib
from pathlib import Path

import requests


# ============================================================
# CONFIGURATION
# ============================================================

WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]

WEBHOOK_NAME = "Nickolas Lilly Assistant"

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

USED_FILE = DATA_DIR / "used_questions.json"


# ============================================================
# QUESTION BANK
# ============================================================

QUESTIONS = [

    # --------------------------------------------------------
    # GENERAL / PERSONAL
    # --------------------------------------------------------

    "What's something small that always makes your day better?",

    "What's something you could talk about for hours without getting bored?",

    "If you could instantly learn one new skill, what would you choose?",

    "What's something you wish more people understood about you?",

    "What's one thing you're looking forward to right now?",

    "What's something you've recently discovered that you really like?",

    "What's one thing you would like to improve about yourself?",

    "What's something you used to dislike but now enjoy?",

    "What's something you think everyone should experience at least once?",

    "What's something that can instantly put you in a better mood?",

    "What's one thing you would never get tired of doing?",

    "What's something you wish you had more time for?",

    "What's one piece of advice that has stayed with you?",

    "What's something you are proud of accomplishing?",

    "What's something you want to try someday but haven't had the chance to?",


    # --------------------------------------------------------
    # HYPOTHETICAL
    # --------------------------------------------------------

    "If you could live anywhere in the world for one year, where would you go?",

    "If you suddenly had an entire week with no responsibilities, how would you spend it?",

    "If you could have any fictional character as a friend, who would you choose?",

    "If you could instantly become amazing at one creative skill, what would it be?",

    "If you could relive one day from your past, which day would you choose?",

    "If you could create your own holiday, what would it celebrate?",

    "If you could have any animal as a companion, what would you choose?",

    "If you could wake up tomorrow with one new talent, what would it be?",

    "If you could visit any fictional world, which one would you visit?",

    "If you could have unlimited money for one day but couldn't keep it, what would you do with it?",

    "If you could instantly understand one language, which language would you choose?",

    "If you could switch lives with any fictional character for one day, who would you pick?",

    "If you could design your dream room, what would you put in it?",

    "If you could create your own video game, what would it be about?",

    "If you could spend one day doing anything you wanted with no consequences, what would you do?",


    # --------------------------------------------------------
    # VOICE ACTING
    # --------------------------------------------------------

    "If you could voice any fictional character, who would you choose?",

    "What's your favorite type of character to voice?",

    "What makes a voice acting performance memorable to you?",

    "What's a voice acting skill you'd like to improve?",

    "If you could work on any animated movie or series, what would you want to work on?",

    "What's more important for a voice actor: emotion, character voice, or timing?",

    "Have you ever heard a voice actor who completely changed how you saw a character?",

    "What kind of character would be the most fun for you to voice?",

    "Would you rather voice the hero, villain, or comic relief character?",

    "If you created your own character, what would their voice sound like?",


    # --------------------------------------------------------
    # ART
    # --------------------------------------------------------

    "What kind of art do you enjoy making the most?",

    "What usually inspires you to create something?",

    "What's an art style you'd like to try?",

    "Do you prefer drawing characters, environments, or objects?",

    "What's something you've always wanted to draw but haven't yet?",

    "What makes artwork stand out to you?",

    "Do you prefer creating art digitally or traditionally?",

    "What's one artist or art style that inspires you?",

    "If you could instantly master one art technique, which would it be?",

    "What is your favorite part of the creative process?",


    # --------------------------------------------------------
    # WRITING
    # --------------------------------------------------------

    "What's your favorite type of story to write?",

    "What makes a character feel realistic to you?",

    "Would you rather write a hero, villain, or morally gray character?",

    "What's more important in a story: characters, worldbuilding, or plot?",

    "What's a story idea you've always wanted to write?",

    "What kind of ending do you enjoy most?",

    "What's one writing skill you'd like to improve?",

    "Do you prefer writing short stories or long stories?",

    "What makes you want to keep reading a story?",

    "If you could create a fictional world, what would it be like?",


    # --------------------------------------------------------
    # MUSIC
    # --------------------------------------------------------

    "What song can you listen to over and over without getting tired of it?",

    "What kind of music do you usually listen to when you're relaxing?",

    "What's a song that brings back a specific memory for you?",

    "If you could meet any musician, who would you want to meet?",

    "What kind of music helps you concentrate?",

    "What's a music genre you'd like to explore more?",

    "Do you prefer listening to music while working or in complete silence?",

    "What's one song you think everyone should hear at least once?",

    "If you could create a song with any artist, who would you choose?",

    "What makes a song memorable to you?",


    # --------------------------------------------------------
    # GAMING
    # --------------------------------------------------------

    "What's a game you could play for hundreds of hours?",

    "What's your favorite type of video game?",

    "What's a game you wish you could experience again for the first time?",

    "What's the most memorable gaming moment you've had?",

    "Would you rather play solo or with friends?",

    "What's one game you think deserves more attention?",

    "If you could create your own game, what would it be like?",

    "What's more important to you in a game: story, gameplay, graphics, or music?",

    "What's a game character you really like?",

    "What's one gaming feature you wish more games had?",


    # --------------------------------------------------------
    # COMMUNITY
    # --------------------------------------------------------

    "What's your favorite thing about being part of a creative community?",

    "What would make a Discord server feel more welcoming to you?",

    "What's something you'd like to see more of in this community?",

    "What's your favorite way to meet new people online?",

    "What's something that makes you want to stay in an online community?",

    "What kind of community event would you enjoy joining?",

    "Would you rather join a voice acting event, art event, writing event, or gaming event?",

    "What's one thing that can make an online conversation more fun?",

    "What's something you think every creative community should have?",

    "What's your favorite way to show support for another creator?",


    # --------------------------------------------------------
    # FUN / RANDOM
    # --------------------------------------------------------

    "What's the weirdest food combination you actually enjoy?",

    "What's a completely random fact you know?",

    "What's something you find funny that probably shouldn't be that funny?",

    "What's the most random thing you've ever become interested in?",

    "What's a useless skill you're surprisingly good at?",

    "What's something you would never want to live without?",

    "What's the strangest dream you remember having?",

    "What's a random thing that annoys you more than it probably should?",

    "What's something you think is overrated?",

    "What's something you think is underrated?",

    "If your life had a soundtrack, what kind of music would be playing?",

    "What's the first thing you'd buy if someone gave you $1,000?",

    "What's your most unusual hobby?",

    "What's a fictional world you absolutely would not want to live in?",

    "What's the funniest username you've ever seen?",

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
# QUESTION SELECTION
# ============================================================

def question_hash(question):
    return hashlib.sha256(
        question.strip().lower().encode("utf-8")
    ).hexdigest()


def get_question():
    used_questions = load_json(
        USED_FILE,
        []
    )

    available_questions = [
        question
        for question in QUESTIONS
        if question_hash(question)
        not in used_questions
    ]

    # If every question has been used,
    # start a fresh cycle.
    if not available_questions:
        print("All questions have been used.")
        print("Starting a new question cycle.")

        used_questions = []

        available_questions = QUESTIONS.copy()

    question = random.choice(
        available_questions
    )

    question_id = question_hash(
        question
    )

    used_questions.append(
        question_id
    )

    save_json(
        USED_FILE,
        used_questions
    )

    return question


# ============================================================
# DISCORD WEBHOOK
# ============================================================

def send_question(question):
    payload = {
        "username": WEBHOOK_NAME,

        "embeds": [
            {
                "title": "💭 Question of the Day",

                "description": (
                    f"**{question}**"
                    "\n\n"
                    "💬 Share your thoughts below!"
                ),

                "color": 65413,

                "footer": {
                    "text": (
                        "Nickolas Lilly Assistant • "
                        "Question of the Day"
                    )
                }
            }
        ]
    }

    response = requests.post(
        WEBHOOK_URL,
        json=payload,
        timeout=30
    )

    if response.status_code not in (200, 204):
        raise RuntimeError(
            "Discord webhook failed: "
            f"{response.status_code} "
            f"{response.text}"
        )

    print("Question successfully posted.")


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 60)
    print("DAILY DISCUSSION QOTD")
    print("=" * 60)

    question = get_question()

    print()
    print("Selected question:")
    print(question)
    print()

    send_question(question)

    print()
    print("QOTD completed successfully.")
    print("=" * 60)


if __name__ == "__main__":
    main()
