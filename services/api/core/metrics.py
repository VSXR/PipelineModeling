from prometheus_client import Counter, Gauge, Histogram

MODEL_LOADED = Gauge(
    "pipeline_model_loaded",
    "1 when a model is resident in memory, 0 during hot-swap",
)

INFERENCE_REQUESTS = Counter(
    "pipeline_inference_requests_total",
    "Cumulative inference requests by outcome",
    ["status"],
)

INFERENCE_LATENCY = Histogram(
    "pipeline_inference_latency_seconds",
    "End-to-end inference latency (model lock + predict + serialise)",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
)

TRAINING_REQUESTS = Counter(
    "pipeline_training_requests_total",
    "Cumulative partial-fit requests by outcome",
    ["status"],
)

TRAINING_SAMPLES = Counter(
    "pipeline_training_samples_total",
    "Cumulative samples consumed by partial_fit",
)

DATA_DRIFT_SCORE = Gauge(
    "pipeline_data_drift_score",
    "Normalised mean-shift drift score relative to reference distribution",
    ["feature"],
)

VERSION_SWITCHES = Counter(
    "pipeline_version_switches_total",
    "Cumulative DVC-backed model version switches by outcome",
    ["status"],
)

MODEL_LOAD_DURATION = Histogram(
    "pipeline_model_load_duration_seconds",
    "Wall-clock time for a DVC pull + joblib reload during version switch",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)
