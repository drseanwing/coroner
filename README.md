# Patient Safety Monitor

An automated system for aggregating, analysing, and disseminating learnings from coronial investigations and patient safety incidents across Australasia and the United Kingdom.

## Overview

The Patient Safety Monitor collects findings from official government sources, applies AI-powered analysis using the SEIPS 2.0 human factors framework, and generates accessible blog posts for healthcare practitioners.

### Key Features

- **Automated Collection**: Web scrapers for coronial courts and safety investigation bodies
- **AI-Powered Analysis**: Claude/GPT analysis using SEIPS 2.0 framework
- **Human Factors Focus**: Systematic identification of contributing factors
- **Blog Generation**: Educational content for healthcare professionals
- **Human-in-the-Loop Review**: Quality assurance before publication

### Data Sources

| Source | Country | Priority | Status |
|--------|---------|----------|--------|
| UK Prevention of Future Deaths | GB | P1 | Active |
| HSSIB Investigations | GB | P1 | Phase 6 |
| Coroners Court Victoria | AU | P1 | Phase 6 |
| NSW Coroners Court | AU | P1 | Phase 6 |
| Health & Disability Commissioner | NZ | P1 | Phase 6 |

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Anthropic API key (get one at [console.anthropic.com](https://console.anthropic.com/))

### Setup

1. **Clone and configure:**
```bash
git clone https://github.com/yourusername/patient-safety-monitor.git
cd patient-safety-monitor
cp .env.example .env
# Edit .env with your API keys
```

2. **Start services:**
```bash
docker-compose up -d
```

3. **Run migrations:**
```bash
docker-compose run --rm migrate
```

4. **Access the admin dashboard:**
Open http://localhost:8000 in your browser.

## Development

### Local Setup (without Docker)

1. **Create virtual environment:**
```bash
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
```

2. **Install dependencies:**
```bash
pip install -r requirements.txt
playwright install chromium
```

3. **Set up PostgreSQL:**
```bash
# Using Docker for just the database
docker run -d \
  --name psm-postgres \
  -e POSTGRES_USER=psm_user \
  -e POSTGRES_PASSWORD=psm_password \
  -e POSTGRES_DB=patient_safety_monitor \
  -p 5432:5432 \
  postgres:15-alpine
```

4. **Configure environment:**
```bash
cp .env.example .env
# Edit .env with DATABASE_URL=postgresql://psm_user:psm_password@localhost:5432/patient_safety_monitor
```

5. **Run migrations:**
```bash
alembic upgrade head
python -m scripts.seed_sources
```

6. **Start the application:**
```bash
# Start the web server
uvicorn admin.main:app --reload --port 8000

# In another terminal, start the scheduler
python -m scrapers.scheduler
```

### Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=. --cov-report=html

# Specific test file
pytest tests/unit/test_repository.py -v
```

### Code Quality

```bash
# Format code
black .
isort .

# Lint
ruff check .

# Type checking
mypy .
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    VPS (Python Backend)                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐  │
│  │Scheduler │─▶│ Scrapers │─▶│ Database │─▶│LLM Analyser │  │
│  │ (Cron)   │  │(Modular) │  │(Postgres)│  │(Claude/GPT) │  │
│  └──────────┘  └──────────┘  └──────────┘  └──────┬──────┘  │
│                                                    │         │
│  ┌─────────────────────────────────────────────────▼──────┐  │
│  │            Admin Dashboard (FastAPI + HTMX)            │  │
│  │       Review Queue │ Approve/Edit/Reject │ Publish     │  │
│  └─────────────────────────────────────────────────┬──────┘  │
└────────────────────────────────────────────────────┼────────┘
                                                     ▼
┌─────────────────────────────────────────────────────────────┐
│              Hostinger (Public Blog - Static HTML)           │
└─────────────────────────────────────────────────────────────┘
```

## Project Structure

```
patient-safety-monitor/
├── config/                 # Configuration management
│   ├── settings.py         # Environment variables
│   ├── logging.py          # Structured logging
│   ├── sources.yaml        # Data source definitions
│   └── prompts/            # LLM prompt templates
├── scrapers/               # Data collection
│   ├── base.py             # Abstract scraper class
│   ├── scheduler.py        # APScheduler integration
│   └── uk_pfd.py           # UK PFD scraper
├── analysis/               # LLM processing
│   ├── llm_client.py       # Claude/GPT abstraction
│   ├── analyser.py         # SEIPS analysis pipeline
│   └── processor.py        # Batch processing
├── database/               # Data persistence
│   ├── models.py           # SQLAlchemy models
│   ├── repository.py       # Data access layer
│   └── migrations/         # Alembic migrations
├── admin/                  # Review dashboard
├── publishing/             # Blog generation
├── scripts/                # Utility scripts
├── tests/                  # Test suites
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## Configuration

### Environment Variables

See `.env.example` for all available configuration options:

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `ANTHROPIC_API_KEY` | Yes | Claude API key |
| `ADMIN_USERNAME` | Yes | Dashboard login |
| `SECRET_KEY` | Yes | Session signing key |
| `LOG_LEVEL` | No | Logging verbosity (default: INFO) |

### Source Configuration

Data sources are defined in `config/sources.yaml`. Each source specifies:
- Scraper class and URL
- Cron schedule
- Category filters
- Rate limiting settings

## API Reference

### Admin API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/posts` | List posts with filtering |
| GET | `/api/posts/{id}` | Get post details |
| PATCH | `/api/posts/{id}` | Update post |
| POST | `/api/posts/{id}/approve` | Approve post |
| POST | `/api/posts/{id}/reject` | Reject post |
| GET | `/api/findings` | List findings |
| GET | `/api/sources` | List sources |
| POST | `/api/sources/{id}/trigger` | Manual scrape |

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is proprietary software. All rights reserved.

## Acknowledgments

- SEIPS 2.0 framework: Carayon et al. (2006)
- UK Judiciary PFD reports
- Australian coronial services
- New Zealand HDC

## Support

For questions or issues, please open a GitHub issue or contact the maintainers.
