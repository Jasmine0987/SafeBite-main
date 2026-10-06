from fastapi import APIRouter
from pydantic import BaseModel
from app.ai.nudge import nudge_risk

router = APIRouter()

class NudgeRequest(BaseModel):
    scans: list[list[float]]

@router.post("/api/nudge")
def nudge(req: NudgeRequest):
    risk = nudge_risk(req.scans)
    return {"risk": risk, "nudge": bool(risk is not None and risk > 0.6), "simulated": True}
