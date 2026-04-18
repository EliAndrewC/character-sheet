# URL fixture descriptors

Each `.fixture.json` here describes a mocked HTTP scenario: what URL the
user pastes, what the server should return, and what the importer should
do with it.

Files in this directory are **not** served over the network. The test
harness (to be written in Phase 3 as `tests/conftest.py` plus a
`httpx_mock` fixture) reads these descriptors and patches the HTTP
client used inside `app/services/import_ingest.py`.

## Descriptor schema

```json
{
  "url": "<URL the user pastes>",
  "mock_response": {
    "status": 200,
    "headers": {"Content-Type": "text/plain"},
    "body_file": "happy_google_doc_body.txt",
    "body_inline": "...",
    "redirects_to": "<URL>"
  },
  "expected": { ...same shape as edge-case .expected.json files... }
}
```

Exactly one of `body_file`, `body_inline`, or `redirects_to` should be
set on the mock.

`body_file` is resolved relative to this directory.
