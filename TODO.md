# Patient Safety Monitor - Implementation Audit & TODO

**Audit Date:** 2026-01-25
**Auditor:** Claude Code
**Spec Version:** 1.0.0 (FRAMEWORK.md)

---

## Executive Summary

This document provides a comprehensive audit of the Patient Safety Monitor codebase against the framework specification, identifies gaps, and presents granular action items for completion.

### Overall Progress

| Phase | Description | Status | Progress |
|-------|-------------|--------|----------|
| 1 | Core Framework & Database | **COMPLETE** | 100% |
| 2 | First Scraper (UK PFD) | **COMPLETE** | 100% |
| 3 | LLM Analysis Pipeline | **COMPLETE** | 100% |
| 4 | Admin Dashboard | **COMPLETE** | 95% |
| 5 | Blog Generation & Publishing | **COMPLETE** | 95% |
| 6 | Additional Scrapers | **NOT STARTED** | 0% |

**Overall Completion: ~82%**

---

## Detailed Audit

### Phase 1: Core Framework & Database - COMPLETE

| Task ID | Task | Status | Implementation |
|---------|------|--------|----------------|
| 1.1 | Project scaffolding and directory structure | ✅ Complete | Standard Python package layout |
| 1.2 | Configuration management (settings.py, .env) | ✅ Complete | `config/settings.py` using Pydantic Settings |
| 1.3 | Logging framework setup | ✅ Complete | `config/logging.py` with JSON/text formats |
| 1.4 | Database models (SQLAlchemy) | ✅ Complete | `database/models.py` - all entities |
| 1.5 | Alembic migrations setup | ✅ Complete | `database/migrations/` with initial schema |
| 1.6 | Repository layer (CRUD operations) | ✅ Complete | `database/repository.py` with UnitOfWork |
| 1.7 | Docker Compose configuration | ✅ Complete | `docker-compose.yml` with PostgreSQL |
| 1.8 | Base scraper abstract class | ✅ Complete | `scrapers/base.py` with async context |

**Files Implemented:**
- `config/settings.py` - Environment configuration
- `config/logging.py` - Logging setup
- `config/sources.yaml` - Source definitions
- `database/models.py` - SQLAlchemy models
- `database/repository.py` - Repository pattern
- `database/connection.py` - Database connection manager
- `database/migrations/` - Alembic setup
- `docker-compose.yml` - Container orchestration
- `requirements.txt` - Dependencies
- `.env.example` - Environment template

### Phase 2: First Scraper (UK PFD) - COMPLETE

| Task ID | Task | Status | Implementation |
|---------|------|--------|----------------|
| 2.1 | UK PFD site analysis and selector mapping | ✅ Complete | Selectors in uk_pfd.py |
| 2.2 | Implement UKPFDScraper class | ✅ Complete | `scrapers/uk_pfd.py` |
| 2.3 | PDF download and text extraction | ✅ Complete | Via pypdf/pdfplumber |
| 2.4 | Healthcare category filtering | ✅ Complete | Category filtering implemented |
| 2.5 | Deduplication logic | ✅ Complete | Via external_id check |
| 2.6 | Error handling and retry logic | ✅ Complete | Exponential backoff in base class |
| 2.7 | Scheduler integration | ✅ Complete | `scrapers/scheduler.py` |
| 2.8 | Unit and integration tests | ⚠️ Partial | Only repository tests exist |

**Files Implemented:**
- `scrapers/base.py` - Abstract scraper base class
- `scrapers/uk_pfd.py` - UK PFD scraper
- `scrapers/scheduler.py` - APScheduler integration
- `scripts/seed_sources.py` - Source seeding utility

### Phase 3: LLM Analysis Pipeline - COMPLETE

| Task ID | Task | Status | Implementation |
|---------|------|--------|----------------|
| 3.1 | LLM client abstraction (Claude/GPT) | ✅ Complete | `analysis/llm_client.py` |
| 3.2 | Prompt template system | ✅ Complete | `analyser.py` PromptTemplateLoader |
| 3.3 | Healthcare classification prompt | ✅ Complete | `config/prompts/classify_healthcare.txt` |
| 3.4 | Human factors analysis prompt | ✅ Complete | `config/prompts/analyse_human_factors.txt` |
| 3.5 | Blog post generation prompt | ✅ Complete | `config/prompts/generate_blog_post.txt` |
| 3.6 | Analysis pipeline orchestration | ✅ Complete | `analysis/analyser.py` |
| 3.7 | Cost tracking and logging | ✅ Complete | In LLMResponse class |
| 3.8 | Response validation and error handling | ✅ Complete | JSON parsing with fallbacks |

**Files Implemented:**
- `analysis/llm_client.py` - Claude/OpenAI clients
- `analysis/analyser.py` - Analysis pipeline
- `analysis/processor.py` - Batch processing
- `config/prompts/` - All prompt templates

### Phase 4: Admin Dashboard - 95% COMPLETE

| Task ID | Task | Status | Implementation |
|---------|------|--------|----------------|
| 4.1 | FastAPI application setup | ✅ Complete | `admin/main.py` |
| 4.2 | Authentication middleware | ✅ Complete | HTTP Basic Auth |
| 4.3 | Review queue page | ✅ Complete | `admin/routes.py` + templates |
| 4.4 | Post editor with preview | ✅ Complete | `review_post.html` |
| 4.5 | Approve/Reject workflow | ✅ Complete | HTMX endpoints |
| 4.6 | Source management page | ✅ Complete | `sources.html` |
| 4.7 | Analytics dashboard | ✅ Complete | `analytics.html` |

**Gaps:**
- Manual trigger doesn't actually invoke scheduler
- Password comparison uses plain text (should use bcrypt)

**Files Implemented:**
- `admin/main.py` - FastAPI app factory
- `admin/routes.py` - Page routes
- `admin/api.py` - API endpoints
- `admin/templates/` - All templates including partials

### Phase 5: Blog Generation & Publishing - 95% COMPLETE

| Task ID | Task | Status | Implementation |
|---------|------|--------|----------------|
| 5.1 | Jinja2 template system setup | ✅ Complete | `publishing/generator.py` |
| 5.2 | Post template design (HTML/CSS) | ✅ Complete | `publishing/templates/post.html` |
| 5.3 | Index and archive pages | ✅ Complete | Templates exist |
| 5.4 | Tag and source listing pages | ⚠️ Partial | Tag pages complete, source pages missing |
| 5.5 | RSS feed generation | ✅ Complete | `feed.xml` template |
| 5.6 | Sitemap generation | ✅ Complete | XML sitemap generation |
| 5.7 | FTP/SFTP deployment to Hostinger | ✅ Complete | `publishing/deployer.py` |
| 5.8 | Client-side search functionality | ⚠️ Partial | JS skeleton only, no index generation |

**Gaps:**
- `search-index.json` generation not implemented
- Source listing pages not generated
- No search index builder

**Files Implemented:**
- `publishing/generator.py` - Static site generator
- `publishing/deployer.py` - FTP deployer
- `publishing/templates/` - All blog templates

### Phase 6: Additional Scrapers - NOT STARTED

| Task ID | Task | Status | Implementation |
|---------|------|--------|----------------|
| 6.1 | UK HSSIB scraper | ❌ Not Started | Missing `scrapers/uk_hssib.py` |
| 6.2 | Victoria Coroner scraper | ❌ Not Started | Missing `scrapers/au_vic_coroner.py` |
| 6.3 | NSW Coroner scraper | ❌ Not Started | Missing `scrapers/au_nsw_coroner.py` |
| 6.4 | Queensland Coroner scraper | ❌ Not Started | Missing `scrapers/au_qld_coroner.py` |
| 6.5 | NZ HDC scraper | ❌ Not Started | Missing `scrapers/nz_hdc.py` |
| 6.6 | NZ Coronial Services scraper | ❌ Not Started | Missing `scrapers/nz_coroner.py` |

---

## Identified Gaps

### Critical Gaps

1. **No additional scrapers** - Only UK PFD implemented
2. **Search functionality incomplete** - No search index generation
3. **Manual trigger disconnected** - Admin trigger doesn't invoke scheduler

### Medium Priority Gaps

4. **Password security** - Plain text comparison instead of bcrypt hashing
5. **Source listing pages missing** - Generator doesn't create `/sources/` pages
6. **Test coverage low** - Only repository unit tests exist
7. **Audit log automation** - No database triggers for automatic logging

### Low Priority Gaps

8. **human_factors.py file** - Mentioned in spec but logic exists in `analyser.py`
9. **OAuth2 authentication** - Listed as future enhancement
10. **SFTP support** - Only FTP implemented in deployer

---

## Granular TODO List

### Priority 1: Critical (Must Complete)

#### 6.1 UK HSSIB Scraper
- [ ] Analyze HSSIB website structure (https://www.hssib.org.uk/patient-safety-investigations/)
- [ ] Map HTML selectors for investigation list pages
- [ ] Map HTML selectors for individual investigation pages
- [ ] Implement PDF link extraction
- [ ] Implement PDF download functionality
- [ ] Implement content text extraction from PDFs
- [ ] Create `scrapers/uk_hssib.py` class extending BaseScraper
- [ ] Add HSSIB-specific pagination handling
- [ ] Add HSSIB-specific metadata extraction
- [ ] Register scraper in ScraperFactory
- [ ] Add source entry to `sources.yaml`
- [ ] Write unit tests for HSSIB scraper
- [ ] Write integration tests for HSSIB scraper

#### 6.2 Victoria Coroner Scraper
- [ ] Analyze Coroners Court Victoria website structure
- [ ] Map selectors for findings database search
- [ ] Handle dynamic content loading (JavaScript)
- [ ] Implement PDF finding extraction
- [ ] Create `scrapers/au_vic_coroner.py` class
- [ ] Add healthcare case filtering logic
- [ ] Register scraper in ScraperFactory
- [ ] Add source entry to `sources.yaml`
- [ ] Write unit tests
- [ ] Write integration tests

#### 6.3 NSW Coroner Scraper
- [ ] Analyze NSW Coroners Court website structure
- [ ] Map selectors for findings pages
- [ ] Implement PDF extraction
- [ ] Create `scrapers/au_nsw_coroner.py` class
- [ ] Register scraper in ScraperFactory
- [ ] Add source entry to `sources.yaml`
- [ ] Write tests

#### 6.4 Queensland Coroner Scraper
- [ ] Analyze Queensland Coroners Court website structure
- [ ] Map selectors for findings
- [ ] Create `scrapers/au_qld_coroner.py` class
- [ ] Register scraper in ScraperFactory
- [ ] Add source entry to `sources.yaml`
- [ ] Write tests

#### 6.5 NZ HDC Scraper
- [ ] Analyze NZ Health & Disability Commissioner website
- [ ] Map selectors for decisions database
- [ ] Handle category filtering (public hospital, private hospital, etc.)
- [ ] Create `scrapers/nz_hdc.py` class
- [ ] Register scraper in ScraperFactory
- [ ] Add source entry to `sources.yaml`
- [ ] Write tests

#### 6.6 NZ Coronial Services Scraper
- [ ] Analyze NZ Coronial Services website structure
- [ ] Map selectors for findings
- [ ] Create `scrapers/nz_coroner.py` class
- [ ] Register scraper in ScraperFactory
- [ ] Add source entry to `sources.yaml`
- [ ] Write tests

### Priority 2: High (Should Complete)

#### Search Functionality
- [ ] Create `publishing/search_index.py` module
- [ ] Implement search index builder function
- [ ] Extract title, excerpt, tags from published posts
- [ ] Generate `search-index.json` during site generation
- [ ] Update `BlogGenerator._copy_assets()` to include search index
- [ ] Test search functionality end-to-end

#### Source Listing Pages
- [ ] Create `publishing/templates/source.html` template
- [ ] Add `_generate_source_page()` method to BlogGenerator
- [ ] Add source pages generation to `generate_all()` method
- [ ] Update sitemap to include source pages
- [ ] Test source page generation

#### Connect Manual Trigger to Scheduler
- [ ] Import scheduler module in admin routes
- [ ] Implement async trigger in `/sources/{id}/trigger` endpoint
- [ ] Add feedback on scrape completion status
- [ ] Add error handling for scraper failures
- [ ] Test manual trigger functionality

#### Password Security
- [ ] Add bcrypt to requirements.txt
- [ ] Update `admin/main.py` to use bcrypt verification
- [ ] Update settings to use `ADMIN_PASSWORD_HASH` correctly
- [ ] Add password hashing utility script
- [ ] Update `.env.example` with hash example
- [ ] Document password hash generation

### Priority 3: Medium (Should Complete When Possible)

#### Expand Test Coverage

##### Scraper Tests
- [ ] Create `tests/unit/test_scrapers.py`
- [ ] Add tests for BaseScraper methods
- [ ] Add tests for UK PFD scraper
- [ ] Mock HTTP requests using pytest-httpx

##### Analysis Tests
- [ ] Create `tests/unit/test_analysis.py`
- [ ] Add tests for LLM client classes
- [ ] Add tests for PromptTemplateLoader
- [ ] Add tests for AnalysisPipeline stages
- [ ] Mock LLM API responses

##### Publishing Tests
- [ ] Create `tests/unit/test_publishing.py`
- [ ] Add tests for BlogGenerator methods
- [ ] Add tests for BlogDeployer methods
- [ ] Add tests for template rendering

##### Integration Tests
- [ ] Expand `tests/integration/test_admin.py`
- [ ] Add full workflow tests
- [ ] Add E2E scrape-to-publish tests

#### Audit Log Automation
- [ ] Create PostgreSQL trigger function for audit logging
- [ ] Add trigger to sources table
- [ ] Add trigger to findings table
- [ ] Add trigger to analyses table
- [ ] Add trigger to posts table
- [ ] Create migration for triggers
- [ ] Test audit log population

### Priority 4: Low (Nice to Have)

#### SFTP Support
- [ ] Add paramiko to requirements.txt
- [ ] Create SFTP client class in deployer.py
- [ ] Add protocol detection based on port/config
- [ ] Test SFTP deployment

#### OAuth2 Authentication
- [ ] Add python-jose to requirements.txt
- [ ] Create auth service module
- [ ] Implement JWT token generation
- [ ] Implement token validation middleware
- [ ] Add login/logout endpoints
- [ ] Create login page template
- [ ] Add role-based access control

#### Human Factors Module
- [ ] Create `analysis/human_factors.py` module
- [ ] Extract SEIPS-specific logic from analyser.py
- [ ] Add severity scoring utilities
- [ ] Add factor categorization helpers
- [ ] Update analyser.py to use new module

---

## Improvement Opportunities

### Code Quality

1. **Type hints completion** - Add type hints to all function signatures
2. **Docstring coverage** - Ensure all public methods have docstrings
3. **Error handling standardization** - Create custom exception classes
4. **Logging consistency** - Use structured logging everywhere

### Performance

1. **Connection pooling** - Optimize database connection pool settings
2. **Caching** - Add Redis caching for frequent queries
3. **Async optimization** - Ensure all I/O operations are async
4. **Batch processing** - Optimize LLM calls with batching

### Operational

1. **Health checks** - Add comprehensive health endpoints
2. **Metrics** - Add Prometheus metrics export
3. **Monitoring** - Add alerting for scraper failures
4. **Backup** - Add database backup automation

### Documentation

1. **API documentation** - Enable Swagger UI in production
2. **Deployment guide** - Create production deployment docs
3. **Contributing guide** - Add CONTRIBUTING.md
4. **Architecture diagram** - Create visual system diagram

---

## Implementation Order (Recommended)

### Sprint 1: Core Scrapers
1. UK HSSIB scraper (highest value source)
2. Search functionality
3. Connect manual trigger

### Sprint 2: Australian Sources
1. Victoria Coroner scraper
2. NSW Coroner scraper
3. Queensland Coroner scraper

### Sprint 3: NZ Sources + Polish
1. NZ HDC scraper
2. NZ Coronial scraper
3. Source listing pages
4. Password security

### Sprint 4: Quality + Testing
1. Expand test coverage
2. Audit log automation
3. Documentation updates

---

## Files Summary

### Existing Files (Implemented)

```
config/
├── settings.py          ✅
├── logging.py           ✅
├── sources.yaml         ✅
└── prompts/
    ├── classify_healthcare.txt     ✅
    ├── extract_content.txt         ✅
    ├── analyse_human_factors.txt   ✅
    └── generate_blog_post.txt      ✅

database/
├── models.py            ✅
├── repository.py        ✅
├── connection.py        ✅
└── migrations/          ✅

scrapers/
├── base.py              ✅
├── uk_pfd.py            ✅
└── scheduler.py         ✅

analysis/
├── llm_client.py        ✅
├── analyser.py          ✅
└── processor.py         ✅

admin/
├── main.py              ✅
├── routes.py            ✅
├── api.py               ✅
└── templates/           ✅ (all)

publishing/
├── generator.py         ✅
├── deployer.py          ✅
└── templates/           ✅ (all except source.html)

tests/
├── conftest.py          ✅
└── unit/
    └── test_repository.py  ✅
```

### Missing Files (To Implement)

```
scrapers/
├── uk_hssib.py          ❌ Priority 1
├── au_vic_coroner.py    ❌ Priority 1
├── au_nsw_coroner.py    ❌ Priority 1
├── au_qld_coroner.py    ❌ Priority 1
├── nz_hdc.py            ❌ Priority 1
└── nz_coroner.py        ❌ Priority 1

publishing/
├── search_index.py      ❌ Priority 2
└── templates/
    └── source.html      ❌ Priority 2

analysis/
└── human_factors.py     ❌ Priority 4

tests/
├── unit/
│   ├── test_scrapers.py     ❌ Priority 3
│   ├── test_analysis.py     ❌ Priority 3
│   └── test_publishing.py   ❌ Priority 3
└── integration/
    └── test_workflow.py     ❌ Priority 3
```

---

## Conclusion

The Patient Safety Monitor implementation is **~82% complete** with all core functionality working. The primary gap is **Phase 6: Additional Scrapers** which represents the bulk of remaining work. The system is functional with the UK PFD source and can be used in production while additional scrapers are developed.

**Key Recommendations:**
1. Begin with UK HSSIB scraper (most similar to existing UK PFD)
2. Complete search functionality for better UX
3. Add password security before production deployment
4. Expand test coverage incrementally
