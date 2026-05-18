from __future__ import annotations

from dataclasses import dataclass

from mlflow.tracking import MlflowClient


@dataclass(frozen=True)
class PromoteResult:
    promoted: bool
    version: str
    reason: str


class ModelPromoter:
    def __init__(
        self,
        tracking_uri: str,
        model_name: str,
        thresholds: dict[str, float],
    ) -> None:
        self._client = MlflowClient(tracking_uri)
        self._model_name = model_name
        self._thresholds = thresholds

    def promote(self, version: str) -> PromoteResult:
        metrics = self._get_run_metrics(version)
        if not self._meets_thresholds(metrics):
            failed = [
                f"{k}={metrics.get(k, 0.0):.4f} < {v}"
                for k, v in self._thresholds.items()
                if metrics.get(k, 0.0) < v
            ]
            return PromoteResult(
                promoted=False, version=version, reason="; ".join(failed)
            )
        self._client.set_registered_model_alias(self._model_name, "Production", version)
        return PromoteResult(promoted=True, version=version, reason="all thresholds met")

    def _get_run_metrics(self, version: str) -> dict[str, float]:
        mv = self._client.get_model_version(self._model_name, version)
        run = self._client.get_run(mv.run_id)
        return {k: float(v) for k, v in run.data.metrics.items()}

    def _meets_thresholds(self, metrics: dict[str, float]) -> bool:
        return all(metrics.get(k, 0.0) >= v for k, v in self._thresholds.items())
