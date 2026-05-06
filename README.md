PipelineModeling/
│
├── .dvcignore
├── .env.example
├── .gitignore
├── docker-compose.yml
├── dvc.yaml
│
├── data/
│
├── model/
│   ├── requirements.txt
│   ├── train.py
│   └── weights/
│       └── .gitkeep
│
├── monitoring/
│   ├── grafana/
│   │   └── provisioning/
│   │       ├── dashboards/
│   │       │   └── dashboard.yml
│   │       └── datasources/
│   │           └── datasource.yml
│   └── prometheus/
│       └── prometheus.yml
│
└── services/
    ├── api/
    │   ├── Dockerfile
    │   ├── main.py
    │   ├── requirements.txt
    │   ├── core/
    │   │   ├── __init__.py
    │   │   ├── config.py
    │   │   ├── metrics.py
    │   │   └── model_manager.py
    │   ├── routers/
    │   │   ├── __init__.py
    │   │   ├── inference.py
    │   │   ├── training.py
    │   │   └── versioning.py
    │   └── schemas/
    │       ├── __init__.py
    │       └── payloads.py
    │
    ├── frontend/
    │   ├── Dockerfile
    │   ├── app.py
    │   └── requirements.txt
    │
    ├── seeder/
    │   ├── Dockerfile
    │   ├── requirements.txt
    │   └── seeder.py
    │
    └── wrapper/
        ├── __init__.py
        ├── client.py
        └── requirements.txt
