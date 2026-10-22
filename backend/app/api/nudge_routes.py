from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.ai.nudge import nudge_risk

router = APIRouter()

class NudgeRequest(BaseModel):
    scans: list[list[float]]

@router.post("/api/nudge")
def nudge(req: NudgeRequest):
    if any(len(s) != 3 for s in req.scans):
        raise HTTPException(422, "Each scan must be a list of exactly 3 numbers.")
    risk = nudge_risk(req.scans)
    return {"risk": risk, "nudge": bool(risk is not None and risk > 0.6), "simulated": True}
