import os
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, Query, Depends, Body
from fastapi.middleware.cors import CORSMiddleware
from bson import ObjectId

from db import connect_to_mongo, close_mongo_connection, get_db
from utils.extract_text import extract_text_from_pdf, extract_text_from_docx, extract_text_from_txt
from utils.keywords import extract_keywords
from utils.quiz import generate_quiz
from utils.serializers import serialize_fiche, str_id

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.on_event("startup")
async def startup_event():
    await connect_to_mongo()

@app.on_event("shutdown")
async def shutdown_event():
    await close_mongo_connection()

@app.get("/")
async def root():
    return {"status": "ok"}

@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    user_id: str = Query(default="test-user-1"),
    db = Depends(get_db),
):
    file_path = os.path.join(UPLOAD_FOLDER, file.filename)
    with open(file_path, "wb") as f:
        f.write(await file.read())

    if file.filename.endswith(".pdf"):
        text = extract_text_from_pdf(file_path)
    elif file.filename.endswith(".docx"):
        text = extract_text_from_docx(file_path)
    elif file.filename.endswith(".txt"):
        text = extract_text_from_txt(file_path)
    else:
        return {"error": "Format non pris en charge"}

    if not text.strip():
        return {"error": "Le fichier est vide ou non lisible"}

    keywords = extract_keywords(text)
    quiz = generate_quiz(text, keywords, num_questions=5)

    fiche_doc = {
        "user_id": user_id,
        "source": {
            "filename": file.filename,
            "mime": file.content_type,
            "size": None,
            "storage": "local",
            "path_or_url": file_path,
        },
        "lang": "fr",
        "status": "processed",
        "extracted_text": text,
        "keywords": keywords,
        "stats": {"chars": len(text), "words": len(text.split())},
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow(),
    }
    fiche_res = await db.fiches.insert_one(fiche_doc)
    fiche_id = fiche_res.inserted_id

    quiz_doc = {
        "user_id": user_id,
        "fiche_id": fiche_id,
        "version": 1,
        "generator": "rule_based",
        "questions": quiz,
        "createdAt": datetime.utcnow(),
    }
    quiz_res = await db.quizzes.insert_one(quiz_doc)

    return {
        "ficheId": str_id(fiche_id),
        "quizId": str_id(quiz_res.inserted_id),
        "filename": file.filename,
        "keywords": keywords,
        "quiz_preview": quiz[:2],
        "extracted_text": text[:800],
    }

@app.get("/fiches/me")
async def list_my_fiches(
    user_id: str = Query(default="test-user-1"),
    limit: int = 10,
    skip: int = 0,
    db = Depends(get_db),
):
    cursor = db.fiches.find({"user_id": user_id}).sort("createdAt", -1).skip(skip).limit(limit)
    items = [serialize_fiche(doc) async for doc in cursor]
    total = await db.fiches.count_documents({"user_id": user_id})
    return {"total": total, "items": items}

@app.get("/quizzes/by-fiche/{fiche_id}")
async def get_quiz_by_fiche(
    fiche_id: str,
    user_id: str = Query(default="test-user-1"),
    db = Depends(get_db),
):
    doc = await db.quizzes.find_one({"fiche_id": ObjectId(fiche_id), "user_id": user_id})
    if not doc:
        return {"error": "Quiz introuvable"}
    doc["_id"] = str_id(doc["_id"])
    doc["fiche_id"] = str_id(doc["fiche_id"])
    return doc

@app.post("/quiz-results")
async def submit_quiz_result(
    payload: dict = Body(...),
    user_id: str = Query(default="test-user-1"),
    db = Depends(get_db),
):
    quiz_id = payload.get("quiz_id")
    fiche_id = payload.get("fiche_id")
    answers = payload.get("answers", [])
    startedAt = payload.get("startedAt")

    if not quiz_id or not fiche_id:
        return {"error": "quiz_id et fiche_id requis"}

    quiz = await db.quizzes.find_one({"_id": ObjectId(quiz_id), "user_id": user_id})
    if not quiz:
        return {"error": "Quiz introuvable"}

    questions = quiz.get("questions", [])
    report = []
    score = 0

    for a in answers:
        qi = a.get("q_index")
        if qi is None or qi < 0 or qi >= len(questions):
            continue
        q = questions[qi]
        entry = {"q_index": qi, "type": q["type"]}

        if q["type"] == "mcq":
            selected = a.get("selected_index")
            correct_index = q.get("answer_index")
            is_correct = (selected == correct_index)
            entry.update({
                "question": q.get("question"),
                "choices": q.get("choices"),
                "selected_index": selected,
                "correct_index": correct_index,
                "is_correct": is_correct,
                "explanation": q.get("explanation")
            })
        else:
            selected_bool = a.get("selected_bool")
            correct_bool = bool(q.get("answer"))
            is_correct = (bool(selected_bool) == correct_bool)
            entry.update({
                "statement": q.get("statement"),
                "selected_bool": bool(selected_bool),
                "correct_bool": correct_bool,
                "is_correct": is_correct,
                "explanation": q.get("explanation")
            })

        if entry["is_correct"]:
            score += 1
        report.append(entry)

    result_doc = {
        "user_id": user_id,
        "quiz_id": ObjectId(quiz_id),
        "fiche_id": ObjectId(fiche_id),
        "answers": report,
        "score": score,
        "total": len(questions),
        "startedAt": startedAt or datetime.utcnow(),
        "finishedAt": datetime.utcnow(),
    }
    res = await db.quiz_results.insert_one(result_doc)

    return {
        "resultId": str(res.inserted_id),
        "score": score,
        "total": len(questions),
        "report": report
    }

@app.get("/results/me")
async def list_my_results(
    user_id: str = Query(default="test-user-1"),
    limit: int = 10,
    skip: int = 0,
    db = Depends(get_db),
):
    cursor = db.quiz_results.find({"user_id": user_id}).sort("finishedAt", -1).skip(skip).limit(limit)
    items = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        doc["quiz_id"] = str(doc["quiz_id"])
        doc["fiche_id"] = str(doc["fiche_id"])
        items.append(doc)
    total = await db.quiz_results.count_documents({"user_id": user_id})
    return {"total": total, "items": items}
