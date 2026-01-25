# Patient Safety Monitor

## Framework Document & Technical Specification

**Version 1.0.0**
**Last Updated: 2026-01-20**

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Technical Architecture](#2-technical-architecture)
3. [Database Schema](#3-database-schema)
4. [Data Sources Specification](#4-data-sources-specification)
5. [LLM Analysis Specification](#5-llm-analysis-specification)
6. [Admin Dashboard Specification](#6-admin-dashboard-specification)
7. [Blog Output Specification](#7-blog-output-specification)
8. [Progress Tracker](#8-progress-tracker)
9. [Configuration Reference](#9-configuration-reference)
10. [Appendix](#10-appendix)

---

## 1. Project Overview

### 1.1 Purpose

The Patient Safety Monitor is an automated system designed to aggregate, analyse, and disseminate learnings from coronial investigations, patient safety incidents, and healthcare-related inquests across Australasia and the United Kingdom.

By systematically collecting findings from official sources and applying AI-powered analysis, the system identifies human factors issues, latent hazards, and improvement opportunities that can help prevent future patient harm.

### 1.2 Goals

Primary goals include:

1. **Automated collection** of coronial and patient safety investigation findings from official government sources
2. **AI-powered extraction** of human factors themes, system vulnerabilities, and actionable recommendations
3. **Generation of accessible, factual blog posts** that translate technical findings for healthcare practitioners
4. **Creation of a searchable knowledge base** of patient safety learnings

### 1.3 Scope

**Geographic focus:** Australia (all states/territories), New Zealand, and United Kingdom.

**Content types:**
- Coronial inquest findings with healthcare relevance
- Prevention of Future Deaths (PFD) reports
- Healthcare Safety Investigation Branch (HSSIB) reports
- Health and Disability Commissioner decisions
- State-based patient safety alerts

**Out of scope (initial release):**
- Root Cause Analysis reports (typically not public)
- Hospital-specific incident reports
- International sources beyond UK/AU/NZ

### 1.4 Key Stakeholders

Target audience includes:
- Emergency department clinicians
- Patient safety officers
- Hospital quality managers
- Paramedics and ambulance services
- Nursing leadership
- Healthcare educators

---

## 2. Technical Architecture

### 2.1 System Overview

The system follows a modular pipeline architecture with clear separation of concerns. Components communicate through a PostgreSQL database and internal APIs.

```
┌─────────────────────────────────────────────────────────────┐
│                     VPS (Python Backend)                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐  │
│  │Scheduler │─▶│ Scrapers │─▶│ Database │─▶│LLM Analyser │  │
│  │  (Cron)  │  │(Modular) │  │(Postgres)│  │(Claude/GPT) │  │
│  └──────────┘  └──────────┘  └──────────┘  └──────┬──────┘  │
│                                                    │         │
│  ┌─────────────────────────────────────────────────▼──────┐  │
│  │           Admin Dashboard (FastAPI + HTMX)             │  │
│  │    Review Queue │ Approve/Edit/Reject │ Publish        │  │
│  └─────────────────────────────────────────────────┬──────┘  │
└────────────────────────────────────────────────────┼─────────┘
                                                     ▼
┌─────────────────────────────────────────────────────────────┐
│            Hostinger (Public Blog - Static HTML)            │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Technology Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Scrapers | Python + Playwright | Handles JavaScript-rendered pages; robust selector support |
| Database | PostgreSQL 15 | ACID compliance; full-text search; JSON support for flexible schema |
| Scheduler | APScheduler + Cron | Persistent job store; configurable intervals per source |
| LLM Provider | Claude API (primary) | Superior reasoning for medical/legal content; GPT-5 as fallback |
| Admin UI | FastAPI + HTMX | Lightweight; no JS framework needed; good DX |
| Blog Output | Static HTML + Tailwind | Fast; secure; Hostinger-compatible; no server required |
| Containerisation | Docker Compose | Reproducible environments; easy deployment |

### 2.3 Directory Structure

```
patient-safety-monitor/
├── config/                    # Configuration management
│   ├── settings.py            # Environment variables
│   ├── sources.yaml           # Source definitions
│   └── prompts/               # LLM prompt templates
├── scrapers/                  # Data collection modules
│   ├── base.py                # Abstract base class
│   ├── uk_pfd.py              # UK PFD reports
│   ├── uk_hssib.py            # UK HSSIB
│   ├── au_vic_coroner.py      # Victoria Coroner
│   ├── au_nsw_coroner.py      # NSW Coroner
│   ├── au_qld_coroner.py      # Queensland Coroner
│   ├── nz_hdc.py              # NZ HDC decisions
│   └── nz_coroner.py          # NZ Coronial Services
├── analysis/                  # LLM processing
│   ├── llm_client.py          # Claude/GPT abstraction
│   ├── analyser.py            # Analysis pipeline
│   └── human_factors.py       # Domain extraction
├── database/                  # Data persistence
│   ├── models.py              # SQLAlchemy models
│   ├── repository.py          # Data access layer
│   └── migrations/            # Alembic migrations
├── admin/                     # Review dashboard
├── publishing/                # Blog generation
├── logs/                      # Application logs
├── tests/                     # Test suites
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

## 3. Database Schema

### 3.1 Entity Relationship Overview

The database uses a normalised schema with the following core entities:
- **sources** - Data source configurations
- **findings** - Raw collected data
- **analyses** - LLM-generated insights
- **posts** - Blog content
- **audit_log** - Change tracking

### 3.2 Table Definitions

#### sources - Data source registry

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| **id** | UUID | NO | Primary key (auto-generated) |
| code | VARCHAR(50) | NO | Unique identifier (e.g., uk_pfd, au_vic) |
| name | VARCHAR(200) | NO | Human-readable name |
| country | VARCHAR(2) | NO | ISO country code (AU, NZ, GB) |
| region | VARCHAR(50) | YES | State/region if applicable |
| base_url | TEXT | NO | Root URL for scraping |
| scraper_class | VARCHAR(100) | NO | Python class name (e.g., UKPFDScraper) |
| schedule_cron | VARCHAR(50) | NO | Cron expression for scheduling |
| is_active | BOOLEAN | NO | Enable/disable scraping |
| last_scraped_at | TIMESTAMPTZ | YES | Last successful scrape |
| config_json | JSONB | YES | Source-specific configuration |
| created_at | TIMESTAMPTZ | NO | Record creation timestamp |
| updated_at | TIMESTAMPTZ | NO | Last modification timestamp |

#### findings - Raw collected investigation data

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| **id** | UUID | NO | Primary key |
| source_id | UUID | NO | FK to sources.id |
| external_id | VARCHAR(100) | NO | ID from source system (for deduplication) |
| title | TEXT | NO | Finding/case title |
| deceased_name | VARCHAR(200) | YES | Name of deceased (if public) |
| date_of_death | DATE | YES | Date of incident/death |
| date_of_finding | DATE | YES | Date finding was published |
| coroner_name | VARCHAR(200) | YES | Name of coroner/investigator |
| source_url | TEXT | NO | URL to original document |
| pdf_url | TEXT | YES | Direct PDF link if available |
| content_text | TEXT | YES | Extracted text content |
| content_html | TEXT | YES | Raw HTML if scraped from web |
| pdf_stored_path | TEXT | YES | Local path to archived PDF |
| categories | TEXT[] | YES | Source-provided categories |
| is_healthcare | BOOLEAN | YES | Classified as healthcare-related |
| healthcare_confidence | DECIMAL(3,2) | YES | Classification confidence (0.00-1.00) |
| status | VARCHAR(20) | NO | new, classified, analysed, published, excluded |
| metadata_json | JSONB | YES | Source-specific metadata |
| created_at | TIMESTAMPTZ | NO | Record creation timestamp |
| updated_at | TIMESTAMPTZ | NO | Last modification timestamp |

#### analyses - LLM-generated analysis results

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| **id** | UUID | NO | Primary key |
| finding_id | UUID | NO | FK to findings.id |
| llm_provider | VARCHAR(20) | NO | claude, openai |
| llm_model | VARCHAR(50) | NO | Model identifier used |
| prompt_version | VARCHAR(20) | NO | Version of prompt template |
| summary | TEXT | NO | Executive summary of incident |
| human_factors | JSONB | NO | Structured HF analysis (see 3.3) |
| latent_hazards | JSONB | NO | System vulnerabilities identified |
| recommendations | JSONB | NO | Improvement opportunities |
| key_learnings | TEXT[] | NO | Bullet-point takeaways |
| settings | TEXT[] | YES | Healthcare settings involved (ED, ambulance, etc.) |
| specialties | TEXT[] | YES | Medical specialties relevant |
| tokens_input | INTEGER | YES | Input tokens consumed |
| tokens_output | INTEGER | YES | Output tokens generated |
| cost_usd | DECIMAL(10,4) | YES | API cost for this analysis |
| raw_response | JSONB | YES | Full LLM response for debugging |
| created_at | TIMESTAMPTZ | NO | Analysis timestamp |

#### posts - Generated blog content

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| **id** | UUID | NO | Primary key |
| analysis_id | UUID | NO | FK to analyses.id |
| slug | VARCHAR(200) | NO | URL-safe identifier (unique) |
| title | TEXT | NO | Blog post title |
| content_markdown | TEXT | NO | Post content in Markdown |
| content_html | TEXT | YES | Rendered HTML |
| excerpt | TEXT | YES | Short preview text |
| tags | TEXT[] | YES | Categorisation tags |
| status | VARCHAR(20) | NO | draft, pending_review, approved, published, rejected |
| reviewer_notes | TEXT | YES | Human reviewer feedback |
| reviewed_by | VARCHAR(100) | YES | Reviewer identifier |
| reviewed_at | TIMESTAMPTZ | YES | Review timestamp |
| published_at | TIMESTAMPTZ | YES | Publication timestamp |
| created_at | TIMESTAMPTZ | NO | Record creation timestamp |
| updated_at | TIMESTAMPTZ | NO | Last modification timestamp |

### 3.3 Human Factors JSONB Schema

The `human_factors` column in analyses stores structured data following this schema:

```json
{
  "individual_factors": [
    { "factor": "Fatigue", "description": "...", "severity": "high" }
  ],
  "team_factors": [
    { "factor": "Communication breakdown", "description": "..." }
  ],
  "task_factors": [
    { "factor": "Cognitive overload", "description": "..." }
  ],
  "environment_factors": [
    { "factor": "Equipment unavailability", "description": "..." }
  ],
  "organisational_factors": [
    { "factor": "Staffing levels", "description": "..." }
  ]
}
```

---

## 4. Data Sources Specification

### 4.1 Source Registry

| Code | Name | Country | Region | Priority | Status |
|------|------|---------|--------|----------|--------|
| uk_pfd | UK Prevention of Future Deaths | GB | — | P1 | Phase 2 |
| uk_hssib | HSSIB Investigations | GB | — | P1 | Phase 6 |
| au_vic | Coroners Court Victoria | AU | VIC | P1 | Phase 6 |
| au_nsw | NSW Coroners Court | AU | NSW | P1 | Phase 6 |
| au_qld | Queensland Coroners Court | AU | QLD | P2 | Phase 6 |
| nz_hdc | Health & Disability Commissioner | NZ | — | P1 | Phase 6 |
| nz_coroner | NZ Coronial Services | NZ | — | P2 | Phase 6 |

### 4.2 Source-Specific Details

#### UK Prevention of Future Deaths (uk_pfd)

**Base URL:** https://www.judiciary.uk/prevention-of-future-death-reports/

**Structure:** Paginated list with individual report pages. Reports categorised by topic including Hospital Death (Clinical), Hospital Death (Other), and Medical cause. Each report contains coroner details, date, addressee organisations, and concerns raised.

**Update frequency:** Daily checks recommended (new reports published irregularly).

**Technical notes:** Site uses standard HTML; no JavaScript rendering required. Category filtering available via URL parameters.

#### HSSIB Investigations (uk_hssib)

**Base URL:** https://www.hssib.org.uk/patient-safety-investigations/

**Structure:** Investigation reports published as HTML summaries with downloadable PDF reports. Each investigation has structured sections including summary, findings, safety recommendations, and responses.

**Update frequency:** Weekly checks sufficient (reports published monthly).

**Technical notes:** Clean HTML structure; PDF extraction required for full content.

#### Coroners Court Victoria (au_vic)

**Base URL:** https://www.coronerscourt.vic.gov.au/inquests-findings

**Structure:** Searchable database of findings. Healthcare-related cases can be filtered. Findings available as PDF documents with structured format.

**Update frequency:** Weekly checks recommended.

**Technical notes:** May require handling of dynamic content loading.

#### Health and Disability Commissioner NZ (nz_hdc)

**Base URL:** https://www.hdc.org.nz/decisions/

**Structure:** Decisions published with case numbers, dates, and full decision text. Categories include public hospital, private hospital, rest home care, and mental health services.

**Update frequency:** Weekly checks sufficient.

**Technical notes:** Well-structured HTML; good search functionality available.

---

## 5. LLM Analysis Specification

### 5.1 Analysis Pipeline

Each finding passes through a multi-stage analysis pipeline:

**Stage 1 - Classification:** Determine if finding is healthcare-related (binary classification with confidence score). Findings below 0.7 confidence flagged for human review.

**Stage 2 - Content Extraction:** Extract structured data including date, location, parties involved, sequence of events, and coroner recommendations.

**Stage 3 - Human Factors Analysis:** Apply SEIPS (Systems Engineering Initiative for Patient Safety) framework to identify contributory factors across individual, team, task, environment, and organisational domains.

**Stage 4 - Synthesis:** Generate executive summary, key learnings, and actionable recommendations.

**Stage 5 - Blog Generation:** Create reader-friendly blog post with appropriate tone and structure.

### 5.2 Prompt Templates

Prompt templates are versioned and stored in `/config/prompts/`. Current versions:

| Template | Version | Purpose |
|----------|---------|---------|
| classify_healthcare.txt | 1.0.0 | Determine if finding relates to healthcare delivery |
| extract_content.txt | 1.0.0 | Extract structured data from finding text |
| analyse_human_factors.txt | 1.0.0 | Apply SEIPS framework to identify HF issues |
| generate_blog_post.txt | 1.0.0 | Create reader-friendly blog content |

### 5.3 Human Factors Framework

Analysis uses the SEIPS 2.0 model adapted for coronial findings:

| Domain | Factors to Identify |
|--------|---------------------|
| Individual | Fatigue, cognitive load, skill level, physical health, distraction, stress |
| Team | Communication failures, handover gaps, role ambiguity, supervision, team composition |
| Task | Complexity, time pressure, interruptions, competing priorities, task design |
| Tools/Technology | Equipment availability, usability, maintenance, interoperability, documentation |
| Environment | Physical layout, noise, lighting, crowding, access to resources |
| Organisation | Staffing, policies, training, culture, resource allocation, leadership |

### 5.4 LLM Configuration

| Parameter | Claude | GPT-5 (Fallback) |
|-----------|--------|------------------|
| Model | claude-sonnet-4-20250514 | gpt-5-turbo |
| Temperature | 0.3 (analysis) / 0.7 (blog) | 0.3 (analysis) / 0.7 (blog) |
| Max tokens | 4096 | 4096 |
| Retry strategy | 3 attempts, exponential backoff | 3 attempts, exponential backoff |

---

## 6. Admin Dashboard Specification

### 6.1 Features

The admin dashboard provides human-in-the-loop review capabilities:

**Review Queue:** List of posts awaiting review with filtering by source, date, and status. Preview of AI-generated content alongside original finding.

**Post Editor:** Inline editing of title, content, and tags. Side-by-side comparison with source material. Revision history tracking.

**Approval Workflow:**
- **Approve** (publish immediately or schedule)
- **Reject** (with reason, excluded from future processing)
- **Request Changes** (return to draft with notes)

**Analytics Dashboard:** Posts published per source, API costs tracking, processing success rates, and average review time.

### 6.2 Authentication

Initial implementation uses HTTP Basic Auth over HTTPS.

Future enhancement: OAuth2 with role-based access control.

### 6.3 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/posts | List posts with filtering/pagination |
| GET | /api/posts/{id} | Get single post with full details |
| PATCH | /api/posts/{id} | Update post content/status |
| POST | /api/posts/{id}/approve | Approve and optionally publish |
| POST | /api/posts/{id}/reject | Reject with reason |
| GET | /api/findings | List raw findings |
| GET | /api/sources | List configured sources |
| POST | /api/sources/{id}/trigger | Manually trigger scrape |
| GET | /api/stats | Dashboard statistics |

---

## 7. Blog Output Specification

### 7.1 Static Site Structure

The blog is generated as static HTML files for deployment to Hostinger:

```
public_html/
├── index.html              # Homepage with recent posts
├── posts/
│   ├── index.html          # Post archive
│   └── {slug}/index.html   # Individual posts
├── tags/
│   └── {tag}/index.html    # Posts by tag
├── sources/
│   └── {source}/index.html # Posts by source
├── about/index.html        # About page
├── assets/
│   ├── css/main.css
│   └── js/search.js
├── feed.xml                # RSS feed
└── sitemap.xml
```

### 7.2 Post Template Structure

Each blog post follows a consistent structure optimised for healthcare professionals:

**Header:** Title, publication date, source attribution, reading time estimate, tags.

**Key Learnings Box:** Bulleted summary of 3-5 main takeaways (highlighted box at top).

**Background:** Brief context about the incident without identifying patients (unless already public).

**What Happened:** Factual sequence of events drawn from the finding.

**Human Factors Analysis:** Structured breakdown using SEIPS categories.

**Recommendations:** Actionable improvement opportunities for similar settings.

**Source Information:** Link to original finding, jurisdiction details, date of publication.

**Related Posts:** Links to similar cases or themes.

### 7.3 SEO and Accessibility

All pages include:
- Semantic HTML5 structure
- Open Graph meta tags for social sharing
- Structured data (JSON-LD) for search engines
- Alt text for any images
- WCAG 2.1 AA compliance
- Mobile-responsive design

---

## 8. Progress Tracker

### 8.1 Phase Overview

| Phase | Description | Target Date | Status | Progress |
|-------|-------------|-------------|--------|----------|
| 1 | Core Framework & Database | — | Not Started | 0% |
| 2 | First Scraper (UK PFD) | — | Not Started | 0% |
| 3 | LLM Analysis Pipeline | — | Not Started | 0% |
| 4 | Admin Dashboard | — | Not Started | 0% |
| 5 | Blog Generation & Publishing | — | Not Started | 0% |
| 6 | Additional Scrapers | — | Not Started | 0% |

### 8.2 Detailed Task Breakdown

#### Phase 1: Core Framework & Database

| ID | Task | Status | Notes |
|----|------|--------|-------|
| 1.1 | Project scaffolding and directory structure | ☐ Todo | |
| 1.2 | Configuration management (settings.py, .env) | ☐ Todo | |
| 1.3 | Logging framework setup | ☐ Todo | |
| 1.4 | Database models (SQLAlchemy) | ☐ Todo | |
| 1.5 | Alembic migrations setup | ☐ Todo | |
| 1.6 | Repository layer (CRUD operations) | ☐ Todo | |
| 1.7 | Docker Compose configuration | ☐ Todo | |
| 1.8 | Base scraper abstract class | ☐ Todo | |

#### Phase 2: First Scraper (UK PFD)

| ID | Task | Status | Notes |
|----|------|--------|-------|
| 2.1 | UK PFD site analysis and selector mapping | ☐ Todo | |
| 2.2 | Implement UKPFDScraper class | ☐ Todo | |
| 2.3 | PDF download and text extraction | ☐ Todo | |
| 2.4 | Healthcare category filtering | ☐ Todo | |
| 2.5 | Deduplication logic | ☐ Todo | |
| 2.6 | Error handling and retry logic | ☐ Todo | |
| 2.7 | Scheduler integration | ☐ Todo | |
| 2.8 | Unit and integration tests | ☐ Todo | |

#### Phase 3: LLM Analysis Pipeline

| ID | Task | Status | Notes |
|----|------|--------|-------|
| 3.1 | LLM client abstraction (Claude/GPT) | ☐ Todo | |
| 3.2 | Prompt template system | ☐ Todo | |
| 3.3 | Healthcare classification prompt | ☐ Todo | |
| 3.4 | Human factors analysis prompt | ☐ Todo | |
| 3.5 | Blog post generation prompt | ☐ Todo | |
| 3.6 | Analysis pipeline orchestration | ☐ Todo | |
| 3.7 | Cost tracking and logging | ☐ Todo | |
| 3.8 | Response validation and error handling | ☐ Todo | |

#### Phase 4: Admin Dashboard

| ID | Task | Status | Notes |
|----|------|--------|-------|
| 4.1 | FastAPI application setup | ☐ Todo | |
| 4.2 | Authentication middleware | ☐ Todo | |
| 4.3 | Review queue page | ☐ Todo | |
| 4.4 | Post editor with preview | ☐ Todo | |
| 4.5 | Approve/Reject workflow | ☐ Todo | |
| 4.6 | Source management page | ☐ Todo | |
| 4.7 | Analytics dashboard | ☐ Todo | |

#### Phase 5: Blog Generation & Publishing

| ID | Task | Status | Notes |
|----|------|--------|-------|
| 5.1 | Jinja2 template system setup | ☐ Todo | |
| 5.2 | Post template design (HTML/CSS) | ☐ Todo | |
| 5.3 | Index and archive pages | ☐ Todo | |
| 5.4 | Tag and source listing pages | ☐ Todo | |
| 5.5 | RSS feed generation | ☐ Todo | |
| 5.6 | Sitemap generation | ☐ Todo | |
| 5.7 | FTP/SFTP deployment to Hostinger | ☐ Todo | |
| 5.8 | Client-side search functionality | ☐ Todo | |

#### Phase 6: Additional Scrapers

| ID | Task | Status | Notes |
|----|------|--------|-------|
| 6.1 | UK HSSIB scraper | ☐ Todo | |
| 6.2 | Victoria Coroner scraper | ☐ Todo | |
| 6.3 | NSW Coroner scraper | ☐ Todo | |
| 6.4 | Queensland Coroner scraper | ☐ Todo | |
| 6.5 | NZ HDC scraper | ☐ Todo | |
| 6.6 | NZ Coronial Services scraper | ☐ Todo | |

---

## 9. Configuration Reference

### 9.1 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| DATABASE_URL | Yes | PostgreSQL connection string |
| ANTHROPIC_API_KEY | Yes | Claude API key |
| OPENAI_API_KEY | No | GPT-5 API key (fallback) |
| LOG_LEVEL | No | Logging level (default: INFO) |
| LOG_FILE | No | Log file path (default: logs/app.log) |
| ADMIN_USERNAME | Yes | Admin dashboard username |
| ADMIN_PASSWORD | Yes | Admin dashboard password (hashed) |
| FTP_HOST | No | Hostinger FTP hostname |
| FTP_USERNAME | No | Hostinger FTP username |
| FTP_PASSWORD | No | Hostinger FTP password |
| SCRAPE_INTERVAL_HOURS | No | Default scrape interval (default: 24) |

### 9.2 sources.yaml Schema

```yaml
sources:
  - code: uk_pfd
    name: "UK Prevention of Future Deaths"
    country: GB
    base_url: "https://www.judiciary.uk/pfd/"
    scraper_class: UKPFDScraper
    schedule: "0 6 * * *"  # Daily at 6 AM
    is_active: true
    config:
      categories:
        - "Hospital Death (Clinical)"
        - "Hospital Death (Other)"
        - "Medical cause"
      max_pages: 10
```

---

## 10. Appendix

### 10.1 Glossary

| Term | Definition |
|------|------------|
| PFD | Prevention of Future Deaths - UK coronial reports with recommendations |
| HSSIB | Healthcare Safety Investigation Branch (UK national body) |
| HDC | Health and Disability Commissioner (New Zealand) |
| SEIPS | Systems Engineering Initiative for Patient Safety (human factors framework) |
| RCA | Root Cause Analysis - internal hospital investigation methodology |
| Human Factors | Study of how humans interact with systems; focuses on error prevention |
| Latent Hazard | Hidden system weakness that can contribute to adverse events |

### 10.2 Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2026-01-20 | Claude | Initial framework document |

### 10.3 References

- UK Judiciary PFD Reports: https://www.judiciary.uk/prevention-of-future-death-reports/
- HSSIB: https://www.hssib.org.uk/
- Coroners Court Victoria: https://www.coronerscourt.vic.gov.au/
- NZ Health & Disability Commissioner: https://www.hdc.org.nz/
- SEIPS Framework: Carayon et al. (2006), Work system design for patient safety
