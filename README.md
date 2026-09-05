# capsolver

capsolver fastapi wrapper

## Realpage solver operations

`GET /turnstile/realpage/solver` keeps the existing `url` and `website_key`
parameters and returns `{"token": "..."}`. Requests have at most three attempts
and a 210-second overall timeout. Each attempt waits at most 30 seconds for a
pool slot, 45 seconds for a new browser, and 60 seconds for page loading and
solving. Failed browsers are closed; their slots are retained for lazy rebuild.

`GET /health` reports connected browsers, available slots and active requests.
It returns 503 while initializing or when no live browser remains. Docker's
existing health check and autoheal can therefore detect pool failure.

Run the regression tests with the project environment:

```sh
uv run python -m unittest test_solver
```

### Deployment check: 2026-09-05

- Five regression tests passed: repeated startup failure, solve failure and
  recovery, timeout/cancellation, bounded queue wait, and bounded retries.
- The production endpoint returned HTTP 200 with a token in 1.24 seconds;
  health reported four live browsers afterwards.
- Follow-up checks confirmed resumed data downloads: one running crawler had
  written 44 nonempty CSV files, and a sample for stock 3324 contained broker
  names, prices, and buy/sell quantities. The full batch was not yet complete.
  Intermittent HTTP 520, empty CSVs, and operation-timeout responses remained;
  do not treat the attempt progress bar as a successful-download count.
- Production image: `capsolver-api:pool-fix` (also tagged `capsolver-api:latest`).
  It uses the previous production dependencies and the updated source files.
- The stopped `capsolver-api-before-pool-fix` container and
  `capsolver-api:before-pool-fix` image are retained for rollback.

Rollback, if needed, after stopping the repaired service:

```sh
docker stop capsolver-api
docker rename capsolver-api capsolver-api-pool-fix-stopped
docker update --restart=no capsolver-api-pool-fix-stopped
docker rename capsolver-api-before-pool-fix capsolver-api
docker update --restart=always capsolver-api
docker tag capsolver-api:before-pool-fix capsolver-api:latest
docker start capsolver-api
```
