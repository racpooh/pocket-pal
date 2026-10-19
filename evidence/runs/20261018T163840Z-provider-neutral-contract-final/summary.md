# Provider-neutral contract review

- Added SDK-independent ChatModel/ExtractionProvider protocols, message/tool schemas and result/error types in model_contracts.py.
- Agent transcript now uses text, tool_calls and correlated tool-role results. Anthropic conversion is confined to the adapter. SDK request shape, output-limit handling and parallel-result correlation have offline tests.
- Existing imports remain compatible through re-exports in providers.py. No new vendor SDK, endpoint setting, automatic fallback or arbitrary plugin loader was added. Provider configuration remains restricted; another provider requires an implemented adapter and wiring/review.
- Full isolated test suite: 329 passed, 2 existing strict reference xfails, no failures/errors or ordinary skips. Fakes/scripted models and mocked Anthropic transport; no live calls. Earlier Anthropic live evidence predates this refactor and is not verification of this version against the external service.
- No-training compliance is not enforced by this interface. Contractual/configuration review and provider admission controls remain separate proposed work.
- Submission DOCX/Markdown reports were not edited at the owner's request. Network/routing/ingress/orchestration security additions remain proposals, not implemented controls.
- No Git commands, paid calls, demo resets or service restarts.
