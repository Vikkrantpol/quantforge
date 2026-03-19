# Contributing

## Development Setup

```bash
chmod +x run.sh
./run.sh
```

Frontend runs on `http://localhost:5173`.
Backend runs on `http://localhost:8010`.

## Project Layout

- `backend/`: API, data ingestion, strategy logic, backtest engine, metrics, history
- `frontend/`: React application and dashboards
- `backend/tests/test_all.py`: backend regression suite

## Before Opening a PR

Run the backend tests:

```bash
pytest backend/tests/test_all.py -q
```

If you changed frontend behavior, also verify the app builds:

```bash
cd frontend
npm run build
```

## Contribution Guidelines

- Keep changes focused and well-scoped.
- Preserve the separation between data loading, signal generation, backtesting, and metrics.
- Add or update tests when changing strategy logic, execution logic, or API behavior.
- Document user-visible changes in `README.md` when setup, behavior, or supported features change.

## Issues and Pull Requests

- Use issues for bugs, regressions, feature requests, and architecture questions.
- In pull requests, describe the problem, the solution, and how you verified it.

