**Project:** Fintech Portfolio Manager
**Architecture:** Domain-Driven Design (DDD), Python (FastAPI), SQLAlchemy 2.0 (Async), Redis, Celery.

**I. Core Architectural Invariants & Design Decisions**

* **Absolute Financial Precision:** Strict enforcement of Python `Decimal` (quantized appropriately) across all pricing, quantities, and balances. `float` is strictly isolated to AI/ML matrix calculations (e.g., Numpy) and must be explicitly coerced back to `Decimal` before interacting with the portfolio.
* **Concurrency & State Safety:** Database models representing mutable financial state (`Account`, `Position`, `Order`) inherit `OptimisticLockMixin` (`version_id`). Concurrent update conflicts raise `StaleDataError`, which must be caught and retried in Python logic via savepoints (`begin_nested`), never ignored or allowed to taint the parent session.
* **Immutable Double-Entry Accounting:** `Account.cash_balance` and `Position.quantity` are merely fast-read materialized views. The ultimate source of truth is the immutable `LedgerJournal` and `LedgerEntry` tables. End-of-Day (EOD) reconciliation mathematically verifies this parity.
* **Fail-Closed Risk & Execution:** The `PreTradeRiskEngine` defaults to rejection. Any missing data, stale market quotes (checked against `MAX_ACCEPTABLE_STALENESS_SECONDS`), or unhandled exceptions must block trade execution.
* **Zero-Trust API Boundaries (IDOR Prevention):** The API routing layer entirely discards user-provided identity fields (like `account_id` in a JSON request body). Identity is strictly extracted from cryptographically verified JWT claims via FastAPI Dependency Injection.
* **Process-Safe Async Workers:** Celery tasks operate via an `@run_async` decorator that provisions a fresh `asyncio` event loop per worker fork. Sharing global DB connection pools across forks is an explicitly forbidden anti-pattern.
* **Graceful AI Degradation:** LLM responses are coerced into strict Pydantic schemas. Parsing failures or JSON hallucinations must trigger neutral heuristic fallbacks, never runtime crashes.

**II. Repository Map & Bounded Contexts**

* **`src/core/` (Global Foundations)**
* `config.py`: Pydantic settings, environment variables, and cryptographic key entropy rules.
* `security.py`: Fernet symmetric encryption for broker credentials and JWT lifecycle management.
* `exceptions.py`: Granular domain error hierarchy (e.g., `DoubleEntryLedgerMismatchError`).
* `database.py`: SQLAlchemy 2.0 AsyncEngine, connection pooling, and base audit mixins.


* **`src/market_data/` (Ingestion & Pricing)**
* `client.py`: External broker API interfaces (mocked via GBM drift).
* `cache.py`: High-performance Redis serialization preserving exact `Decimal` states.
* `pricing.py`: Cache-first orchestrator with strict quote staleness validation and distributed locking.
* `websocket.py`: Redis Pub/Sub async streaming fan-out for live client tickers.


* **`src/portfolio/` (Accounting & Valuation)**
* `models.py`: Relational schema for Accounts, Positions, and Ledger structures.
* `ledger.py`: Atomic transaction boundaries enforcing double-entry invariants.
* `valuation.py`: Real-time Net Asset Value (NAV) and unrealized PnL calculation.
* `rebalance.py`: Calculates delta between current NAV and target algorithmic weights.


* **`src/trading/` (Order & Execution Management)**
* `schemas.py`: Pydantic inbound request validation (e.g., enforcing limit prices).
* `models.py`: Order book state machine (`PENDING` -> `OPEN` -> `FILLED`).
* `order_book.py`: Order Management System (OMS) routing and pre-trade risk invocation.
* `execution.py`: Execution Management System (EMS) binding market fills to atomic ledger settlements.


* **`src/risk/` (Compliance & Guardrails)**
* `limits.py`: Pre-trade checks blocking concentration breaches and Pattern Day Trading (FINRA 4210).
* `metrics.py`: Post-trade quantitative modeling (Historical Value at Risk, Volatility).


* **`src/ai_advisory/` (Robo-Advisor)**
* `profiling.py`: Maps demographic surveys to strict portfolio equity constraints.
* `sentiment.py`: Structured LLM parsing for news-based asset sentiment.
* `optimization.py`: Modern Portfolio Theory (MPT) variance-covariance matrix solving.


* **`tasks/` (Background Processing)**
* `worker.py`: Celery initialization and async execution boundaries.
* `market_sync.py`: Periodic sweeping of the order book against live market ticks.
* `end_of_day.py`: Heavy reconciliation jobs verifying ledger parity.


* **`src/api/` & `src/main.py` (Transport Layer)**
* `dependencies.py`: FastAPI DI graph injecting scoped DB sessions and JWT identities.
* `v1_*.py`: Isolated API routers for trading, portfolio, and market data.
* `main.py`: App lifecycle, CORS, global exception masking (mapping domain errors to standard HTTP responses).



fintech_portfolio_manager/
│
├── pyproject.toml              # Dependency and project management
├── README.md
│
├── src/
│   ├── __init__.py
│   │
│   ├── core/                   # Global configurations and base classes
│   │   ├── config.py           # Environment variables and secrets
│   │   ├── security.py         # JWT auth, hashing, and encryption
│   │   ├── exceptions.py       # Custom domain exceptions (e.g., InsufficientFundsError)
│   │   └── database.py         # SQLAlchemy engine, session maker, connection pooling
│   │
│   ├── market_data/            # Ingests and serves pricing data
│   │   ├── __init__.py
│   │   ├── client.py           # Mock integration with Bloomberg/Alpaca API
│   │   ├── pricing.py          # Real-time price fetching and VWAP calculation
│   │   ├── websocket.py        # Streaming live ticker data
│   │   └── cache.py            # Redis caching layer for fast price retrieval
│   │
│   ├── portfolio/              # Manages user accounts and holdings
│   │   ├── __init__.py
│   │   ├── models.py           # DB models: Account, Position, Transaction
│   │   ├── ledger.py           # Double-entry accounting logic for cash/asset movement
│   │   ├── valuation.py        # Calculates current portfolio Nav, PnL, and ROI
│   │   └── rebalance.py        # Logic to realign portfolio to target weights
│   │
│   ├── trading/                # Order management and execution
│   │   ├── __init__.py
│   │   ├── models.py           # DB models: Order, TradeExecution
│   │   ├── schemas.py          # Pydantic validation for incoming orders
│   │   ├── order_book.py       # Manages limit, market, and stop-loss orders
│   │   └── execution.py        # Async task: interacts with broker, updates ledger
│   │
│   ├── risk/                   # Compliance and pre-trade checks
│   │   ├── __init__.py
│   │   ├── limits.py           # Checks for pattern day trading, margin limits
│   │   └── metrics.py          # Calculates VaR (Value at Risk) and Volatility
│   │
│   ├── ai_advisory/            # The intelligent layer
│   │   ├── __init__.py
│   │   ├── optimization.py     # Modern Portfolio Theory (Efficient Frontier math)
│   │   ├── sentiment.py        # LLM integration for news sentiment scoring
│   │   └── profiling.py        # ML model to classify user risk tolerance
│   │
│   ├── api/                    # The REST API entrypoints (FastAPI)
│   │   ├── __init__.py
│   │   ├── dependencies.py     # Auth extraction, DB session injection
│   │   ├── v1_portfolio.py     # Endpoints: GET /portfolio, POST /rebalance
│   │   ├── v1_trading.py       # Endpoints: POST /order, GET /orders/{id}
│   │   └── v1_market.py        # Endpoints: GET /quote/{ticker}
│   │
│   └── main.py                 # FastAPI application factory and startup events
│
└── tasks/                      # Background asynchronous workers
    ├── __init__.py
    ├── worker.py               # Celery app initialization
    ├── end_of_day.py           # EOD reconciliation, dividend processing
    └── market_sync.py          # Periodic fetching of historical market data