"""Runtime loader for the optional trained fire classifier."""

from pathlib import Path
import logging

logger = logging.getLogger(__name__)
MODEL_PATH = Path(__file__).with_name("fire_classifier.pkl")
_MODEL = None

try:
    if MODEL_PATH.exists():
        import joblib
        _MODEL = joblib.load(MODEL_PATH)
        logger.info("Loaded optional ML classifier from %s", MODEL_PATH)
except Exception:
    logger.exception("Could not load optional ML classifier")
    _MODEL = None


def model_available():
    """Whether a model was successfully loaded during module import."""
    return _MODEL is not None


def classify_with_model(distance, persistence, frp, facility_type=None):
    """Return ``(label, confidence)`` from the persisted sklearn pipeline."""
    if _MODEL is None:
        raise RuntimeError("ML classifier model is not available")
    row = {
        "distance_m": float(distance if distance is not None else 999999),
        "persistence_count": float(persistence or 0),
        "frp": float(frp or 0),
        "facility_type": facility_type or "unknown",
        "hour": 0,
        "month": 0,
    }
    prediction = _MODEL.predict([row])[0]
    probabilities = _MODEL.predict_proba([row])[0]
    confidence = float(max(probabilities))
    return str(prediction), confidence
