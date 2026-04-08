from __future__ import annotations

from app.contracts.schemas import FeatureVector, InferenceResult


class MockModelAdapter:
    model_id = "mock-default"

    def infer(self, features: FeatureVector) -> InferenceResult:
        score = float(features.values["Risk Hint"])
        if score >= 0.8:
            label = "anomaly"
            reason = "High risk hint based on burst size and flow density."
        elif score >= 0.45:
            label = "warning"
            reason = "Medium confidence anomaly, should be reviewed."
        else:
            label = "normal"
            reason = "Traffic profile looks stable for the mock baseline."

        return InferenceResult(
            event_id=features.event_id,
            label=label,
            score=round(score, 3),
            reason=reason,
            model_id=self.model_id,
        )

