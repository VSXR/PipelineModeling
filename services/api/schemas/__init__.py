from .inference import InferenceRequest, InferenceResponse
from .training import TrainingRequest, TrainingResponse
from .versioning import VersionCurrentResponse, VersionSwitchRequest, VersionSwitchResponse

__all__ = [
    "InferenceRequest",
    "InferenceResponse",
    "TrainingRequest",
    "TrainingResponse",
    "VersionCurrentResponse",
    "VersionSwitchRequest",
    "VersionSwitchResponse",
]
