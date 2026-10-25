# Security and operating limits

- Curated shared collections only. Service-token auth does not implement user or
  private-collection ACLs. OSCAR authenticates users and permits explicit opt-in;
  the service separately enforces its collection allowlist and document approval.
- Generate a random internal token, store outside Git, and rotate both processes
  together. Empty token fails closed. Comparison is constant-time. Never include
  it in URLs, screenshots or normal logs. Use TLS/private ingress across hosts.
- Keep DB and HTTP ports on loopback. Local Compose DB credentials are examples;
  production needs separate migration and least-privilege application roles,
  secret management, backups, encrypted transport and operator-reviewed access.
- Documents are untrusted data. Parsing never runs macros, JS or spreadsheet
  formulas. The approved-download helper accepts only a fixed host, validates
  public addresses and refuses redirects/proxies. Deployment egress policy should
  also pin permitted destinations to mitigate DNS rebinding and network changes.
- Manifests are local administrative inputs, validated against a bounded schema.
  Local file references must resolve below the manifest directory. Archives are
  inspected for traversal/size/ratio attacks and are not extracted to disk. Direct
  directory imports reject symlink files and are nonrecursive. Trusted curators
  must prevent filesystem replacement races while a job is processing.
- Size/row/page/chunk/batch/storage limits and a killable parser subprocess bound
  work. Native parser RAM is not strictly limited by Python: use container/OS
  memory and CPU quotas for untrusted material. Bounded Uvicorn concurrency and DB
  pools help; public exposure still needs ingress rate limiting and request deadlines.
- Retrieved text cannot grant permissions or alter system instructions. OSCAR's
  existing untrusted-data boundary remains. Sources never authorize writes,
  personal-memory creation, tool execution or decisions. Citation IDs are checked
  against the actual budgeted evidence, not trusted model-generated metadata.
- API evidence strips local paths and rejects credential-bearing/non-public
  citation URLs. Public source URLs omit query strings/fragments. Curators must
  avoid secrets/private paths inside titles, body text, and section metadata;
  this service is not a general-purpose secret-detection/redaction system.
- No raw text, prompts, credentials, private paths or provider response bodies in
  normal logs. Request IDs are generated server-side. Errors expose safe codes.
  API is read-only; administrative mutation stays in the local CLI.
- License approval is explicit. Preserve attribution, license, usage notes and
  third-party exceptions. MIT OCW is generally CC BY-NC-SA, not blanket commercial
  reuse permission. No paid/authenticated/DRM resource bypass is supported.
- Old normalized revisions and raw sources persist until an operator retention
  review. Soft deletion immediately excludes documents from retrieval; it does
  not erase backups or historical revisions. Coordinate approved removal from
  raw storage, DB and backups under the deployment's retention policy. No deletion
  automation is shipped in this MVP.
- Embedding credentials are separate from DeepSeek credentials. Embedding batches
  are paid when configured; tests use fake vectors only. Keyword mode costs no
  provider tokens. Limits: 32 texts/request, three retry attempts for retryable
  errors, 256 embedded chunks/document, one request at a time per worker. There is
  no account-wide dollar billing hard cap; use provider budgets and operator limits.
