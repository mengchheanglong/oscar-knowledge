# OSCAR integration

Existing backend and frontend stay independently deployed. No change is made to
OSCAR embedding settings, workspace ingestion/search, MAVIS, existing migrations,
Compose identity, model choice or generation provider.

The Knowledge service can now use local Qwen through Ollama independently of
OSCAR's generation provider. No OpenAI embedding key is needed in local mode.
DeepSeek generation still uses OSCAR's existing provider credentials. A verified
live DeepSeek conversation with Qwen-indexed citations is recorded in
[the Qwen report](QWEN_IMPLEMENTATION_REPORT.md).

Add to the **backend's private environment**, then restart its local process:

```dotenv
OSCAR_KNOWLEDGE_ENABLED=true
OSCAR_KNOWLEDGE_BASE_URL=http://127.0.0.1:8010
OSCAR_KNOWLEDGE_SERVICE_TOKEN=<same random value as KNOWLEDGE_SERVICE_TOKEN>
OSCAR_KNOWLEDGE_COLLECTION=mba-business
OSCAR_KNOWLEDGE_TIMEOUT_MS=2500
```

Defaults in the backend `.env.example` and Zod schema keep the feature disabled.
Missing configuration or an offline optional service does not prevent startup.
Do not use 127.0.0.1 from the backend container to address the host service; choose
an explicitly configured private-network URL and restrict it appropriately.
The URL is operator configuration, never supplied through the chat request.

The existing authenticated endpoint accepts:

```http
POST /api/v1/projects/<project-id>/ai/conversations/<conversation-id>/messages
Content-Type: application/json
Cookie: <existing OSCAR session>

{
  "content": "How should Rentify test its subscription pricing, using the synthetic course notes?",
  "clientRequestId": "<fresh UUID for this request and its retries>",
  "includeKnowledge": true
}
```

Project/session authorization remains enforced by existing guards and services.
The frontend **Course knowledge** checkbox sends this field per turn. It is off by
default and is not a personal-memory preference. Use ordinary assistant chat for
this demo; external agent execution modes have separate workflows.

The HTTP client caps top-k at four, response bytes at 100 KB, validates UUIDs,
source type, collection, locators, lengths, finite scores and safe public HTTPS
URLs. Redirects are rejected. Timeouts and malformed/unavailable responses degrade
to workspace evidence. An opted-in unavailable turn receives an explicit stored
notice; a no-match turn tells the model not to claim corpus support.

ContextAssembler keeps its overall approximate 4,000-token ceiling. With external
results it allocates at most 10,000 characters to workspace evidence and 5,000 to
external evidence plus shared bounded formatting. Only included, clipped chunks
are passed to the generator. Markers use the final ordered list. AssistantService
reconstructs citations from that same list and discards unknown chunk IDs. Optional
document/course/collection/URL/page/time metadata persists in existing citation
JSON. No external item pretends to be an internal project source.

The request fingerprint includes opt-in when true, while preserving the previous
fingerprint for absent/false requests. Reusing a request ID after changing opt-in
is rejected rather than silently reusing a different answer. Frontend request
signatures also include opt-in. After a page reload, changing options on an
unfinished historical request may produce the server's safe conflict; send a new
turn to resolve it. Optional knowledge is not retroactively added to old answers.

Citation cards display course/institution and the existing locator. External source
links accept public HTTPS URLs only; the inspector uses the stored excerpt rather
than querying OSCAR document tables with an external document ID. Synthetic
example.org identifiers are explicitly demo provenance, not hosted source files.

Regression commands (from backend):

```powershell
pnpm openapi:generate
pnpm lint
pnpm typecheck
pnpm test
pnpm test:e2e
pnpm db:test:up
pnpm test:integration
pnpm build
pnpm format:check
```

Read IMPLEMENTATION_REPORT.md for the checks actually completed. No live-model
answer is implied by mocked generation tests.
