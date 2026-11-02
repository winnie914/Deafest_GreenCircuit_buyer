from statistics import median
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator

app = FastAPI(title="중고 스마트폰 구매자 추천")

from pathlib import Path
from fastapi.responses import FileResponse

BASE_DIR = Path(__file__).resolve().parent

@app.get("/")
def home():
    return FileResponse(BASE_DIR / "static" / "index.html")

# ---------- 설정값 (여기만 바꿔서 튜닝) ----------
TESTS = ["camera", "mic", "speaker", "gyro", "touch"]
RANK_WEIGHTS = [0.5, 0.3, 0.2]          # 1순위, 2순위, 3순위 가중치 (합 = 1)
W_PERF, W_PRICE, W_ECO = 0.40, 0.35, 0.25  # 최종 점수 비중 (합 = 1)
MIN_PRIORITY_SCORE = 60                 # 선택한 3개 항목 중 이 점수 미만이면 제외

# ---------- 샘플 데이터 (실제로는 DB/성능 검사 결과에서 가져오기) ----------
LISTINGS = [
    {"id": 1, "model": "갤럭시 S23", "price": 520000, "eco_temp": 36.6,
     "scores": {"camera": 92, "mic": 85, "speaker": 80, "gyro": 90, "touch": 88}},
    {"id": 2, "model": "갤럭시 S23", "price": 480000, "eco_temp": 37.31,
     "scores": {"camera": 75, "mic": 90, "speaker": 85, "gyro": 70, "touch": 80}},
    {"id": 3, "model": "갤럭시 S23", "price": 610000, "eco_temp": 37.51,
     "scores": {"camera": 98, "mic": 95, "speaker": 92, "gyro": 96, "touch": 97}},
    {"id": 4, "model": "아이폰 14", "price": 650000, "eco_temp": 36.6,
     "scores": {"camera": 90, "mic": 88, "speaker": 86, "gyro": 91, "touch": 93}},
]


# ---------- 요청/응답 모델 ----------
class RecommendRequest(BaseModel):
    device_model: str
    priorities: list[str]  # 순서대로 1, 2, 3순위. 예: ["camera", "touch", "gyro"]

    @field_validator("priorities")
    @classmethod
    def check_priorities(cls, v):
        if len(v) != 3 or len(set(v)) != 3:
            raise ValueError("서로 다른 성능 항목 3개를 순위대로 선택해야 합니다.")
        for item in v:
            if item not in TESTS:
                raise ValueError(f"지원하지 않는 항목: {item} (가능: {TESTS})")
        return v


def normalize(text: str) -> str:
    return text.replace(" ", "").lower()


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


# ---------- 핵심 로직 ----------
def recommend(device_model: str, priorities: list[str]) -> list[dict]:
    # 1) 기종 필터 (공백/대소문자 무시, 부분 일치)
    q = normalize(device_model)
    candidates = [l for l in LISTINGS if q in normalize(l["model"])]
    if not candidates:
        return []

    # 2) 중시하는 성능 3개가 최소 기준 미만인 매물 제외
    candidates = [
        l for l in candidates
        if all(l["scores"][p] >= MIN_PRIORITY_SCORE for p in priorities)
    ]
    if not candidates:
        return []

    # 3) 가격 기준선: 같은 조건 후보들의 중앙값 (나중에 Gemini 시세로 교체 가능)
    ref_price = median(l["price"] for l in candidates)

    results = []
    for l in candidates:
        # 성능 점수: 순위별 가중 평균 (0~1)
        perf = sum(w * l["scores"][p] for w, p in zip(RANK_WEIGHTS, priorities)) / 100

        # 가격 점수: 기준가 대비 비율. 0.7배 이하면 1점, 1.3배 이상이면 0점
        ratio = l["price"] / ref_price
        price = clamp(1 - (ratio - 0.7) / 0.6)

        # 환경온도 점수 (36.6 기준)
        ECO_BASE = 36.6
        ECO_TARGET = 40.0

        eco = clamp(
            (l["eco_temp"] - ECO_BASE) / (ECO_TARGET - ECO_BASE)
)

        final = W_PERF * perf + W_PRICE * price + W_ECO * eco
        results.append({
            **l,
            "final_score": round(final * 100, 1),
            "breakdown": {
                "performance": round(perf * 100, 1),
                "price": round(price * 100, 1),
                "eco": round(eco * 100, 1),
            },
        })

    # 4) 최종 점수 내림차순
    results.sort(key=lambda r: r["final_score"], reverse=True)
    return results


# ---------- API ----------
@app.post("/recommend")
def recommend_api(req: RecommendRequest):
    items = recommend(req.device_model, req.priorities)
    if not items:
        raise HTTPException(404, "조건에 맞는 매물이 없습니다.")
    return {"query": req.model_dump(), "count": len(items), "items": items}