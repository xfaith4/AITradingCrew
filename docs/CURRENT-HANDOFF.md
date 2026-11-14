# AITradingCrew — Current Handoff

> Active operational context only. Newest entry first.

## 2026-11-13 — A4 fetch_/format_ split for four analysts (A4 next)

- **Did:** Commit 81016ba (local, not pushed). technical_indicators.py: fetch_technical_data returns TechnicalData (IndicatorSnapshot + PriceBars + quote), format_ti_context. social.py: fetch_stocktwits_sentiment returns SentimentSnapshot, format_stocktwits_sentiment. fundamental_analysis.py: fetch_fundamentals returns FundamentalData (FundamentalSnapshot + four prose sections; drops inconsistent price targets with a warning), format_fundamental_context. timegpt.py: fetch_forecast_point returns ForecastPoint, format_forecast_point. get_*_context are now thin wrappers. Added tests/test_analysts_structured.py (22 tests: golden equality, run-store round trips, comparison against the legacy TwelveTI path). ROADMAP: A4 progress note (left open), added X10 (Ichimoku sys.exit) and X11 (remove dead legacy TwelveTI methods).
- **Verified:** uv run pytest tests/test_golden_context.py tests/test_analysts_structured.py -q: 32 passed, 1 xfailed (X8 strict xfail). uv run pytest -q: 110 passed, 1 xfailed. Roadmap validator: score 100, L4, exit 0 (existing house-style warnings only). Not verified: a live keyed run.
- **Progress:** Roadmap progress appended: 4/53 items done, phases 0/0, 49 open-items left -> docs/ROADMAP-PROGRESS.md
- **Safe to proceed:** yes; tests green, A4 work committed locally on main, not pushed
- **Next:** Finish A4: add a golden for stock_headlines_fetcher.get_news_context, then split it into fetch_news (list[NewsItem]) and format_news; decide whether VIX/global market need a new A2 model or get carved out of A4 before stamping it
- **Owner:** Approve pushing to the fork; provide .env for a keyed run to record live fixtures (A1); decide on keyless demo-data slice.

## 2026-11-13 — Golden prompt-text fixtures for analyst context builders (A3) (A4 next)

- **Did:** Added tests/test_golden_context.py (11 tests: TI context, VIX, global market, StockTwits x2 + pagination, fundamentals full + partial failure, TimeGPT x2, strict xfail for Finviz UnboundLocalError). Inputs in tests/fixtures/golden/inputs (synthetic provider-shaped: deterministic OHLCV, Twelve Data quote, Yahoo chart, StockTwits pages, trimmed Finviz/TipRanks/ValueInvesting HTML); 9 goldens in tests/fixtures/golden/expected, regenerate with UPDATE_GOLDENS=1. Added .gitattributes (golden dir -text, repo has autocrlf=true). ROADMAP: A3 stamped done; added X8 (finviz UnboundLocalError) and X9 (sys.exit in TwelveDataManager bypasses per-asset except). Committed on main (local, not pushed).
- **Verified:** uv run pytest tests/test_golden_context.py -q: 10 passed, 1 xfailed. uv run pytest -q: 88 passed, 1 xfailed. Read every golden to confirm intended branches are hit. Not verified: goldens against recorded live responses (needs keyed run); VIX golden assumes local TZ within +/-11h of UTC.
- **Progress:** Roadmap progress appended: 4/51 items done, phases 0/0, 47 open-items left -> docs/ROADMAP-PROGRESS.md
- **Safe to proceed:** yes; tests green, A3 committed locally on main, not pushed
- **Next:** A4: split each analyst into fetch_* (A2 model) and format_* (existing text), keep get_*_context wrappers; check: uv run pytest tests/test_golden_context.py tests/test_analysts_structured.py -q
- **Owner:** Approve pushing to the fork; provide .env for a keyed run to record live fixtures (A1); decide on keyless demo-data slice.

## 2026-11-13 — Typed run models (A2) and SQLite run store (A5) (A3 next)

- **Did:** Added ai_trading_crew/models.py (A2: RunManifest, SymbolStatus, PriceBar, IndicatorPoint/Snapshot, SentimentSnapshot, NewsItem, FundamentalSnapshot, ForecastPoint, AnalystStance, Recommendation; Signal enum with -2..2 score; LLM-facing models accept labels like "Very Bullish" and ignore extra keys). Added ai_trading_crew/store/ (A5: schema.py with versioned transactional migrations, run_store.py RunStore over stdlib sqlite3 at output/aitc.sqlite, 11 tables plus schema_version, FK cascade, idempotent upserts, indicator_history query). Added tests/test_models.py (41) and tests/test_store.py (19). Stamped A2 and A5 done in ROADMAP.md. Nothing committed.
- **Verified:** uv run pytest tests -q: 78 passed offline, no keys. ai_trading_crew.models and .store import without keys. markdownlint ROADMAP.md: 0 issues. Invoke-RoadmapValidation.ps1 (run from GitHubRepoManagement root; it resolves rules relative to cwd): exit 0, score 100, L4, 0 errors. Not verified: store has no live data yet (no keys, A4/A8 not wired); FundamentalSnapshot fields are a guess at what A4 can parse from Finviz/TipRanks.
- **Progress:** Roadmap progress appended: 3/49 items done, phases 0/0, 46 open-items left -> docs/ROADMAP-PROGRESS.md
- **Safe to proceed:** yes; tests green, all work uncommitted on main pending owner approval to commit
- **Next:** A3: capture golden text fixtures for get_ti_context, get_stocktwits_context, get_fundamental_context, format_timegpt_forecast, get_vix, get_global_market from recorded inputs; check: uv run pytest tests/test_golden_context.py -q. If recorded API responses are not available, B1 figures (Plotly builders from store rows) can proceed in parallel since A5 is done.
- **Owner:** Provide .env with OPENROUTER_*, TWELVE_API_KEY, RAPID_API_KEY, TIMEGPT_API_KEY (A1 fixtures and A3 goldens need one keyed run); approve committing and pushing to the fork; decide on a keyless demo-data slice.

## 2026-11-13 — Fork, gitignore narrowing (X3), lazy LLM and Twelve Data init (A1 partial) (A2 next)

- **Did:** Forked to the owner account; origin now points to the fork, upstream to the original author. .gitignore: dropped blanket *.md/*.txt/*.html/*.png, now ignores output/, *_response.html, .claude/state/ (X3 done). config.py: cached get_llm(name) plus module __getattr__ for legacy names; crew.py and market_overview_agents.py call get_llm; twelve_data_manager singleton is lazy. pyproject: pytest dev dep, crawl4ai pinned <0.9 (0.9+ ships unclecode-litellm, which overwrites litellm and breaks import crewai). Added tests/conftest.py, test_config_import.py, test_gitignore.py. Nothing committed.
- **Verified:** uv run pytest tests -q: 18 passed. ai_trading_crew.main imports without keys. Roadmap validator: exit 0, score 100, L4, 0 errors; markdownlint ROADMAP.md: 0 issues. Not verified: a real pipeline run (no .env with API keys exists in this clone); no dashboard exists yet.
- **Progress:** Roadmap progress appended: 1/49 items done, phases 0/0, 48 open-items left -> docs/ROADMAP-PROGRESS.md
- **Safe to proceed:** yes; tests green, changes uncommitted on main pending owner review
- **Next:** A2: pydantic models in ai_trading_crew/models.py, then A5 store, B1 figures, C1 Streamlit scaffold; check: uv run pytest tests/test_models.py -q
- **Owner:** Provide a .env with OPENROUTER_*, TWELVE_API_KEY, RAPID_API_KEY, TIMEGPT_API_KEY to get real data; decide whether to add a keyless demo-data slice so a dashboard is visible before the full store lands; approve committing and pushing to the fork.

## 2026-11-13 — Capability assessment and first ROADMAP.md (A1 next)

- **Did:** Added ROADMAP.md (releases 0.2-0.7: structured run store, HTML visual report, Streamlit dashboard, conversational analyst, track record, scheduled delivery) and .markdownlint.jsonc (MD024 siblings_only, MD013 off). No code changed. README.md has pre-existing uncommitted edits by the owner; untouched.
- **Verified:** Invoke-RoadmapValidation.ps1 -MinimumMaturity L3-Contract-Ready -FailOnError: exit 0, score 100, L4, 0 errors, 25 warnings (R004/R011 parser artifacts: structure linter ends a release block at its first ### heading). npx markdownlint-cli2 ROADMAP.md: 0 issues. Not verified: no code or tests exist yet; X5 SYMBOLS comma parsing bug is inferred, not reproduced.
- **Progress:** Roadmap progress appended: 0/49 items done, phases 0/0, 49 open-items left -> docs/ROADMAP-PROGRESS.md
- **Safe to proceed:** yes; roadmap only, nothing committed; origin is the upstream author repo so nothing can be pushed until the owner forks
- **Next:** A1: add pytest harness and make ai_trading_crew.config importable without API keys (lazy get_llm factory), check: uv run pytest tests/test_config_import.py -q
- **Owner:** Decide whether to fork or re-point origin (currently the upstream author's repo); confirm Plotly + Streamlit choice for 0.3/0.4; note `.gitignore` line 51 (`*.md`) ignores ROADMAP.md and docs/ until X3 lands, so approve X3 before expecting to commit them. Progress count 49 includes 3 example bullets inside the roadmap's authoring comment (46 real items).
