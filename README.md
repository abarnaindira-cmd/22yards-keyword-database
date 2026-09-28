# Amazon Keyword Analysis System - Phase 1

This repository contains the backend service for the Amazon Keyword Analysis system, built with Python, FastAPI, MySQL, SQLAlchemy, Pydantic, and Uvicorn.

## Phase 1 Overview
Phase 1 establishes the project foundation and database setup:
- FastAPI application setup with dynamic lifespan table initialization.
- MySQL database connectivity using SQLAlchemy ORM and PyMySQL.
- Database schema for `keywords` with fields (`id`, `keyword`, `source`, `source_product_asin`, `category`, `relevance_score`, `created_at`, `updated_at`).
- Unique constraint `(keyword, source_product_asin, source)` to prevent duplicate keyword entries.
- Health-check endpoint `GET /health` and database verification endpoint `GET /api/keywords/test-db`.
- Full RESTful CRUD endpoints for keyword management.

---

## Project Structure
```text
amazon_keyword_analysis/
│
├── app/
│   ├── main.py              # FastAPI app initialization and /health route
│   ├── database.py          # SQLAlchemy MySQL configuration and connection pool
│   ├── models/
│   │   ├── __init__.py
│   │   └── keyword.py       # SQLAlchemy Keyword ORM model
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── keyword.py       # Pydantic Keyword schemas
│   ├── routers/
│   │   ├── __init__.py
│   │   └── keywords.py      # Keyword CRUD API router
│   └── services/
│       ├── __init__.py
│       └── keyword_collector.py # Playwright Amazon suggestion collector
│
├── .env                     # Environment configuration
├── .env.example             # Example environment template
├── .gitignore               # Git ignore rules
├── requirements.txt         # Project dependencies
└── README.md                # Phase 1 documentation
```

---

## Configuration (.env)
Set your MySQL database parameters in `.env`:
```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=root
DB_NAME=amazon_keyword_db
USE_SQLITE_FALLBACK=false
```

---

## Setup & Running

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the Application**:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

3. **Endpoints**:
   - Health Check: `GET http://localhost:8000/health`
   - Test DB Connection: `GET http://localhost:8000/api/keywords/test-db`
   - List Keywords: `GET http://localhost:8000/api/keywords`
   - Create Keyword: `POST http://localhost:8000/api/keywords`
   - Interactive OpenAPI Docs: `http://localhost:8000/docs`

## Phase 2 - Competitor Analysis

The project now supports a controlled competitor-analysis workflow:

`Product ASIN -> Existing Product Keywords -> Amazon Search -> Our Rank -> Top Competitor ASINs -> Competitor Product Details -> Competitor Keyword Suggestions -> MySQL`

### New MySQL tables
- `keyword_rankings`: displayed Amazon result position for each source product/keyword/result ASIN.
- `competitor_products`: top competitor products found for a source product keyword, including rank, title, URL, price, rating and review count when available.
- `competitor_keywords`: keyword suggestions associated with a competitor ASIN and the source product/keyword that led to the competitor.

### Controlled test
Run a read-only test first:
```bash
python run_competitor_analysis.py --products 3 --keywords-per-product 1 --top-competitors 5 --pages 1
```

To persist a validated test to MySQL:
```bash
python run_competitor_analysis.py --products 3 --keywords-per-product 1 --top-competitors 5 --pages 1 --write
```

The collector does not guess ASINs or ranks. If Amazon presents a CAPTCHA/access challenge or no product cards, the test reports an error instead of inventing data.

### API
- `POST /api/competitors/test` - controlled test; `write_db=false` by default.
- `GET /api/competitors/rankings` - inspect ranking records.
- `GET /api/competitors/products` - inspect competitor products.
- `GET /api/competitors/keywords` - inspect competitor keyword suggestions.
