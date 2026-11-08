# Client examples

Both examples submit a scrape with an `Idempotency-Key`, poll the job until it
reaches a terminal state, and print the result. They use only standard-library
HTTP clients.

```bash
# Python 3.12+
SCRAPEFLOW_BASE_URL=https://api.example.com \
SCRAPEFLOW_API_KEY=sf_live_... \
python docs/examples/python_client.py https://example.com

# Node 18+
SCRAPEFLOW_BASE_URL=https://api.example.com \
SCRAPEFLOW_API_KEY=sf_live_... \
node docs/examples/node_client.mjs https://example.com
```

Create the key from the dashboard or `POST /v1/keys`. Keys are shown once; store
them in a secret manager, never in source control. API errors return
`{error: {code, message, details}, request_id}`; include the request id when
contacting support.

Do not point these examples at a development API with production data. For
browser-rendered pages set `render_js: true`; that consumes a browser session
and is subject to plan concurrency and credit limits.
