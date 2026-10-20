# Remote provider routing

The pipeline can route either of its two roles (`draft` and `judge`) to a
free-tier remote API instead of local Ollama. This dramatically improves
prose quality (70B Llama vs 12B local) at the cost of sending manuscript
text to a third party.

**The default is fully local.** Remote routing is strictly opt-in via
environment variables.

## Supported providers

Both expose OpenAI-compatible chat completions and have free tiers with no
credit card requirement as of writing. Verify the current ToS yourself
before sending unpublished text.

| Provider | Free signup | Default draft model | Default judge model | Speed |
|---|---|---|---|---|
| **Groq** | [console.groq.com](https://console.groq.com) | `llama-3.3-70b-versatile` | `llama-3.1-8b-instant` | ~300 tok/s |
| **Cerebras** | [cloud.cerebras.ai](https://cloud.cerebras.ai) | `llama3.3-70b` | `llama3.1-8b` | often faster |

## Enable a provider

```bash
# 1. Sign up and copy your key. No credit card required.
export GROQ_API_KEY='gsk_...'

# 2. Choose which roles go remote.
export WRITER_DRAFT_PROVIDER=groq    # prose drafting goes to Groq
export WRITER_JUDGE_PROVIDER=local   # scoring stays local (faster, free)

# 3. Verify.
writer providers
```

`writer providers` shows what's reachable, what each role will resolve to,
and links to the relevant ToS/privacy URLs.

## Override the remote model name

If a default model is retired or you want a different size:

```bash
export WRITER_DRAFT_REMOTE_MODEL='llama-3.1-70b-versatile'
```

## Privacy

When a role is set to remote, every LLM call for that role sends:
- The chapter text being drafted or scored
- Slices of `WORLD_BIBLE.md` (for the Drafter)
- The chapter beat sheet (for the Drafter)

Both Groq and Cerebras state in their published ToS that they do **not**
train on customer inputs. That is a *contractual* protection only — you
cannot technically verify it from outside.

**For unpublished work**: if you are not comfortable with that contractual
promise, keep `WRITER_DRAFT_PROVIDER=local`. The local Ollama path sends
nothing anywhere.

## Auto-fallback to local

The router falls back to local Ollama in these cases:

1. **No internet.** A 3-second DNS check is cached for 30s. Skipping a
   provider when offline is instant.
2. **Network error during a call.** 15-second timeout per call, then
   fall back.
3. **Authentication failure (HTTP 401 / 403).** Immediate fall-back, plus
   the circuit breaker opens for this provider for the rest of the run.
4. **Rate limit (HTTP 429).** Fall back; the circuit breaker counts this
   as a failure.
5. **Malformed response.** Fall back; counts as a failure.
6. **3 consecutive failures.** Circuit breaker opens — no more remote
   attempts this run. Reset on next `writer start`.
7. **`--local-only` flag passed.** Hard-force local.

The user-visible message names the provider and the reason.

## Disabling remote for one run

```bash
writer start ~/books/my-series --local-only
```

This sets a process-local force-flag that bypasses every remote provider
regardless of env vars.

## Tool-using agents stay local

The Loremaster and Plotter agents use the Ollama tool-call protocol for
writing files. They always run locally, even when other roles are remote.
This is intentional — tool-calling syntax varies across providers and we
keep these short structural agents local for simplicity.

The Drafter, Reviser, Humanizer rewriter, Reader Panel, Critic Panel,
Continuity, and Humanizer detector all respect remote routing.

## Privacy reminders

- Setting a remote provider does NOT change KDP's "AI-generated" category.
  The text is still AI-generated regardless of where the AI ran. You still
  disclose. See [PUBLISHING.md](PUBLISHING.md).
- API keys live in your shell environment. The pipeline never writes them
  to `STATE.json` or any committed file.
- If you save keys in the Streamlit UI, they are stored locally in the
  book folder (`<project>/.env`) with owner-only permissions (0600). That
  file is the only place outside your shell where they are kept.

## Troubleshooting

```bash
writer providers   # what does the router see?
```

Common results:

- `local (WRITER_DRAFT_PROVIDER unset)` — env vars not set
- `local — provider groq configured but API key missing` — env var set,
  key not in environment (forgot to `export`)
- `local (circuit open)` — auth failed earlier this session; restart the
  process to retry
- `REMOTE → groq (llama-3.3-70b-versatile)` — good, remote is active
