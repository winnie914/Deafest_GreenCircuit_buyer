const express = require("express");
const path = require("path");

const app = express();
app.use(express.json());

// ---------- 설정값 (여기만 바꿔서 튜닝) ----------
const TESTS = ["camera", "mic", "speaker", "gyro", "touch"];
const RANK_WEIGHTS = [0.5, 0.3, 0.2]; // 1순위, 2순위, 3순위 가중치 (합 = 1)
const W_PERF = 0.4, W_PRICE = 0.35, W_ECO = 0.25; // 최종 점수 비중 (합 = 1)
const MIN_PRIORITY_SCORE = 60; // 선택한 3개 항목 중 이 점수 미만이면 제외

// ---------- 샘플 데이터 (실제로는 DB/성능 검사 결과에서 가져오기) ----------
const LISTINGS = [
  { id: 1, model: "갤럭시 S23", price: 520000, eco_temp: 78,
    scores: { camera: 92, mic: 85, speaker: 80, gyro: 90, touch: 88 } },
  { id: 2, model: "갤럭시 S23", price: 480000, eco_temp: 45,
    scores: { camera: 75, mic: 90, speaker: 85, gyro: 70, touch: 80 } },
  { id: 3, model: "갤럭시 S23", price: 610000, eco_temp: 92,
    scores: { camera: 98, mic: 95, speaker: 92, gyro: 96, touch: 97 } },
  { id: 4, model: "아이폰 14", price: 650000, eco_temp: 60,
    scores: { camera: 90, mic: 88, speaker: 86, gyro: 91, touch: 93 } },
];

// ---------- 유틸 ----------
const normalize = (text) => text.replace(/\s+/g, "").toLowerCase();
const clamp = (x, lo = 0, hi = 1) => Math.max(lo, Math.min(hi, x));
const round1 = (x) => Math.round(x * 10) / 10;

function median(nums) {
  const s = [...nums].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

// ---------- 핵심 로직 ----------
function recommend(deviceModel, priorities) {
  // 1) 기종 필터 (공백/대소문자 무시, 부분 일치)
  const q = normalize(deviceModel);
  let candidates = LISTINGS.filter((l) => normalize(l.model).includes(q));

  // 2) 중시하는 성능 3개가 최소 기준 미만인 매물 제외
  candidates = candidates.filter((l) =>
    priorities.every((p) => l.scores[p] >= MIN_PRIORITY_SCORE)
  );
  if (candidates.length === 0) return [];

  // 3) 가격 기준선: 같은 조건 후보들의 중앙값 (나중에 Gemini 시세로 교체 가능)
  const refPrice = median(candidates.map((l) => l.price));

  const results = candidates.map((l) => {
    // 성능 점수: 순위별 가중 평균 (0~1)
    const perf =
      priorities.reduce((sum, p, i) => sum + RANK_WEIGHTS[i] * l.scores[p], 0) / 100;

    // 가격 점수: 기준가 대비 비율. 0.7배 이하면 1점, 1.3배 이상이면 0점
    const ratio = l.price / refPrice;
    const price = clamp(1 - (ratio - 0.7) / 0.6);

    // 환경온도 점수 (0~100 -> 0~1)
    const eco = clamp(l.eco_temp / 100);

    const final = W_PERF * perf + W_PRICE * price + W_ECO * eco;
    return {
      ...l,
      final_score: round1(final * 100),
      breakdown: {
        performance: round1(perf * 100),
        price: round1(price * 100),
        eco: round1(eco * 100),
      },
    };
  });

  // 4) 최종 점수 내림차순
  results.sort((a, b) => b.final_score - a.final_score);
  return results;
}

// ---------- API ----------
app.post("/recommend", (req, res) => {
  const { device_model, priorities } = req.body || {};

  if (typeof device_model !== "string" || !device_model.trim()) {
    return res.status(422).json({ detail: "기종을 입력해야 합니다." });
  }
  if (
    !Array.isArray(priorities) ||
    priorities.length !== 3 ||
    new Set(priorities).size !== 3 ||
    !priorities.every((p) => TESTS.includes(p))
  ) {
    return res.status(422).json({
      detail: `서로 다른 성능 항목 3개를 순위대로 선택해야 합니다. (가능: ${TESTS.join(", ")})`,
    });
  }

  const items = recommend(device_model, priorities);
  if (items.length === 0) {
    return res.status(404).json({ detail: "조건에 맞는 매물이 없습니다." });
  }
  res.json({ query: { device_model, priorities }, count: items.length, items });
});

// 화면(static/index.html) 서빙
app.use(express.static(path.join(__dirname, "static")));

const PORT = process.env.PORT || 8000;
app.listen(PORT, () => console.log(`http://localhost:${PORT}`));