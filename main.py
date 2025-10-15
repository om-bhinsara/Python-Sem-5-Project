from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uuid
import random
from typing import Dict, Any, Optional
import os

app = FastAPI()

# CORS for local dev; adjust as needed
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],            # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/images", StaticFiles(directory="images"), name="images")

# Mount static folder to serve static files like index.html, app.js, etc.
#app.mount("/static", StaticFiles(directory="static"), name="static")

# Serve the index.html file when visiting the root URL
@app.get("/")
async def read_index():
    return FileResponse("index.html")  # Ensure the path to index.html is correct

# Your game logic (remains the same as in the code you provided)
class AnswerRequest(BaseModel):
    game_id: str
    answer: str  # accept string, parse as int

GAMES: Dict[str, Dict[str, Any]] = {}

def generate_question() -> Dict[str, Any]:
    a = random.randint(0, 12)
    b = random.randint(0, 12)
    op = random.choice(["+", "-", "×"])
    if op == "+":
        ans = a + b
    elif op == "-":
        ans = a - b
    else:
        ans = a * b
    text = f"{a} {op} {b} = ?"
    return {"id": str(uuid.uuid4()), "text": text, "answer": ans}

def new_game_state() -> Dict[str, Any]:
    return {
        "user_distance": 10,
        "comp_distance": 10,
        "user_correct": 0,
        "comp_correct": 0,
        "user_questions_asked": 0,
        "comp_questions_asked": 0,
        "status": "playing",               # playing | won | lost
        "current_user_q": generate_question(),
        "comp_accuracy": 0.6,              # configurable
        "last_user": None,
        "last_comp": None,
    }

def check_loss(distance: int) -> bool:
    return distance < 3

def finalize_if_done(state: Dict[str, Any]) -> None:
    # End when user has answered 10 questions or if already lost
    if state["status"] != "playing":
        return
    if state["user_questions_asked"] >= 10:
        if state["user_correct"] >= 7 and not check_loss(state["user_distance"]):
            state["status"] = "won"
        else:
            state["status"] = "lost"

@app.post("/start")
def start():
    game_id = str(uuid.uuid4())
    state = new_game_state()
    GAMES[game_id] = state
    return {
        "game_id": game_id,
        "state": {
            "status": state["status"],
            "user_distance": state["user_distance"],
            "comp_distance": state["comp_distance"],
            "user_correct": state["user_correct"],
            "comp_correct": state["comp_correct"],
            "user_questions_asked": state["user_questions_asked"],
            "comp_questions_asked": state["comp_questions_asked"],
            "question": {
                "id": state["current_user_q"]["id"],
                "text": state["current_user_q"]["text"],
            },
            "last_user": None,
            "last_comp": None,
        },
    }

@app.post("/answer")
def answer(req: AnswerRequest):
    if req.game_id not in GAMES:
        raise HTTPException(status_code=404, detail="Invalid game_id")
    state = GAMES[req.game_id]
    if state["status"] != "playing":
        return {"error": "Game over", "state": state}

    # User turn
    q = state["current_user_q"]
    correct_answer = q["answer"]
    try:
        user_ans = int(req.answer.strip())
    except Exception:
        user_ans = None

    user_correct = (user_ans == correct_answer)
    if user_correct:
        state["user_correct"] += 1
    else:
        state["user_distance"] -= 1

    state["user_questions_asked"] += 1
    state["last_user"] = {
        "question": q["text"],
        "provided": req.answer,
        "correct": user_correct,
        "correct_answer": correct_answer,
        "user_distance": state["user_distance"],
    }

    # Check immediate loss after user turn
    if check_loss(state["user_distance"]):
        state["status"] = "lost"

    # If still playing, simulate computer turn (independent path)
    last_comp: Optional[Dict[str, Any]] = None
    if state["status"] == "playing":
        comp_q = generate_question()
        comp_correct = (random.random() < state["comp_accuracy"])
        if comp_correct:
            state["comp_correct"] += 1
        else:
            state["comp_distance"] -= 1
        state["comp_questions_asked"] += 1
        last_comp = {
            "question": comp_q["text"],
            "correct": comp_correct,
            "correct_answer": comp_q["answer"],
            "comp_distance": state["comp_distance"],
        }
        state["last_comp"] = last_comp

    # Check win/lose after user count reaches 10 (even if comp still plays)
    finalize_if_done(state)

    # Prepare next question if still playing
    next_q = None
    if state["status"] == "playing":
        state["current_user_q"] = generate_question()
        next_q = {
            "id": state["current_user_q"]["id"],
            "text": state["current_user_q"]["text"],
        }

    return {
        "state": {
            "status": state["status"],
            "user_distance": state["user_distance"],
            "comp_distance": state["comp_distance"],
            "user_correct": state["user_correct"],
            "comp_correct": state["comp_correct"],
            "user_questions_asked": state["user_questions_asked"],
            "comp_questions_asked": state["comp_questions_asked"],
            "question": next_q,
            "last_user": state["last_user"],
            "last_comp": state["last_comp"],
        }
    }
    
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))  # Use Render’s dynamic PORT
    uvicorn.run(app, host="0.0.0.0", port=port)   