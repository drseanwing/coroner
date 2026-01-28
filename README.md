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
| HSSIB Investigations | GB | P1 | Active |
| Coroners Court Victoria | AU | P1 | Active |
| NSW Coroners Court | AU | P1 | Active |
| Queensland Coroners Court | AU | P1 | Active |
| Health & Disability Commissioner | NZ | P1 | Active |
| NZ Coronial Services | NZ | P1 | Active |

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
Open http://localhost:7410 in your browser.

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
  -p 7411:5432 \
  postgres:15-alpine
```

4. **Configure environment:**
```bash
cp .env.example .env
# Edit .env with DATABASE_URL=postgresql://psm_user:psm_password@localhost:7411/patient_safety_monitor
```

5. **Run migrations:**
```bash
alembic upgrade head
python -m scripts.seed_sources
```

6. **Start the application:**
```bash
# Start the web server
uvicorn admin.main:app --reload --port 7410

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

## Deployment

### Production Deployment

#### Prerequisites

- VPS with Docker and Docker Compose installed
- Domain name with SSL certificate configured
- FTP or SFTP access to web hosting (for blog deployment)
- PostgreSQL 15+ database (can use Docker or managed service)

#### Environment Configuration

Create a production `.env` file with the following variables:

```bash
# Database
DATABASE_URL=postgresql://user:password@host:7411/patient_safety_monitor

# LLM API Keys
ANTHROPIC_API_KEY=your_claude_api_key
OPENAI_API_KEY=your_openai_api_key  # Optional fallback

# Admin Authentication
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=pbkdf2:sha256:...  # Generate with scripts/hash_password.py
SECRET_KEY=your_secure_random_secret_key  # Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"

# FTP/SFTP Configuration for Blog Deployment
FTP_HOST=your-hosting-server.com
FTP_USERNAME=your_ftp_username
FTP_PASSWORD=your_ftp_password
FTP_PORT=21  # Use 21 for FTP, 22 for SFTP

# Optional: Set to "sftp" to use SFTP instead of FTP
# FTP_PROTOCOL=sftp

# Application Settings
LOG_LEVEL=INFO
ENVIRONMENT=production
```

**Important Security Notes:**

- Generate a secure `SECRET_KEY` using: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
- Hash passwords using `scripts/hash_password.py`: `python scripts/hash_password.py your_password`
- Never commit `.env` files to version control
- Use environment-specific `.env` files for different deployments

#### Deploying with Docker

1. **Build and start services:**

```bash
# Pull latest code
git pull origin main

# Build images
docker-compose build

# Start all services in detached mode
docker-compose up -d
```

2. **Run database migrations:**

```bash
# Apply database schema migrations
docker-compose run --rm migrate

# Seed initial data sources (first time only)
docker-compose run --rm app python -m scripts.seed_sources
```

3. **Verify deployment:**

```bash
# Check service status
docker-compose ps

# View logs
docker-compose logs -f app
docker-compose logs -f scheduler

# Check health
curl http://localhost:7410/health
```

4. **Update deployment:**

```bash
# Pull latest changes
git pull origin main

# Rebuild and restart
docker-compose down
docker-compose build
docker-compose up -d

# Run any new migrations
docker-compose run --rm migrate
```

#### Blog Deployment

The system supports both FTP and SFTP for deploying the static blog:

**FTP Configuration (Port 21):**
```bash
FTP_HOST=ftp.yourhosting.com
FTP_PORT=21
FTP_USERNAME=user@yourdomain.com
FTP_PASSWORD=your_password
```

**SFTP Configuration (Port 22):**
```bash
FTP_HOST=sftp.yourhosting.com
FTP_PORT=22
FTP_PROTOCOL=sftp
FTP_USERNAME=user@yourdomain.com
FTP_PASSWORD=your_password
```

**Triggering Blog Generation and Deployment:**

1. **Via Admin Dashboard:**
   - Navigate to the "Publishing" section
   - Click "Generate & Deploy Blog"
   - Monitor progress in real-time

2. **Via Command Line:**
   ```bash
   # Generate blog locally
   docker-compose run --rm app python -m publishing.generator

   # Deploy to hosting
   docker-compose run --rm app python -m publishing.deployer
   ```

3. **Automated Publishing:**
   - Configure automatic deployment after post approval in `config/settings.py`
   - Blog regenerates when posts are approved/rejected
   - Scheduled regeneration available via cron

#### Database Migrations

**Creating new migrations:**

```bash
# Auto-generate migration from model changes
docker-compose run --rm app alembic revision --autogenerate -m "description"

# Create empty migration
docker-compose run --rm app alembic revision -m "description"
```

**Applying migrations:**

```bash
# Upgrade to latest
docker-compose run --rm migrate

# Or manually:
docker-compose run --rm app alembic upgrade head

# Rollback one version
docker-compose run --rm app alembic downgrade -1

# Show current version
docker-compose run --rm app alembic current
```

#### Monitoring and Maintenance

**View Logs:**
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f app
docker-compose logs -f scheduler
docker-compose logs -f db
```

**Backup Database:**
```bash
# Create backup
docker-compose exec db pg_dump -U psm_user patient_safety_monitor > backup_$(date +%Y%m%d).sql

# Restore backup
docker-compose exec -T db psql -U psm_user patient_safety_monitor < backup_20260125.sql
```

**Resource Monitoring:**
```bash
# Container resource usage
docker stats

# Disk usage
docker system df
```

#### Scaling Considerations

For high-volume production deployments:

1. **Database**: Use managed PostgreSQL (AWS RDS, DigitalOcean Managed Database)
2. **LLM Rate Limiting**: Configure rate limits in `config/settings.py`
3. **Scheduler**: Run on separate container with `docker-compose scale scheduler=1`
4. **Caching**: Enable Redis for session storage and API caching
5. **CDN**: Serve static blog content via Cloudflare or similar CDN

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
│   ├── uk_pfd.py           # UK PFD scraper
│   ├── uk_hssib.py         # UK HSSIB scraper
│   ├── au_vic_coroner.py   # Victoria Coroner scraper
│   ├── au_nsw_coroner.py   # NSW Coroner scraper
│   ├── au_qld_coroner.py   # Queensland Coroner scraper
│   ├── nz_hdc.py           # NZ HDC scraper
│   └── nz_coroner.py       # NZ Coronial scraper
├── analysis/               # LLM processing
│   ├── llm_client.py       # Claude/GPT abstraction
│   ├── analyser.py         # SEIPS analysis pipeline
│   ├── processor.py        # Batch processing
│   └── human_factors.py    # SEIPS 2.0 framework
├── database/               # Data persistence
│   ├── models.py           # SQLAlchemy models
│   ├── repository.py       # Data access layer
│   └── migrations/         # Alembic migrations
├── admin/                  # Review dashboard
│   ├── main.py             # FastAPI application
│   ├── auth.py             # OAuth2/JWT authentication
│   └── routes/             # API endpoints
├── publishing/             # Blog generation
│   ├── generator.py        # Static site generator
│   ├── deployer.py         # FTP/SFTP deployment
│   └── search_index.py     # Search functionality
├── scripts/                # Utility scripts
│   ├── seed_sources.py     # Initialize data sources
│   └── hash_password.py    # Password hashing utility
├── tests/                  # Test suites
│   ├── unit/               # Unit tests
│   ├── integration/        # Integration tests
│   └── e2e/                # End-to-end tests
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

#### Authentication

The API supports two authentication methods:

1. **HTTP Basic Auth (Legacy)**
   - Username and password from environment variables
   - Used for backward compatibility

2. **OAuth2/JWT Tokens (Recommended)**
   - POST `/api/auth/login` - Obtain access token
   - POST `/api/auth/refresh` - Refresh expired token
   - GET `/api/auth/me` - Get current user info

**Example Login:**
```bash
curl -X POST http://localhost:7410/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"your_password"}'
```

#### Endpoints

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/api/auth/login` | Obtain JWT token | No |
| POST | `/api/auth/refresh` | Refresh access token | Yes (Refresh token) |
| GET | `/api/auth/me` | Get current user | Yes |
| GET | `/api/posts` | List posts with filtering | Yes |
| GET | `/api/posts/{id}` | Get post details | Yes |
| PATCH | `/api/posts/{id}` | Update post | Yes |
| POST | `/api/posts/{id}/approve` | Approve post | Yes |
| POST | `/api/posts/{id}/reject` | Reject post | Yes |
| GET | `/api/findings` | List findings | Yes |
| GET | `/api/sources` | List sources | Yes |
| POST | `/api/sources/{id}/trigger` | Manual scrape | Yes |
| POST | `/api/publish/generate` | Generate blog | Yes |
| POST | `/api/publish/deploy` | Deploy to hosting | Yes |

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

## Version History

### v1.0.0 (2026-01-25)

**Initial Release**

- **Data Collection**: 7 scrapers covering UK, Australia, and New Zealand
  - UK Prevention of Future Deaths (PFD)
  - UK Health Services Safety Investigations Body (HSSIB)
  - Victoria Coroners Court (AU)
  - NSW Coroners Court (AU)
  - Queensland Coroners Court (AU)
  - New Zealand Health & Disability Commissioner
  - New Zealand Coronial Services

- **Analysis Pipeline**:
  - LLM-powered analysis using Claude (Anthropic) and GPT (OpenAI)
  - SEIPS 2.0 human factors framework integration
  - Automated extraction of contributing factors, recommendations, and learnings
  - Batch processing with retry logic and rate limiting

- **Admin Dashboard**:
  - FastAPI + HTMX web interface
  - Dual authentication: HTTP Basic Auth (legacy) and OAuth2/JWT (recommended)
  - Review queue with approve/edit/reject workflow
  - Manual scraper triggering
  - Real-time status monitoring

- **Publishing System**:
  - Static blog generation with responsive design
  - Full-text search functionality
  - RSS feed and XML sitemap generation
  - FTP and SFTP deployment support
  - Automated deployment after post approval

- **Testing & Quality**:
  - Comprehensive test coverage (unit, integration, E2E)
  - Type hints and mypy validation
  - Linting with ruff and formatting with black
  - Docker-based CI/CD ready

- **Documentation**:
  - Complete setup and deployment guide
  - API reference
  - Development workflow documentation
  - Architecture diagrams
