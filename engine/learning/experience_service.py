from __future__ import annotations


class ExperienceService:
    def __init__(self, store, minimum_samples: int = 5, prior_weight: float = 10.0,
                 max_adjustment: float = 1.5):
        self.store = store
        self.minimum_samples = minimum_samples
        self.prior_weight = prior_weight
        self.max_adjustment = max_adjustment

    def apply(self, context: dict, candidates: list[dict]) -> list[dict]:
        output = []
        for candidate in candidates:
            rows = self.store.query_similar(context, candidate["action_key"])
            count = len(rows)
            mean = sum(float(row["reward"]) for row in rows) / count if rows else 0.0
            confidence = count / (count + self.prior_weight)
            adjustment = 0.0
            if count >= self.minimum_samples:
                adjustment = max(-self.max_adjustment, min(self.max_adjustment, mean * 0.05 * confidence))
            baseline = float(candidate["score"])
            output.append({**candidate, "baseline_score": baseline,
                           "historical_adjustment": round(adjustment, 3),
                           "final_score": round(baseline + adjustment, 3),
                           "sample_count": count, "confidence": round(confidence, 3)})
        return sorted(output, key=lambda item: item["final_score"], reverse=True)
