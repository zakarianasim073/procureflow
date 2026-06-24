from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import httpx
import numpy as np
from sqlalchemy import case, func, select

from app.db.models import Award, OpeningReport
from app.core.ollama_client import OllamaClient
from app.models.intelligence import Contractor as IntelContractor, ProcurementLifecycle, PPREvaluation

PPR_REGIME_CUTOFF_DATE = datetime(2025, 9, 28).date()
REGIME_PPR2025 = "PPR2025"


def get_regime(tender_date: Any) -> str:
    if tender_date is None:
        return "PPR2008"
    try:
        if hasattr(tender_date, "date"):
            tender_date = tender_date.date()
        elif isinstance(tender_date, str):
            tender_date = datetime.fromisoformat(tender_date.replace("Z", "+00:00")).date()
    except Exception:
        return "PPR2008"
    return "PPR2025" if tender_date >= PPR_REGIME_CUTOFF_DATE else "PPR2008"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _runtime_dir() -> Path:
    root = _repo_root() / "runtime" / "ppr_ml"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, bool):
            return float(value)
        return float(value)
    except Exception:
        return default


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    return " ".join(text.split())


def _normalize_name(value: Any) -> str:
    text = _normalize_text(value)
    if not text:
        return ""
    keep = []
    for ch in text:
        if ch.isalnum() or ch.isspace():
            keep.append(ch)
    return " ".join("".join(keep).split())


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def _sigmoid(x: np.ndarray | float) -> np.ndarray | float:
    arr = np.asarray(x, dtype=float)
    clipped = np.clip(arr, -35.0, 35.0)
    out = 1.0 / (1.0 + np.exp(-clipped))
    if np.isscalar(x):
        return float(out)
    return out


def _safe_auc(y_true: np.ndarray, scores: np.ndarray) -> float:
    if len(y_true) == 0:
        return 0.0
    y_true = np.asarray(y_true, dtype=int)
    scores = np.asarray(scores, dtype=float)
    pos = int(y_true.sum())
    neg = int(len(y_true) - pos)
    if pos == 0 or neg == 0:
        return 0.5
    order = np.argsort(scores)
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, len(scores) + 1)
    pos_ranks = ranks[y_true == 1].sum()
    return float((pos_ranks - pos * (pos + 1) / 2.0) / (pos * neg))


def _safe_average_precision(y_true: np.ndarray, scores: np.ndarray) -> float:
    if len(y_true) == 0:
        return 0.0
    y_true = np.asarray(y_true, dtype=int)
    scores = np.asarray(scores, dtype=float)
    order = np.argsort(-scores)
    y_sorted = y_true[order]
    total_pos = int(y_sorted.sum())
    if total_pos == 0:
        return 0.0
    tp = 0
    fp = 0
    prev_recall = 0.0
    ap = 0.0
    for label in y_sorted:
        if label:
            tp += 1
        else:
            fp += 1
        recall = tp / total_pos
        precision = tp / max(tp + fp, 1)
        ap += precision * (recall - prev_recall)
        prev_recall = recall
    return float(ap)


def _brier_score(y_true: np.ndarray, probs: np.ndarray) -> float:
    if len(y_true) == 0:
        return 0.0
    y_true = np.asarray(y_true, dtype=float)
    probs = np.asarray(probs, dtype=float)
    return float(np.mean((probs - y_true) ** 2))


def _log_loss(y_true: np.ndarray, probs: np.ndarray) -> float:
    if len(y_true) == 0:
        return 0.0
    y_true = np.asarray(y_true, dtype=float)
    probs = np.clip(np.asarray(probs, dtype=float), 1e-6, 1 - 1e-6)
    return float(-np.mean(y_true * np.log(probs) + (1 - y_true) * np.log(1 - probs)))


def _classification_report(y_true: np.ndarray, probs: np.ndarray, threshold: float = 0.5) -> Dict[str, float]:
    pred = (np.asarray(probs) >= threshold).astype(int)
    y_true = np.asarray(y_true).astype(int)
    tp = int(((pred == 1) & (y_true == 1)).sum())
    fp = int(((pred == 1) & (y_true == 0)).sum())
    tn = int(((pred == 0) & (y_true == 0)).sum())
    fn = int(((pred == 0) & (y_true == 1)).sum())
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    accuracy = (tp + tn) / max(len(y_true), 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-9)
    return {
        "accuracy": round(float(accuracy), 4),
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "f1": round(float(f1), 4),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
    }


def _platt_fit(scores: np.ndarray, y_true: np.ndarray) -> Tuple[float, float]:
    scores = np.asarray(scores, dtype=float)
    y_true = np.asarray(y_true, dtype=float)
    if len(scores) == 0 or len(np.unique(y_true)) < 2:
        return 1.0, 0.0
    a = 1.0
    b = 0.0
    for _ in range(50):
        z = np.clip(a * scores + b, -35.0, 35.0)
        p = _sigmoid(z)
        g_a = float(np.sum((p - y_true) * scores))
        g_b = float(np.sum(p - y_true))
        h = p * (1 - p)
        h_aa = float(np.sum(h * scores * scores))
        h_ab = float(np.sum(h * scores))
        h_bb = float(np.sum(h))
        det = h_aa * h_bb - h_ab * h_ab
        if abs(det) < 1e-12:
            break
        step_a = (h_bb * g_a - h_ab * g_b) / det
        step_b = (-h_ab * g_a + h_aa * g_b) / det
        a -= step_a
        b -= step_b
        if max(abs(step_a), abs(step_b)) < 1e-6:
            break
    return float(a), float(b)


def _approx_equal(left: float, right: float, tolerance: float = 0.02) -> bool:
    baseline = max(abs(left), abs(right), 1.0)
    return abs(left - right) <= baseline * tolerance


def _best_name_match(candidate: str, target: str) -> bool:
    candidate = _normalize_name(candidate)
    target = _normalize_name(target)
    if not candidate or not target:
        return False
    if candidate == target:
        return True
    if candidate in target or target in candidate:
        return True
    return SequenceMatcher(None, candidate, target).ratio() >= 0.82


def _safe_json_loads(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return []
    return []


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if hasattr(value, "to_pydatetime"):
        try:
            return value.to_pydatetime()
        except Exception:
            pass
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y"):
                try:
                    return datetime.strptime(text, fmt)
                except Exception:
                    continue
    return None


def _coerce_date_key(value: Any) -> float:
    dt = _coerce_datetime(value)
    if dt is None:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return float(dt.timestamp())


@dataclass
class _Stump:
    feature_idx: int
    threshold: float
    left_value: float
    right_value: float
    monotonic: int

    def predict(self, x: np.ndarray) -> np.ndarray:
        mask = x[:, self.feature_idx] <= self.threshold
        return np.where(mask, self.left_value, self.right_value)

    def contribution(self, value: float) -> float:
        return self.left_value if value <= self.threshold else self.right_value

    def to_dict(self, feature_name: str) -> Dict[str, Any]:
        return {
            "feature": feature_name,
            "feature_idx": self.feature_idx,
            "threshold": float(self.threshold),
            "left_value": float(self.left_value),
            "right_value": float(self.right_value),
            "monotonic": int(self.monotonic),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "_Stump":
        return cls(
            feature_idx=int(data["feature_idx"]),
            threshold=float(data["threshold"]),
            left_value=float(data["left_value"]),
            right_value=float(data["right_value"]),
            monotonic=int(data.get("monotonic", 0)),
        )


class PortableBoostingModel:
    def __init__(
        self,
        feature_names: Sequence[str],
        monotonic_cst: Sequence[int],
        learning_rate: float = 0.08,
        n_estimators: int = 48,
        min_samples_leaf: int = 25,
        threshold_bins: int = 9,
    ) -> None:
        self.feature_names = list(feature_names)
        self.monotonic_cst = list(monotonic_cst)
        self.learning_rate = learning_rate
        self.n_estimators = n_estimators
        self.min_samples_leaf = min_samples_leaf
        self.threshold_bins = threshold_bins
        self.base_logit = 0.0
        self.calibration_a = 1.0
        self.calibration_b = 0.0
        self.feature_medians: List[float] = []
        self.stumps: List[_Stump] = []
        self.training_rows = 0

    def _prepare_X(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, dtype=float)
        if X.ndim == 1:
            X = X.reshape(1, -1)
        if not self.feature_medians:
            self.feature_medians = [0.0] * X.shape[1]
        for idx, median in enumerate(self.feature_medians):
            column = X[:, idx]
            mask = ~np.isfinite(column)
            if mask.any():
                column = column.copy()
                column[mask] = median
                X[:, idx] = column
        return X

    def fit(self, X: np.ndarray, y: np.ndarray, sample_weight: Optional[np.ndarray] = None) -> "PortableBoostingModel":
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)
        if sample_weight is None:
            sample_weight = np.ones(len(y), dtype=float)
        else:
            sample_weight = np.asarray(sample_weight, dtype=float)

        self.training_rows = int(len(y))
        if X.size == 0 or len(np.unique(y)) < 2:
            self.base_logit = 0.0
            self.stumps = []
            self.feature_medians = [0.0] * (X.shape[1] if X.ndim == 2 else len(self.feature_names))
            return self

        self.feature_medians = [
            float(np.nanmedian(X[:, idx])) if np.isfinite(np.nanmedian(X[:, idx])) else 0.0
            for idx in range(X.shape[1])
        ]
        X = self._prepare_X(X.copy())
        pos = float(np.sum(sample_weight[y == 1]))
        neg = float(np.sum(sample_weight[y == 0]))
        self.base_logit = float(math.log((pos + 0.5) / (neg + 0.5)))
        f = np.full(len(y), self.base_logit, dtype=float)
        self.stumps = []

        for _ in range(self.n_estimators):
            p = np.clip(_sigmoid(f), 1e-6, 1 - 1e-6)
            grad = (y - p) * sample_weight
            hess = p * (1 - p) * sample_weight
            best_gain = 0.0
            best_stump: Optional[_Stump] = None
            total_grad = float(np.sum(grad))
            total_hess = float(np.sum(hess))
            if total_hess <= 1e-9:
                break

            for feature_idx in range(X.shape[1]):
                x = X[:, feature_idx]
                values = np.unique(np.quantile(x, np.linspace(0.1, 0.9, self.threshold_bins)))
                if len(values) == 0:
                    continue
                monotonic = int(self.monotonic_cst[feature_idx]) if feature_idx < len(self.monotonic_cst) else 0
                for threshold in values:
                    left_mask = x <= threshold
                    right_mask = ~left_mask
                    left_count = int(left_mask.sum())
                    right_count = int(right_mask.sum())
                    if left_count < self.min_samples_leaf or right_count < self.min_samples_leaf:
                        continue
                    gl = float(np.sum(grad[left_mask]))
                    hl = float(np.sum(hess[left_mask]))
                    gr = float(np.sum(grad[right_mask]))
                    hr = float(np.sum(hess[right_mask]))
                    if hl <= 1e-9 or hr <= 1e-9:
                        continue
                    left_value = gl / hl
                    right_value = gr / hr
                    if monotonic > 0 and right_value < left_value:
                        continue
                    if monotonic < 0 and right_value > left_value:
                        continue
                    gain = 0.5 * ((gl * gl) / hl + (gr * gr) / hr - (total_grad * total_grad) / total_hess)
                    if gain > best_gain + 1e-12:
                        best_gain = gain
                        best_stump = _Stump(
                            feature_idx=feature_idx,
                            threshold=float(threshold),
                            left_value=float(left_value),
                            right_value=float(right_value),
                            monotonic=monotonic,
                        )

            if best_stump is None or best_gain <= 1e-9:
                break

            self.stumps.append(best_stump)
            f += self.learning_rate * best_stump.predict(X)

        return self

    def decision_function(self, X: np.ndarray) -> np.ndarray:
        X = self._prepare_X(np.asarray(X, dtype=float).copy())
        scores = np.full(X.shape[0], self.base_logit, dtype=float)
        for stump in self.stumps:
            scores += self.learning_rate * stump.predict(X)
        return scores

    def predict_logit(self, X: np.ndarray) -> np.ndarray:
        return self.decision_function(X)

    def set_calibration(self, logits: np.ndarray, y: np.ndarray) -> None:
        a, b = _platt_fit(np.asarray(logits, dtype=float), np.asarray(y, dtype=float))
        self.calibration_a = float(a)
        self.calibration_b = float(b)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        logits = self.decision_function(X)
        calibrated = self.calibration_a * logits + self.calibration_b
        return np.asarray(_sigmoid(calibrated), dtype=float)

    def feature_contributions(self, row: Sequence[float]) -> Dict[str, float]:
        values = np.asarray(row, dtype=float).reshape(1, -1)
        values = self._prepare_X(values)
        contributions = {name: 0.0 for name in self.feature_names}
        for stump in self.stumps:
            feature_name = self.feature_names[stump.feature_idx]
            contributions[feature_name] += self.learning_rate * stump.contribution(float(values[0, stump.feature_idx]))
        return contributions

    def top_factors(self, row: Sequence[float], limit: int = 6) -> List[Dict[str, Any]]:
        contributions = self.feature_contributions(row)
        sorted_items = sorted(contributions.items(), key=lambda kv: abs(kv[1]), reverse=True)[:limit]
        return [
            {
                "feature": name,
                "impact_logit": round(float(value), 4),
                "direction": "favorable" if value > 0 else "unfavorable" if value < 0 else "neutral",
            }
            for name, value in sorted_items
        ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_names": self.feature_names,
            "monotonic_cst": self.monotonic_cst,
            "learning_rate": self.learning_rate,
            "n_estimators": self.n_estimators,
            "min_samples_leaf": self.min_samples_leaf,
            "threshold_bins": self.threshold_bins,
            "base_logit": self.base_logit,
            "calibration_a": self.calibration_a,
            "calibration_b": self.calibration_b,
            "feature_medians": self.feature_medians,
            "training_rows": self.training_rows,
            "stumps": [stump.to_dict(self.feature_names[stump.feature_idx]) for stump in self.stumps],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PortableBoostingModel":
        model = cls(
            feature_names=data["feature_names"],
            monotonic_cst=data.get("monotonic_cst", [0] * len(data["feature_names"])),
            learning_rate=float(data.get("learning_rate", 0.08)),
            n_estimators=int(data.get("n_estimators", 48)),
            min_samples_leaf=int(data.get("min_samples_leaf", 25)),
            threshold_bins=int(data.get("threshold_bins", 9)),
        )
        model.base_logit = float(data.get("base_logit", 0.0))
        model.calibration_a = float(data.get("calibration_a", 1.0))
        model.calibration_b = float(data.get("calibration_b", 0.0))
        model.feature_medians = [float(v) for v in data.get("feature_medians", [0.0] * len(model.feature_names))]
        model.training_rows = int(data.get("training_rows", 0))
        model.stumps = [_Stump.from_dict(item) for item in data.get("stumps", [])]
        return model


class PPRMLService:
    FEATURE_NAMES = [
        "bid_ratio",
        "discount_pct",
        "bidder_count",
        "bid_rank_pct",
        "gap_to_min_ratio",
        "gap_to_median_ratio",
        "opening_mean_ratio",
        "opening_std_ratio",
        "slt_share",
        "alt_share",
        "non_responsive_share",
        "has_slt_flag",
        "has_alt_flag",
        "contractor_prior_bid_count",
        "contractor_prior_win_rate",
        "contractor_prior_avg_ratio",
        "contractor_prior_avg_discount",
        "contractor_agency_affinity",
        "contractor_zone_affinity",
        "agency_prior_bidder_count",
        "agency_prior_slt_rate",
        "agency_prior_avg_ratio",
        "zone_prior_bidder_count",
        "zone_prior_slt_rate",
        "zone_prior_avg_ratio",
        "regime_2025",
    ]

    SLT_MONOTONIC = [
        -1,  # bid_ratio
        1,   # discount_pct
        1,   # bidder_count
        -1,  # bid_rank_pct
        1,   # gap_to_min_ratio
        1,   # gap_to_median_ratio
        0,   # opening_mean_ratio
        0,   # opening_std_ratio
        1,   # slt_share
        1,   # alt_share
        1,   # non_responsive_share
        1,   # has_slt_flag
        1,   # has_alt_flag
        0,   # contractor_prior_bid_count
        -1,  # contractor_prior_win_rate
        -1,  # contractor_prior_avg_ratio
        1,   # contractor_prior_avg_discount
        -1,  # contractor_agency_affinity
        -1,  # contractor_zone_affinity
        1,   # agency_prior_bidder_count
        1,   # agency_prior_slt_rate
        -1,  # agency_prior_avg_ratio
        1,   # zone_prior_bidder_count
        1,   # zone_prior_slt_rate
        -1,  # zone_prior_avg_ratio
        0,   # regime_2025
    ]

    WIN_MONOTONIC = [
        -1,  # bid_ratio
        1,   # discount_pct
        -1,  # bidder_count
        -1,  # bid_rank_pct
        -1,  # gap_to_min_ratio
        -1,  # gap_to_median_ratio
        -1,  # opening_mean_ratio
        -1,  # opening_std_ratio
        -1,  # slt_share
        -1,  # alt_share
        -1,  # non_responsive_share
        -1,  # has_slt_flag
        -1,  # has_alt_flag
        1,   # contractor_prior_bid_count
        1,   # contractor_prior_win_rate
        -1,  # contractor_prior_avg_ratio
        1,   # contractor_prior_avg_discount
        1,   # contractor_agency_affinity
        1,   # contractor_zone_affinity
        -1,  # agency_prior_bidder_count
        -1,  # agency_prior_slt_rate
        -1,  # agency_prior_avg_ratio
        -1,  # zone_prior_bidder_count
        -1,  # zone_prior_slt_rate
        -1,  # zone_prior_avg_ratio
        0,   # regime_2025
    ]

    def __init__(self, db=None):
        self.db = db
        self.runtime_dir = _runtime_dir()
        self.artifact_path = self.runtime_dir / "ppr_model_bundle.json"
        self.summary_path = self.runtime_dir / "ppr_model_summary.json"
        self._bundle: Optional[Dict[str, Any]] = None
        self._agency_prior_cache: Dict[str, Dict[str, float]] = {}
        self._zone_prior_cache: Dict[str, Dict[str, float]] = {}
        self._award_lookup_cache: Dict[str, str] = {}
        self._ollama_client: Optional[OllamaClient] = None

    async def status(self) -> Dict[str, Any]:
        bundle = await self._load_bundle()
        if not bundle:
            return {
                "trained": False,
                "message": "PPR ML bundle not trained yet",
                "artifact_path": str(self.artifact_path),
            }
        return {
            "trained": True,
            "artifact_path": str(self.artifact_path),
            "trained_at": bundle.get("trained_at"),
            "dataset": bundle.get("dataset", {}),
            "metrics": bundle.get("metrics", {}),
            "feature_names": bundle.get("feature_names", []),
        }

    async def train_models(self, force: bool = False) -> Dict[str, Any]:
        if not force and self.artifact_path.exists():
            loaded = await self._load_bundle()
            if loaded:
                return loaded.get("summary", {})

        samples = await self._build_samples()
        if not samples["rows"]:
            summary = {
                "trained": False,
                "message": "No opening-report training rows were available",
                "rows": 0,
            }
            self._write_summary(summary)
            return summary

        X = np.asarray([row["features"] for row in samples["rows"]], dtype=float)
        y_slt = np.asarray([row["slt_label"] for row in samples["rows"]], dtype=int)
        y_win = np.asarray([row["win_label"] for row in samples["rows"]], dtype=int)
        sample_weight = np.asarray([float(row.get("weight", 1.0)) for row in samples["rows"]], dtype=float)
        regimes = np.asarray([1 if row["regime"] == REGIME_PPR2025 else 0 for row in samples["rows"]], dtype=int)
        dates = np.asarray([row["sort_key"] for row in samples["rows"]], dtype=float)

        slt_train_idx, slt_calib_idx, slt_test_idx = self._split_indices(regimes, dates, y_slt)
        win_train_idx, win_calib_idx, win_test_idx = self._split_indices(regimes, dates, y_win)
        if len(slt_train_idx) == 0 or len(slt_test_idx) == 0:
            slt_train_idx = np.arange(len(X))
            slt_calib_idx = np.array([], dtype=int)
            slt_test_idx = np.arange(len(X))
        if len(win_train_idx) == 0 or len(win_test_idx) == 0:
            win_train_idx = np.arange(len(X))
            win_calib_idx = np.array([], dtype=int)
            win_test_idx = np.arange(len(X))

        slt_model = PortableBoostingModel(self.FEATURE_NAMES, self.SLT_MONOTONIC)
        win_model = PortableBoostingModel(self.FEATURE_NAMES, self.WIN_MONOTONIC)

        slt_model.fit(X[slt_train_idx], y_slt[slt_train_idx], sample_weight=sample_weight[slt_train_idx])
        win_model.fit(X[win_train_idx], y_win[win_train_idx], sample_weight=sample_weight[win_train_idx])

        if len(slt_calib_idx) > 0:
            slt_model.set_calibration(slt_model.predict_logit(X[slt_calib_idx]), y_slt[slt_calib_idx])
        else:
            slt_model.set_calibration(slt_model.predict_logit(X[slt_train_idx]), y_slt[slt_train_idx])
        if len(win_calib_idx) > 0:
            win_model.set_calibration(win_model.predict_logit(X[win_calib_idx]), y_win[win_calib_idx])
        else:
            win_model.set_calibration(win_model.predict_logit(X[win_train_idx]), y_win[win_train_idx])

        slt_probs = slt_model.predict_proba(X[slt_test_idx])
        win_probs = win_model.predict_proba(X[win_test_idx])

        slt_test_y = y_slt[slt_test_idx]
        win_test_y = y_win[win_test_idx]
        slt_metrics = self._metrics(slt_test_y, slt_probs)
        win_metrics = self._metrics(win_test_y, win_probs)
        slt_metrics["feature_importance"] = self._feature_importance(slt_model, X[slt_test_idx], y_slt[slt_test_idx])
        win_metrics["feature_importance"] = self._feature_importance(win_model, X[win_test_idx], y_win[win_test_idx])
        temporal_validation = {
            "slt": self._temporal_breakdown(slt_test_y, slt_probs, dates[slt_test_idx], granularity="month"),
            "win": self._temporal_breakdown(win_test_y, win_probs, dates[win_test_idx], granularity="month"),
        }

        bundle = {
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "feature_names": self.FEATURE_NAMES,
            "models": {
                "slt": slt_model.to_dict(),
                "win": win_model.to_dict(),
            },
            "dataset": samples["summary"],
            "metrics": {
                "slt": slt_metrics,
                "win": win_metrics,
            },
            "summary": self._build_summary(samples["summary"], slt_metrics, win_metrics, slt_model, win_model, temporal_validation),
        }
        self._bundle = bundle
        self._write_bundle(bundle)
        self._write_summary(bundle["summary"])
        await self._store_validation_record(bundle)
        return bundle["summary"]

    async def predict(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        bundle = await self._ensure_bundle()
        if not bundle:
            return self._fallback_prediction(payload)

        slt_model = PortableBoostingModel.from_dict(bundle["models"]["slt"])
        win_model = PortableBoostingModel.from_dict(bundle["models"]["win"])
        features, context = await self._context_features(payload)
        if features is None:
            return self._fallback_prediction(payload)

        row = np.asarray(features, dtype=float).reshape(1, -1)
        slt_prob = float(slt_model.predict_proba(row)[0])
        win_prob = float(win_model.predict_proba(row)[0])
        slt_prob, win_prob = self._blend_sparse_history_probabilities(slt_prob, win_prob, context)
        slt_risk = self._risk_bucket(slt_prob)
        win_bucket = self._confidence_bucket(win_prob, context["evidence_score"])
        slt_factors = slt_model.top_factors(features)
        win_factors = win_model.top_factors(features)
        explanation = await self._build_explanation(payload, context, slt_prob, win_prob, slt_factors, win_factors)
        return {
            "trained": True,
            "model_version": "ppr-boosted-stumps-v1",
            "slt": {
                "probability": round(slt_prob, 4),
                "risk": slt_risk,
                "threshold": 0.70,
                "factors": slt_factors,
            },
            "win": {
                "probability": round(win_prob, 4),
                "confidence": win_bucket,
                "factors": win_factors,
            },
            "confidence": win_bucket,
            "evidence": context,
            "explanation": explanation,
        }

    async def model_report(self) -> Dict[str, Any]:
        bundle = await self._ensure_bundle()
        if not bundle:
            return {
                "trained": False,
                "summary": self._fallback_summary(),
            }
        summary = dict(bundle["summary"])
        summary.setdefault("calibration", self._calibration_from_bundle(bundle))
        summary.setdefault("audit", self._audit_training_quality(bundle.get("dataset", {}), bundle.get("metrics", {}).get("slt", {}), bundle.get("metrics", {}).get("win", {}), PortableBoostingModel.from_dict(bundle["models"]["slt"]), PortableBoostingModel.from_dict(bundle["models"]["win"])))
        summary.setdefault("split_policy", {
            "type": "time_based_regime_holdout",
            "primary_validation_regime": REGIME_PPR2025,
            "auxiliary_training_regime": "PPR2008",
        })
        return {
            "trained": True,
            "summary": summary,
            "metrics": bundle["metrics"],
            "dataset": bundle["dataset"],
            "trained_at": bundle["trained_at"],
        }

    async def predict_market_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        return await self.predict(row)

    def _blend_sparse_history_probabilities(
        self,
        slt_prob: float,
        win_prob: float,
        context: Dict[str, Any],
    ) -> Tuple[float, float]:
        history_rows = float(context.get("contractor_history_rows", 0.0) or 0.0)
        evidence_score = float(context.get("evidence_score", 0.0) or 0.0)
        if history_rows >= 5 and evidence_score >= 0.6:
            return float(np.clip(slt_prob, 0.01, 0.99)), float(np.clip(win_prob, 0.01, 0.99))

        bid_ratio = _safe_float(context.get("bid_ratio", 1.0), 1.0)
        discount_pct = _safe_float(context.get("discount_pct", max(0.0, (1.0 - bid_ratio) * 100.0)), 0.0)
        bidder_count = int(context.get("bidder_count", 1) or 1)
        regime_bonus = 0.04 if context.get("regime") == REGIME_PPR2025 else 0.0

        win_prior = 0.24
        win_prior += min(0.18, max(0.0, discount_pct) / 120.0)
        win_prior += min(0.12, max(0.0, 6 - bidder_count) * 0.015)
        win_prior -= min(0.10, max(0.0, bid_ratio - 1.0) * 0.20)
        win_prior += regime_bonus
        win_prior = float(np.clip(win_prior, 0.05, 0.85))

        slt_prior = 0.18
        slt_prior += min(0.45, max(0.0, (0.72 - bid_ratio)) * 1.8)
        slt_prior += min(0.15, max(0.0, discount_pct - 15.0) / 100.0)
        slt_prior = float(np.clip(slt_prior, 0.03, 0.95))

        mix = float(np.clip(0.35 + evidence_score * 0.4, 0.35, 0.85))
        slt_final = mix * float(np.clip(slt_prob, 0.01, 0.99)) + (1.0 - mix) * slt_prior
        win_final = mix * float(np.clip(win_prob, 0.01, 0.99)) + (1.0 - mix) * win_prior
        return float(np.clip(slt_final, 0.01, 0.99)), float(np.clip(win_final, 0.01, 0.99))

    async def _build_explanation(
        self,
        payload: Dict[str, Any],
        context: Dict[str, Any],
        slt_prob: float,
        win_prob: float,
        slt_factors: List[Dict[str, Any]],
        win_factors: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        explanation = {
            "available": True,
            "summary": self._rule_explanation_text(context, slt_prob, win_prob),
            "engine": "rules",
        }
        client = self._ollama_client
        if client is None:
            client = OllamaClient()
            self._ollama_client = client
        try:
            if not await client.is_available():
                return explanation
            prompt = (
                "Summarize this Bangladesh PPR 2025 tender scoring result in 3 short bullet points. "
                "Focus on why the win probability and SLT risk are high or low, using plain procurement language. "
                "Do not mention code internals. Return concise prose only.\n\n"
                f"Estimate: {payload.get('estimated_cost', payload.get('official_estimate', 0))}\n"
                f"Bid price: {payload.get('bid_price', payload.get('quoted_bid_price', 0))}\n"
                f"Bidder count: {context.get('bidder_count', 0)}\n"
                f"Regime: {context.get('regime', 'unknown')}\n"
                f"SLT probability: {slt_prob:.4f}\n"
                f"Win probability: {win_prob:.4f}\n"
                f"SLT factors: {json.dumps(slt_factors[:3])}\n"
                f"Win factors: {json.dumps(win_factors[:3])}\n"
            )
            async with httpx.AsyncClient(timeout=8.0) as http:
                response = await http.post(
                    f"{client.base_url}/api/chat",
                    json={
                        "model": client.model,
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "You are a procurement analytics assistant. "
                                    "Explain scoring results clearly and briefly for a tender dashboard."
                                ),
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "stream": False,
                    },
                )
                if response.status_code != 200:
                    return explanation
                result = response.json()
            content = result.get("message", {}).get("content", "")
            if content:
                explanation.update(
                    {
                        "available": True,
                        "summary": content.strip(),
                        "engine": f"ollama/{client.model}",
                    }
                )
        except Exception:
            return explanation
        return explanation

    def _rule_explanation_text(self, context: Dict[str, Any], slt_prob: float, win_prob: float) -> str:
        bid_ratio = float(context.get("bid_ratio", 1.0) or 1.0)
        discount_pct = float(context.get("discount_pct", 0.0) or 0.0)
        bidder_count = int(context.get("bidder_count", 1) or 1)
        contractor_history_rows = float(context.get("contractor_history_rows", 0.0) or 0.0)
        regime = context.get("regime", "unknown")
        evidence_score = float(context.get("evidence_score", 0.0) or 0.0)
        reason_bits = []
        if bid_ratio >= 0.85:
            reason_bits.append("the bid is relatively close to the estimate")
        else:
            reason_bits.append("the bid is materially below the estimate")
        if bidder_count <= 2:
            reason_bits.append("competition is thin")
        elif bidder_count >= 6:
            reason_bits.append("competition is broader than average")
        if contractor_history_rows < 5:
            reason_bits.append("contractor history is sparse")
        else:
            reason_bits.append("contractor history is available")
        if regime == REGIME_PPR2025:
            reason_bits.append("PPR 2025 regime applies")
        lead = f"SLT risk is {self._risk_bucket(slt_prob)} at {slt_prob * 100:.1f}% and win probability is {win_prob * 100:.1f}%."
        tail = f" Key signals: {', '.join(reason_bits)}. Discount is {discount_pct:.1f}% and evidence score is {evidence_score:.2f}."
        return lead + tail

    async def _ensure_bundle(self) -> Optional[Dict[str, Any]]:
        if self._bundle is not None:
            return self._bundle
        self._bundle = await self._load_bundle()
        return self._bundle

    async def _load_bundle(self) -> Optional[Dict[str, Any]]:
        if self._bundle is not None:
            return self._bundle
        if not self.artifact_path.exists():
            return None
        try:
            self._bundle = json.loads(self.artifact_path.read_text(encoding="utf-8"))
        except Exception:
            self._bundle = None
        return self._bundle

    def _write_bundle(self, bundle: Dict[str, Any]) -> None:
        self.artifact_path.write_text(json.dumps(_jsonable(bundle), indent=2), encoding="utf-8")

    def _write_summary(self, summary: Dict[str, Any]) -> None:
        self.summary_path.write_text(json.dumps(_jsonable(summary), indent=2), encoding="utf-8")

    def _fallback_summary(self) -> Dict[str, Any]:
        return {
            "trained": False,
            "message": "Model not trained yet; using rule engine only",
            "recommended_action": "Train the PPR ML bundle",
        }

    def _calibration_from_bundle(self, bundle: Dict[str, Any]) -> Dict[str, Any]:
        slt_model = PortableBoostingModel.from_dict(bundle["models"]["slt"])
        win_model = PortableBoostingModel.from_dict(bundle["models"]["win"])
        return {
            "slt": {
                "a": round(float(slt_model.calibration_a), 6),
                "b": round(float(slt_model.calibration_b), 6),
                "training_rows": int(slt_model.training_rows),
            },
            "win": {
                "a": round(float(win_model.calibration_a), 6),
                "b": round(float(win_model.calibration_b), 6),
                "training_rows": int(win_model.training_rows),
            },
        }

    def _fallback_prediction(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        estimate = _safe_float(payload.get("estimated_cost", payload.get("estimate", 0)))
        bid_price = _safe_float(payload.get("bid_price", 0))
        ratio = bid_price / estimate if estimate > 0 and bid_price > 0 else 1.0
        discount_pct = max(0.0, (1.0 - ratio) * 100.0)
        bidder_count = int(payload.get("bidder_count", payload.get("responsive_bidders_count", 1)) or 1)
        slt_prob = min(0.95, max(0.05, 1.2 - ratio))
        win_prob = min(0.95, max(0.05, 0.45 + (0.15 if discount_pct >= 5 else 0.0) + min(bidder_count, 10) * 0.02))
        evidence = {
            "bid_ratio": round(ratio, 4),
            "discount_pct": round(discount_pct, 2),
            "bidder_count": bidder_count,
        }
        return {
            "trained": False,
            "model_version": "rule-fallback",
            "slt": {
                "probability": round(slt_prob, 4),
                "risk": self._risk_bucket(slt_prob),
                "threshold": 0.70,
                "factors": [],
            },
            "win": {
                "probability": round(win_prob, 4),
                "confidence": "low" if bidder_count < 3 else "medium",
                "factors": [],
            },
            "confidence": "low" if bidder_count < 3 else "medium",
            "evidence": evidence,
        }

    async def _context_features(self, payload: Dict[str, Any]) -> Tuple[Optional[List[float]], Dict[str, Any]]:
        estimate = _safe_float(payload.get("estimated_cost", payload.get("official_estimate", payload.get("estimate", 0))))
        bid_price = _safe_float(payload.get("bid_price", payload.get("quoted_bid_price", 0)))
        if estimate <= 0:
            return None, {"reason": "missing_estimate", "evidence_score": 0.0}

        bidders = _safe_json_loads(payload.get("bidders", payload.get("responsive_bidders", [])))
        bidder_count = int(payload.get("bidder_count", len(bidders) or payload.get("responsive_bidders_count", 1)) or 1)

        bid_ratio = bid_price / estimate if bid_price > 0 else _safe_float(payload.get("bid_ratio", 1.0))
        bid_ratio = max(0.05, min(1.8, bid_ratio))
        discount_pct = max(0.0, (1.0 - bid_ratio) * 100.0)
        regime = payload.get("regime") or get_regime(payload.get("tender_open_date") or payload.get("opening_date"))

        bidder_ratios: List[float] = []
        slt_count = 0
        alt_count = 0
        nr_count = 0
        winner_name = _normalize_name(payload.get("winner_name") or payload.get("winner") or payload.get("winner_contractor"))
        contractor_name = _normalize_name(payload.get("contractor_name") or payload.get("bidder_name") or payload.get("company_name"))
        for bidder in bidders or []:
            if not isinstance(bidder, dict):
                continue
            amount = _safe_float(
                bidder.get("quoted_amount")
                or bidder.get("quoted_price")
                or bidder.get("bid_amount")
                or bidder.get("final_amount")
                or bidder.get("amount")
            )
            if amount <= 0:
                continue
            ratio = amount / estimate
            bidder_ratios.append(ratio)
            status = _normalize_text(bidder.get("status"))
            if ratio < 0.70 or status in {"slt", "alt", "non_responsive"}:
                slt_count += 1
            if ratio < 0.60 or status == "alt":
                alt_count += 1
            if status in {"non_responsive", "rejected"}:
                nr_count += 1

        if bidder_ratios:
            bidder_ratios = sorted(bidder_ratios)
            bid_rank_pct = (sum(1 for r in bidder_ratios if r <= bid_ratio) / len(bidder_ratios))
            gap_to_min = bid_ratio - bidder_ratios[0]
            gap_to_median = bid_ratio - float(np.median(np.asarray(bidder_ratios, dtype=float)))
            opening_mean = float(np.mean(bidder_ratios))
            opening_std = float(np.std(bidder_ratios))
        else:
            bid_rank_pct = 1.0
            gap_to_min = 0.0
            gap_to_median = 0.0
            opening_mean = bid_ratio
            opening_std = 0.0

        contractor_prior = await self._contractor_prior(contractor_name or winner_name or payload.get("contractor_name"))
        agency_prior = await self._agency_prior(payload.get("agency") or payload.get("agency_code"))
        zone_prior = await self._zone_prior(payload.get("zone") or payload.get("division"))

        evidence = {
            "bid_ratio": round(bid_ratio, 4),
            "discount_pct": round(discount_pct, 2),
            "bidder_count": bidder_count,
            "regime": regime,
            "opening_bidder_count": len(bidder_ratios),
            "contractor_history_rows": contractor_prior["bid_count"],
        }
        evidence_score = 0.25
        evidence_score += min(0.25, len(bidder_ratios) / 12.0)
        evidence_score += min(0.25, contractor_prior["bid_count"] / 25.0)
        evidence_score += min(0.25, agency_prior["bid_count"] / 40.0)

        features = [
            bid_ratio,
            discount_pct,
            float(bidder_count),
            float(bid_rank_pct),
            float(gap_to_min),
            float(gap_to_median),
            float(opening_mean),
            float(opening_std),
            float(slt_count / max(len(bidder_ratios), 1)),
            float(alt_count / max(len(bidder_ratios), 1)),
            float(nr_count / max(len(bidder_ratios), 1)),
            1.0 if slt_count > 0 else 0.0,
            1.0 if alt_count > 0 else 0.0,
            float(contractor_prior["bid_count"]),
            float(contractor_prior["win_rate"]),
            float(contractor_prior["avg_ratio"]),
            float(contractor_prior["avg_discount"]),
            float(contractor_prior["agency_affinity"]),
            float(contractor_prior["zone_affinity"]),
            float(agency_prior["bid_count"]),
            float(agency_prior["slt_rate"]),
            float(agency_prior["avg_ratio"]),
            float(zone_prior["bid_count"]),
            float(zone_prior["slt_rate"]),
            float(zone_prior["avg_ratio"]),
            1.0 if regime == REGIME_PPR2025 else 0.0,
        ]
        return features, {
            **evidence,
            "evidence_score": round(float(min(evidence_score, 1.0)), 4),
            "contractor_prior": contractor_prior,
            "agency_prior": agency_prior,
            "zone_prior": zone_prior,
            "winner_present": bool(winner_name or payload.get("winner")),
            "candidate_name": contractor_name or winner_name,
        }

    async def _contractor_prior(self, contractor_name: Any) -> Dict[str, float]:
        name = _normalize_name(contractor_name)
        if not name:
            return {"bid_count": 0.0, "win_rate": 0.0, "avg_ratio": 0.0, "avg_discount": 0.0, "agency_affinity": 0.0, "zone_affinity": 0.0}
        if self.db is not None:
            try:
                stmt = select(IntelContractor).where(IntelContractor.contractor_name.ilike(f"%{contractor_name}%"))
                row = (await self.db.execute(stmt)).scalars().first()
                if row:
                    agencies_worked = row.agencies_worked or []
                    districts_worked = row.districts_worked or []
                    agency_affinity = len(agencies_worked) if isinstance(agencies_worked, (list, tuple, set, dict)) else 0
                    zone_affinity = len(districts_worked) if isinstance(districts_worked, (list, tuple, set, dict)) else 0
                    avg_npp = float(row.avg_npp or 0.0)
                    avg_discount = max(0.0, min(40.0, (1.0 - avg_npp) * 100.0))
                    return {
                        "bid_count": float(row.total_contracts or 0),
                        "win_rate": float(max(0.05, min(0.95, 1.0 - avg_npp))),
                        "avg_ratio": float(max(0.05, min(1.8, avg_npp or 1.0))),
                        "avg_discount": float(avg_discount),
                        "agency_affinity": float(agency_affinity),
                        "zone_affinity": float(zone_affinity),
                    }
            except Exception:
                pass
        return {"bid_count": 0.0, "win_rate": 0.0, "avg_ratio": 0.0, "avg_discount": 0.0, "agency_affinity": 0.0, "zone_affinity": 0.0}

    async def _agency_prior(self, agency: Any) -> Dict[str, float]:
        agency_text = _normalize_text(agency)
        if not agency_text:
            return {"bid_count": 0.0, "slt_rate": 0.0, "avg_ratio": 0.0}
        cached = self._agency_prior_cache.get(agency_text)
        if cached is not None:
            return cached
        if self.db is None:
            return {"bid_count": 0.0, "slt_rate": 0.0, "avg_ratio": 0.0}
        try:
            ratio_expr = func.coalesce(
                func.nullif(ProcurementLifecycle.npp_ratio, 0.0),
                ProcurementLifecycle.award_amount_bdt / func.nullif(ProcurementLifecycle.estimated_cost_bdt, 0.0),
                0.0,
            )
            stmt = (
                select(
                    func.count().label("count"),
                    func.avg(func.nullif(ratio_expr, 0.0)).label("avg_ratio"),
                    func.avg(case((ratio_expr <= 0.70, 1.0), else_=0.0)).label("slt_rate"),
                )
                .where(ProcurementLifecycle.agency_code.ilike(f"%{agency_text}%"))
            )
            count, avg_ratio, slt_rate = (await self.db.execute(stmt)).one()
            result = {
                "bid_count": float(count),
                "slt_rate": float(slt_rate or 0.0),
                "avg_ratio": float(max(0.05, min(1.8, float(avg_ratio or 0.0)))),
            }
            self._agency_prior_cache[agency_text] = result
            return result
        except Exception:
            if self.db is not None:
                try:
                    await self.db.rollback()
                except Exception:
                    pass
            return {"bid_count": 0.0, "slt_rate": 0.0, "avg_ratio": 0.0}

    async def _zone_prior(self, zone: Any) -> Dict[str, float]:
        zone_text = _normalize_text(zone)
        if not zone_text:
            return {"bid_count": 0.0, "slt_rate": 0.0, "avg_ratio": 0.0}
        cached = self._zone_prior_cache.get(zone_text)
        if cached is not None:
            return cached
        if self.db is None:
            return {"bid_count": 0.0, "slt_rate": 0.0, "avg_ratio": 0.0}
        try:
            ratio_expr = func.coalesce(
                func.nullif(ProcurementLifecycle.npp_ratio, 0.0),
                ProcurementLifecycle.award_amount_bdt / func.nullif(ProcurementLifecycle.estimated_cost_bdt, 0.0),
                0.0,
            )
            stmt = (
                select(
                    func.count().label("count"),
                    func.avg(func.nullif(ratio_expr, 0.0)).label("avg_ratio"),
                    func.avg(case((ratio_expr <= 0.70, 1.0), else_=0.0)).label("slt_rate"),
                )
                .where(ProcurementLifecycle.zone_name.ilike(f"%{zone_text}%"))
            )
            count, avg_ratio, slt_rate = (await self.db.execute(stmt)).one()
            result = {
                "bid_count": float(count),
                "slt_rate": float(slt_rate or 0.0),
                "avg_ratio": float(max(0.05, min(1.8, float(avg_ratio or 0.0)))),
            }
            self._zone_prior_cache[zone_text] = result
            return result
        except Exception:
            if self.db is not None:
                try:
                    await self.db.rollback()
                except Exception:
                    pass
            return {"bid_count": 0.0, "slt_rate": 0.0, "avg_ratio": 0.0}

    async def _load_lifecycle_priors(self) -> Dict[str, Dict[str, Dict[str, float]]]:
        if self.db is None:
            return {"agencies": {}, "zones": {}}
        try:
            cutoff = PPR_REGIME_CUTOFF_DATE
            ratio_expr = func.coalesce(
                func.nullif(ProcurementLifecycle.npp_ratio, 0.0),
                ProcurementLifecycle.award_amount_bdt / func.nullif(ProcurementLifecycle.estimated_cost_bdt, 0.0),
                0.0,
            )
            agencies = {}
            agency_rows = (
                await self.db.execute(
                    select(
                        ProcurementLifecycle.agency_code.label("agency_code"),
                        func.count().label("count"),
                        func.avg(func.nullif(ratio_expr, 0.0)).label("avg_ratio"),
                        func.avg(case((ratio_expr <= 0.70, 1.0), else_=0.0)).label("slt_rate"),
                    )
                    .where(
                        ProcurementLifecycle.agency_code.isnot(None),
                        ProcurementLifecycle.award_date.isnot(None),
                        ProcurementLifecycle.award_date < cutoff,
                    )
                    .group_by(ProcurementLifecycle.agency_code)
                )
            ).all()
            for agency_code, count, avg_ratio, slt_rate in agency_rows:
                key = _normalize_text(agency_code)
                if key:
                    agencies[key] = {
                        "bid_count": float(count or 0),
                        "slt_rate": float(slt_rate or 0.0),
                        "avg_ratio": float(max(0.05, min(1.8, float(avg_ratio or 0.0)))),
                    }

            zones = {}
            zone_rows = (
                await self.db.execute(
                    select(
                        ProcurementLifecycle.zone_name.label("zone_name"),
                        func.count().label("count"),
                        func.avg(func.nullif(ratio_expr, 0.0)).label("avg_ratio"),
                        func.avg(case((ratio_expr <= 0.70, 1.0), else_=0.0)).label("slt_rate"),
                    )
                    .where(
                        ProcurementLifecycle.zone_name.isnot(None),
                        ProcurementLifecycle.award_date.isnot(None),
                        ProcurementLifecycle.award_date < cutoff,
                    )
                    .group_by(ProcurementLifecycle.zone_name)
                )
            ).all()
            for zone_name, count, avg_ratio, slt_rate in zone_rows:
                key = _normalize_text(zone_name)
                if key:
                    zones[key] = {
                        "bid_count": float(count or 0),
                        "slt_rate": float(slt_rate or 0.0),
                        "avg_ratio": float(max(0.05, min(1.8, float(avg_ratio or 0.0)))),
                    }
            return {"agencies": agencies, "zones": zones}
        except Exception:
            if self.db is not None:
                try:
                    await self.db.rollback()
                except Exception:
                    pass
            return {"agencies": {}, "zones": {}}

    async def _build_samples(self) -> Dict[str, Any]:
        if self.db is None:
            return {"rows": [], "summary": {"rows": 0, "regime_counts": {}, "source": "none"}}

        contractor_priors = await self._load_contractor_priors()
        award_lookup = await self._load_award_lookup()
        lifecycle_priors = await self._load_lifecycle_priors()
        samples: List[Dict[str, Any]] = []
        regime_counts: Dict[str, int] = {"PPR2008": 0, "PPR2025": 0}

        def add_lifecycle_sample(row: ProcurementLifecycle, weight: float = 1.0) -> None:
            estimate = _safe_float(row.estimated_cost_bdt)
            award_amount = _safe_float(row.award_amount_bdt)
            observed_ratio = _safe_float(row.npp_ratio)
            has_win = bool(row.winner) or award_amount > 0 or observed_ratio > 0
            ratio = observed_ratio
            sort_date = _coerce_datetime(row.award_date) or _coerce_datetime(row.created_at)
            regime = get_regime(sort_date or row.award_date or row.created_at)
            if estimate > 0 and award_amount > 0:
                ratio = award_amount / estimate
            if ratio <= 0 and estimate > 0:
                ratio = award_amount / estimate if award_amount > 0 else 1.0
            ratio = float(max(0.05, min(1.8, ratio or 1.0)))
            discount_pct = max(0.0, (1.0 - ratio) * 100.0)
            agency = _normalize_text(row.agency_code)
            zone = _normalize_text(row.zone_name)
            winner_name = _normalize_name(row.winner or award_lookup.get(row.tender_id or "", ""))
            contractor_state = self._seeded_contractor_state({}, winner_name)
            agency_state = lifecycle_priors["agencies"].get(agency, self._empty_agency_state())
            zone_state = lifecycle_priors["zones"].get(zone, self._empty_zone_state())
            procurement_method = _normalize_text(row.procurement_method)
            bidder_count = 1 + int(min(8.0, max(0.0, math.log10(max(estimate, 1.0)) - 4.0)))
            if procurement_method in {"otm", "lcm", "ltm"}:
                bidder_count += 1
            if agency in {"lged", "pwd", "bwdb"}:
                bidder_count += 1
            bidder_count = max(1, min(12, bidder_count))
            opening_mean = float(agency_state["avg_ratio"] or zone_state["avg_ratio"] or ratio)
            opening_std = float(min(0.35, abs(ratio - opening_mean) / 2.0 + 0.02))
            bid_rank_pct = float(min(1.0, max(0.05, ratio + (0.06 if contractor_state["win_rate"] > 0 else 0.0))))
            gap_to_min = float(max(-0.2, ratio - max(0.55, opening_mean - 0.05)))
            gap_to_median = float(ratio - (zone_state["avg_ratio"] or opening_mean))
            slt_share = 1.0 if ratio <= 0.70 else 0.0
            alt_share = 1.0 if ratio <= 0.60 else 0.0
            non_responsive_share = 1.0 if ratio <= 0.45 and not winner_name else 0.0
            features = [
                ratio,
                discount_pct,
                float(bidder_count),
                bid_rank_pct,
                gap_to_min,
                gap_to_median,
                opening_mean,
                opening_std,
                slt_share,
                alt_share,
                non_responsive_share,
                slt_share,
                alt_share,
                float(contractor_state["bid_count"]),
                float(contractor_state["win_rate"]),
                float(contractor_state["avg_ratio"]),
                float(contractor_state["avg_discount"]),
                float(contractor_state["agency_affinity"]),
                float(contractor_state["zone_affinity"]),
                float(agency_state["bid_count"]),
                float(agency_state["slt_rate"]),
                float(agency_state["avg_ratio"]),
                float(zone_state["bid_count"]),
                float(zone_state["slt_rate"]),
                float(zone_state["avg_ratio"]),
                1.0 if regime == REGIME_PPR2025 else 0.0,
            ]
            samples.append(
                {
                    "tender_id": row.tender_id or row.package_no,
                    "tender_date": row.award_date or (sort_date.date().isoformat() if sort_date else None),
                    "sort_key": _coerce_date_key(row.award_date or row.created_at),
                    "regime": regime,
                    "agency": agency,
                    "zone": zone,
                    "candidate": winner_name,
                    "winner": winner_name,
                    "features": features,
                    "win_label": 1 if has_win else 0,
                    "slt_label": 1 if ratio <= 0.70 else 0,
                    "weight": weight,
                }
            )
            regime_counts[regime] = regime_counts.get(regime, 0) + 1

        positive_stmt = (
            select(ProcurementLifecycle)
            .where(
                (ProcurementLifecycle.winner.isnot(None))
                | (ProcurementLifecycle.award_amount_bdt > 0)
                | (ProcurementLifecycle.npp_ratio > 0)
            )
            .order_by(ProcurementLifecycle.award_date.asc().nulls_last(), ProcurementLifecycle.package_no.asc())
        )
        recent_positive_stmt = positive_stmt.where(
            (ProcurementLifecycle.award_date.is_(None)) | (ProcurementLifecycle.award_date >= "2025-09-28")
        ).limit(50000)
        historical_positive_stmt = positive_stmt.where(ProcurementLifecycle.award_date < "2025-09-28").limit(40000)
        negative_stmt = (
            select(ProcurementLifecycle)
            .where(
                (ProcurementLifecycle.winner.is_(None))
                & (ProcurementLifecycle.award_amount_bdt <= 0)
                & (ProcurementLifecycle.npp_ratio <= 0)
            )
            .order_by(ProcurementLifecycle.package_no.asc())
            .limit(50000)
        )
        historical_positive_rows = (await self.db.execute(historical_positive_stmt)).scalars().all()
        recent_positive_rows = (await self.db.execute(recent_positive_stmt)).scalars().all()
        negative_rows = (await self.db.execute(negative_stmt)).scalars().all()

        for row in historical_positive_rows:
            add_lifecycle_sample(row, weight=1.0)
        for row in recent_positive_rows:
            add_lifecycle_sample(row, weight=1.0)
        for row in negative_rows:
            add_lifecycle_sample(row, weight=0.7)

        opening_rows = (await self.db.execute(select(OpeningReport))).scalars().all()
        opening_rows.sort(key=lambda report: ((_coerce_datetime(report.opening_date) or datetime(2000, 1, 1, tzinfo=timezone.utc)).timestamp(), report.tender_id or ""))

        history: Dict[str, Dict[str, Any]] = {
            "contractors": {},
            "agencies": {},
            "zones": {},
        }
        for report in opening_rows:
            opening_date = _coerce_datetime(report.opening_date)
            if not opening_date:
                continue
            estimate = _safe_float(report.estimated_amount_bdt)
            if estimate <= 0:
                continue
            regime = get_regime(opening_date)
            regime_counts[regime] = regime_counts.get(regime, 0) + 1
            bidders = _safe_json_loads(report.bidders)
            if not isinstance(bidders, list) or not bidders:
                continue
            bidder_records = self._parse_bidders(bidders, estimate)
            if not bidder_records:
                continue

            bidder_ratios = [item["ratio"] for item in bidder_records]
            bidder_ratios_sorted = sorted(bidder_ratios)
            opening_mean = float(np.mean(bidder_ratios))
            opening_std = float(np.std(bidder_ratios))
            winner_name = _normalize_name(report.winner_name)
            if not winner_name:
                winner_name = _normalize_name(award_lookup.get(report.tender_id, ""))

            tender_agency = _normalize_text(report.agency)
            tender_zone = _normalize_text(report.zone)

            for bidder in bidder_records:
                normalized_bidder = _normalize_name(bidder["name"])
                contractor_state = history["contractors"].get(normalized_bidder, self._seeded_contractor_state(contractor_priors, normalized_bidder))
                agency_state = history["agencies"].get(tender_agency, self._empty_agency_state())
                zone_state = history["zones"].get(tender_zone, self._empty_zone_state())
                rank_pct = bidder["rank"] / max(len(bidder_records), 1)
                feature_row = [
                    bidder["ratio"],
                    bidder["discount_pct"],
                    float(len(bidder_records)),
                    float(rank_pct),
                    float(bidder["ratio"] - bidder_ratios_sorted[0]),
                    float(bidder["ratio"] - float(np.median(np.asarray(bidder_ratios_sorted, dtype=float)))),
                    opening_mean,
                    opening_std,
                    float(sum(1 for item in bidder_records if item["ratio"] < 0.70) / len(bidder_records)),
                    float(sum(1 for item in bidder_records if item["ratio"] < 0.60) / len(bidder_records)),
                    float(sum(1 for item in bidder_records if item["status"] in {"non_responsive", "rejected"}) / len(bidder_records)),
                    1.0 if report.has_slt else 0.0,
                    1.0 if report.has_alt else 0.0,
                    float(contractor_state["bid_count"]),
                    float(contractor_state["win_rate"]),
                    float(contractor_state["avg_ratio"]),
                    float(contractor_state["avg_discount"]),
                    float(contractor_state["agency_affinity"]),
                    float(contractor_state["zone_affinity"]),
                    float(agency_state["bid_count"]),
                    float(agency_state["slt_rate"]),
                    float(agency_state["avg_ratio"]),
                    float(zone_state["bid_count"]),
                    float(zone_state["slt_rate"]),
                    float(zone_state["avg_ratio"]),
                    1.0 if regime == REGIME_PPR2025 else 0.0,
                ]
                is_winner = 1 if (winner_name and _best_name_match(bidder["name"], winner_name)) else 0
                slt_label = 1 if (bidder["ratio"] <= 0.70 or report.has_slt or report.has_alt or bidder["status"] in {"slt", "alt", "non_responsive"}) else 0
                samples.append(
                    {
                        "tender_id": report.tender_id,
                        "tender_date": opening_date.date().isoformat(),
                        "sort_key": float(opening_date.timestamp()),
                        "regime": regime,
                        "agency": tender_agency,
                        "zone": tender_zone,
                        "candidate": normalized_bidder,
                        "winner": winner_name,
                        "features": feature_row,
                        "win_label": is_winner,
                        "slt_label": slt_label,
                        "weight": 3.0,
                    }
                )

            self._advance_history(history, tender_agency, tender_zone, bidder_records, opening_mean, winner_name)

        summary = {
            "rows": len(samples),
            "regime_counts": regime_counts,
            "source": "procurement_lifecycle+opening_reports",
            "lifecycle_rows": len(historical_positive_rows) + len(recent_positive_rows) + len(negative_rows),
            "opening_report_rows": len(opening_rows),
            "contractor_prior_rows": len(contractor_priors),
        }
        return {"rows": samples, "summary": summary}

    async def _load_contractor_priors(self) -> Dict[str, Dict[str, Any]]:
        priors: Dict[str, Dict[str, Any]] = {}
        if self.db is None:
            return priors
        try:
            result = await self.db.execute(select(IntelContractor))
            for row in result.scalars().all():
                agencies_worked = row.agencies_worked or []
                districts_worked = row.districts_worked or []
                agency_affinity = len(agencies_worked) if isinstance(agencies_worked, (list, tuple, set, dict)) else 0
                zone_affinity = len(districts_worked) if isinstance(districts_worked, (list, tuple, set, dict)) else 0
                avg_npp = float(row.avg_npp or 0.0)
                priors[_normalize_name(row.contractor_name)] = {
                    "bid_count": float(row.total_contracts or 0),
                    "win_rate": float(max(0.05, min(0.95, 1.0 - avg_npp))),
                    "avg_ratio": float(max(0.05, min(1.8, avg_npp or 1.0))),
                    "avg_discount": float(max(0.0, min(40.0, (1.0 - avg_npp) * 100.0))),
                    "agency_affinity": float(agency_affinity),
                    "zone_affinity": float(zone_affinity),
                }
        except Exception:
            if self.db is not None:
                try:
                    await self.db.rollback()
                except Exception:
                    pass
        return priors

    def _seeded_contractor_state(self, contractor_priors: Dict[str, Dict[str, Any]], name: str) -> Dict[str, float]:
        if name and name in contractor_priors:
            return contractor_priors[name].copy()
        return {"bid_count": 0.0, "win_rate": 0.0, "avg_ratio": 1.0, "avg_discount": 0.0, "agency_affinity": 0.0, "zone_affinity": 0.0}

    @staticmethod
    def _empty_agency_state() -> Dict[str, float]:
        return {"bid_count": 0.0, "slt_rate": 0.0, "avg_ratio": 1.0}

    @staticmethod
    def _empty_zone_state() -> Dict[str, float]:
        return {"bid_count": 0.0, "slt_rate": 0.0, "avg_ratio": 1.0}

    def _advance_history(
        self,
        history: Dict[str, Dict[str, Any]],
        agency: str,
        zone: str,
        bidder_records: List[Dict[str, Any]],
        opening_mean: float,
        winner_name: str,
    ) -> None:
        agency_state = history["agencies"].setdefault(agency, self._empty_agency_state())
        zone_state = history["zones"].setdefault(zone, self._empty_zone_state())

        winner_count = 0
        slt_count = 0
        ratios = []
        for bidder in bidder_records:
            name = _normalize_name(bidder["name"])
            state = history["contractors"].setdefault(name, {"bid_count": 0.0, "win_rate": 0.0, "avg_ratio": 1.0, "avg_discount": 0.0, "agency_affinity": 0.0, "zone_affinity": 0.0, "wins": 0.0, "discount_sum": 0.0})
            ratio = float(bidder["ratio"])
            is_winner = 1 if (winner_name and _best_name_match(bidder["name"], winner_name)) else 0
            is_slt = 1 if (ratio <= 0.70 or bidder["status"] in {"slt", "alt", "non_responsive"}) else 0

            prev_bid_count = float(state.get("bid_count", 0.0))
            prev_wins = float(state.get("wins", 0.0))
            prev_ratio_sum = float(state.get("ratio_sum", state.get("avg_ratio", 1.0) * max(prev_bid_count, 1.0))) if prev_bid_count else 0.0
            prev_discount_sum = float(state.get("discount_sum", state.get("avg_discount", 0.0) * max(prev_bid_count, 1.0))) if prev_bid_count else 0.0

            state["bid_count"] = prev_bid_count + 1.0
            state["wins"] = prev_wins + float(is_winner)
            state["win_rate"] = state["wins"] / max(state["bid_count"], 1.0)
            state["ratio_sum"] = prev_ratio_sum + ratio
            state["discount_sum"] = prev_discount_sum + max(0.0, (1.0 - ratio) * 100.0)
            state["avg_ratio"] = state["ratio_sum"] / max(state["bid_count"], 1.0)
            state["avg_discount"] = state["discount_sum"] / max(state["bid_count"], 1.0)
            state["agency_affinity"] = float(state.get("agency_affinity", 0.0)) + (1.0 if agency else 0.0)
            state["zone_affinity"] = float(state.get("zone_affinity", 0.0)) + (1.0 if zone else 0.0)

            ratios.append(ratio)
            winner_count += is_winner
            slt_count += is_slt

        if ratios:
            agency_state["bid_count"] = float(agency_state.get("bid_count", 0.0)) + len(ratios)
            zone_state["bid_count"] = float(zone_state.get("bid_count", 0.0)) + len(ratios)
            agency_state["slt_rate"] = (float(agency_state.get("slt_rate", 0.0)) + slt_count / len(ratios)) / 2 if agency_state.get("bid_count", 0.0) else slt_count / len(ratios)
            zone_state["slt_rate"] = (float(zone_state.get("slt_rate", 0.0)) + slt_count / len(ratios)) / 2 if zone_state.get("bid_count", 0.0) else slt_count / len(ratios)
            agency_state["avg_ratio"] = (float(agency_state.get("avg_ratio", 1.0)) + float(np.mean(ratios))) / 2 if agency_state.get("bid_count", 0.0) else float(np.mean(ratios))
            zone_state["avg_ratio"] = (float(zone_state.get("avg_ratio", 1.0)) + float(np.mean(ratios))) / 2 if zone_state.get("bid_count", 0.0) else float(np.mean(ratios))

    def _parse_bidders(self, bidders: List[Dict[str, Any]], estimate: float) -> List[Dict[str, Any]]:
        parsed: List[Dict[str, Any]] = []
        for idx, bidder in enumerate(bidders):
            if not isinstance(bidder, dict):
                continue
            name = bidder.get("name") or bidder.get("bidder_name") or bidder.get("contractor_name") or bidder.get("company_name")
            amount = _safe_float(
                bidder.get("quoted_amount")
                or bidder.get("quoted_price")
                or bidder.get("bid_amount")
                or bidder.get("final_amount")
                or bidder.get("amount")
            )
            if not name or amount <= 0 or estimate <= 0:
                continue
            ratio = max(0.05, min(1.8, amount / estimate))
            parsed.append(
                {
                    "name": str(name),
                    "amount": amount,
                    "ratio": ratio,
                    "discount_pct": max(0.0, (1.0 - ratio) * 100.0),
                    "status": _normalize_text(bidder.get("status")),
                    "rank": idx + 1,
                }
            )
        parsed.sort(key=lambda item: item["ratio"])
        for idx, item in enumerate(parsed, start=1):
            item["rank"] = idx
        return parsed

    async def _load_award_lookup(self) -> Dict[str, str]:
        if self._award_lookup_cache:
            return self._award_lookup_cache
        if self.db is None:
            return {}
        try:
            result = await self.db.execute(select(Award.tender_id, Award.contractor_name, Award.winner))
            lookup: Dict[str, str] = {}
            for tender_id, contractor_name, winner in result.all():
                candidate = contractor_name or winner or ""
                if tender_id and candidate and str(tender_id) not in lookup:
                    lookup[str(tender_id)] = str(candidate)
            self._award_lookup_cache = lookup
        except Exception:
            if self.db is not None:
                try:
                    await self.db.rollback()
                except Exception:
                    pass
            self._award_lookup_cache = {}
        return self._award_lookup_cache

    def _split_indices(self, regimes: np.ndarray, sort_keys: np.ndarray, labels: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        idx = np.arange(len(regimes))
        p25 = idx[regimes == 0]
        ppr = idx[regimes == 1]
        labels = np.asarray(labels, dtype=int)
        if len(ppr) < 10 or len(np.unique(labels[ppr])) < 2:
            order = np.argsort(sort_keys)
            n = len(order)
            train_end = max(1, int(n * 0.7))
            calib_end = max(train_end + 1, int(n * 0.85))
            return order[:train_end], order[train_end:calib_end], order[calib_end:]
        order_ppr = ppr[np.argsort(sort_keys[ppr])]
        pos = order_ppr[labels[order_ppr] == 1]
        neg = order_ppr[labels[order_ppr] == 0]

        def split_group(group: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
            if len(group) == 0:
                empty = np.array([], dtype=int)
                return empty, empty, empty
            train_end = max(1, int(len(group) * 0.6))
            calib_end = max(train_end + 1, int(len(group) * 0.8))
            return group[:train_end], group[train_end:calib_end], group[calib_end:]

        pos_train, pos_calib, pos_test = split_group(pos)
        neg_train, neg_calib, neg_test = split_group(neg)
        train = np.concatenate([p25, pos_train, neg_train]) if len(p25) else np.concatenate([pos_train, neg_train])
        calib = np.concatenate([pos_calib, neg_calib])
        test = np.concatenate([pos_test, neg_test])
        if len(test) == 0:
            test = calib if len(calib) else train
        return train, calib, test

    def _metrics(self, y_true: np.ndarray, probs: np.ndarray) -> Dict[str, Any]:
        y_true = np.asarray(y_true, dtype=int)
        probs = np.asarray(probs, dtype=float)
        threshold = 0.5
        return {
            "auc": round(_safe_auc(y_true, probs), 4),
            "pr_auc": round(_safe_average_precision(y_true, probs), 4),
            "brier": round(_brier_score(y_true, probs), 4),
            "log_loss": round(_log_loss(y_true, probs), 4),
            "classification": _classification_report(y_true, probs, threshold=threshold),
            "positive_rate": round(float(y_true.mean()) if len(y_true) else 0.0, 4),
            "n": int(len(y_true)),
        }

    def _feature_importance(self, model: PortableBoostingModel, X: np.ndarray, y: np.ndarray) -> List[Dict[str, Any]]:
        if len(X) == 0:
            return []
        importances: Dict[str, float] = {name: 0.0 for name in self.FEATURE_NAMES}
        for row in X[: min(len(X), 250)]:
            contribs = model.feature_contributions(row)
            for feature, impact in contribs.items():
                importances[feature] += abs(float(impact))
        ranked = sorted(importances.items(), key=lambda kv: kv[1], reverse=True)
        return [{"feature": feature, "importance": round(value, 4)} for feature, value in ranked[:10]]

    def _temporal_breakdown(
        self,
        y_true: np.ndarray,
        probs: np.ndarray,
        sort_keys: np.ndarray,
        granularity: str = "month",
    ) -> List[Dict[str, Any]]:
        y_true = np.asarray(y_true, dtype=int)
        probs = np.asarray(probs, dtype=float)
        sort_keys = np.asarray(sort_keys, dtype=float)
        if len(y_true) == 0 or len(sort_keys) == 0:
            return []
        buckets: Dict[str, Dict[str, List[float]]] = {}
        for idx, ts in enumerate(sort_keys):
            if not np.isfinite(ts):
                continue
            dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
            if granularity == "quarter":
                period = f"{dt.year}-Q{((dt.month - 1) // 3) + 1}"
            else:
                period = dt.strftime("%Y-%m")
            bucket = buckets.setdefault(period, {"y": [], "p": []})
            bucket["y"].append(int(y_true[idx]))
            bucket["p"].append(float(probs[idx]))
        rows: List[Dict[str, Any]] = []
        for period, bucket in sorted(buckets.items()):
            y_bucket = np.asarray(bucket["y"], dtype=int)
            p_bucket = np.asarray(bucket["p"], dtype=float)
            rows.append(
                {
                    "period": period,
                    "n": int(len(y_bucket)),
                    "positive_rate": round(float(y_bucket.mean()) if len(y_bucket) else 0.0, 4),
                    "avg_prob": round(float(p_bucket.mean()) if len(p_bucket) else 0.0, 4),
                    "auc": round(_safe_auc(y_bucket, p_bucket), 4),
                    "pr_auc": round(_safe_average_precision(y_bucket, p_bucket), 4),
                    "brier": round(_brier_score(y_bucket, p_bucket), 4),
                    "log_loss": round(_log_loss(y_bucket, p_bucket), 4),
                }
            )
        return rows

    def _build_summary(
        self,
        dataset: Dict[str, Any],
        slt_metrics: Dict[str, Any],
        win_metrics: Dict[str, Any],
        slt_model: PortableBoostingModel,
        win_model: PortableBoostingModel,
        temporal_validation: Dict[str, Any],
    ) -> Dict[str, Any]:
        audit = self._audit_training_quality(dataset, slt_metrics, win_metrics, slt_model, win_model)
        return {
            "trained": True,
            "rows": int(dataset.get("rows", 0)),
            "regime_counts": dataset.get("regime_counts", {}),
            "model_family": "portable-monotonic-boosted-stumps",
            "split_policy": {
                "type": "time_based_regime_holdout",
                "primary_validation_regime": REGIME_PPR2025,
                "auxiliary_training_regime": "PPR2008",
            },
            "calibration": {
                "slt": {
                    "a": round(float(slt_model.calibration_a), 6),
                    "b": round(float(slt_model.calibration_b), 6),
                    "training_rows": int(slt_model.training_rows),
                },
                "win": {
                    "a": round(float(win_model.calibration_a), 6),
                    "b": round(float(win_model.calibration_b), 6),
                    "training_rows": int(win_model.training_rows),
                },
            },
            "audit": audit,
            "temporal_validation": temporal_validation,
            "validation": {
                "slt": slt_metrics,
                "win": win_metrics,
            },
            "recommendation": self._recommendation(slt_metrics, win_metrics),
        }

    def _audit_training_quality(
        self,
        dataset: Dict[str, Any],
        slt_metrics: Dict[str, Any],
        win_metrics: Dict[str, Any],
        slt_model: PortableBoostingModel,
        win_model: PortableBoostingModel,
    ) -> Dict[str, Any]:
        warnings: List[str] = []
        notes: List[str] = []
        slt_auc = _safe_float(slt_metrics.get("auc"))
        win_auc = _safe_float(win_metrics.get("auc"))
        slt_brier = _safe_float(slt_metrics.get("brier"))
        win_brier = _safe_float(win_metrics.get("brier"))
        ppr_rows = int((dataset.get("regime_counts") or {}).get(REGIME_PPR2025, 0) or 0)
        total_rows = int(dataset.get("rows", 0) or 0)
        opening_rows = int(dataset.get("opening_report_rows", 0) or 0)

        if slt_auc >= 0.995 or win_auc >= 0.995:
            warnings.append(
                "Validation metrics are near-perfect; re-check feature leakage and label construction before trusting calibration blindly."
            )
        if slt_brier <= 0.01 and win_brier <= 0.01:
            warnings.append("Extremely low Brier scores suggest the holdout may still be too easy or too closely related to the training regime.")
        if opening_rows < 20:
            warnings.append("Opening-report coverage is limited; SLT calibration can shift as more opening reports arrive.")
        if total_rows and ppr_rows / max(total_rows, 1) < 0.5:
            notes.append("PPR2008 rows still anchor part of the training set; PPR2025 is the validation focus.")
        if int(slt_model.training_rows) == 0 or int(win_model.training_rows) == 0:
            warnings.append("One of the models saw zero effective training rows.")
        return {
            "risk_level": "high" if warnings else "low",
            "warnings": warnings,
            "notes": notes,
            "slt": {
                "auc": round(float(slt_auc), 4),
                "brier": round(float(slt_brier), 4),
            },
            "win": {
                "auc": round(float(win_auc), 4),
                "brier": round(float(win_brier), 4),
            },
        }

    def _recommendation(self, slt_metrics: Dict[str, Any], win_metrics: Dict[str, Any]) -> str:
        slt_auc = _safe_float(slt_metrics.get("auc"))
        win_brier = _safe_float(win_metrics.get("brier"))
        if slt_auc >= 0.7 and win_brier <= 0.22:
            return "Use model-assisted ranking with rule-engine gate"
        if slt_auc >= 0.6:
            return "Use model for scoring, but keep manual review for borderline cases"
        return "Fallback to rule engine until more labeled PPR 2025 data accumulates"

    async def _store_validation_record(self, bundle: Dict[str, Any]) -> None:
        if self.db is None:
            return
        try:
            payload = {
                "trained_at": bundle.get("trained_at"),
                "dataset": bundle.get("dataset", {}),
                "metrics": bundle.get("metrics", {}),
            }
            existing = (
                await self.db.execute(
                    select(PPREvaluation)
                    .where(PPREvaluation.evaluation_type == "model_validation")
                    .order_by(PPREvaluation.created_at.desc())
                    .limit(1)
                )
            ).scalars().first()
            if existing:
                existing.input_data = payload
                existing.result_data = bundle.get("summary", {})
            else:
                self.db.add(
                    PPREvaluation(
                        evaluation_type="model_validation",
                        tender_id="PPR-ML",
                        input_data=payload,
                        result_data=bundle.get("summary", {}),
                    )
                )
            await self.db.commit()
        except Exception:
            try:
                await self.db.rollback()
            except Exception:
                pass

    def _risk_bucket(self, probability: float) -> str:
        if probability >= 0.75:
            return "high"
        if probability >= 0.45:
            return "medium"
        return "low"

    def _confidence_bucket(self, probability: float, evidence_score: float) -> str:
        if evidence_score < 0.35:
            return "low"
        if probability >= 0.7 and evidence_score >= 0.55:
            return "high"
        if probability >= 0.5 and evidence_score >= 0.4:
            return "medium"
        return "low"

    async def _write_validation_summary(self, summary: Dict[str, Any]) -> None:
        self._write_summary(summary)


_service_cache: Dict[int, PPRMLService] = {}


def get_ppr_ml_service(db=None) -> PPRMLService:
    key = id(db) if db is not None else 0
    service = _service_cache.get(key)
    if service is None:
        service = PPRMLService(db=db)
        _service_cache[key] = service
    return service
