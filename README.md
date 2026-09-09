# llm-port

[![CI](https://github.com/sanketnaik/llm-port/actions/workflows/ci.yml/badge.svg)](https://github.com/sanketnaik/llm-port/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Typed, provider-neutral chat and reliable tool calling for hosted and local LLMs.**

`llm-port` gives Python applications one contract for messages, tools, streaming, usage, and
errors. Provider adapters handle wire-format differences, while the conformance layer recovers,
validates, and repairs malformed tool calls before they reach your application.

> **Status:** alpha. The public surface described below is settled, but minor versions may still
> change it.

## Why llm-port?

- Use the same API with Anthropic, Gemini, Sarvam, OpenAI, Ollama, and LM Studio.
- Receive typed `Message`, `ToolCall`, `Usage`, and `StreamEvent` values.
- Declare a tool once and reuse its schema for provider calls and validation.
- Recover tool calls emitted as text by weak or local models.
- Apply bounded corrective retries and constrained decoding when supported.
- Normalize provider failures into a small exception hierarchy.

## Install

```bash
pip install llm-port
```

Python 3.12 or later is required. The only runtime dependency is `httpx`.

## Quick start

```python
from llm_port import LLMClient, LLMConfig, Provider

client = LLMClient(
    LLMConfig(
        provider=Provider.ANTHROPIC,
        model_name="your-model-name",
    )
)

reply = client.chat([
    {"role": "user", "content": "Name three prime numbers."},
])

print(reply.content)
print(reply.usage.input_tokens, reply.usage.output_tokens)
```

The API key is read from the provider's environment variable when `api_key` is not passed
explicitly. Use an OpenAI-compatible local endpoint by changing the configuration:

```python
client = LLMClient(
    LLMConfig(
        provider=Provider.OLLAMA,
        model_name="your-local-model",
        base_url="http://localhost:11434/v1",
    )
)
```

## Providers

| Provider           | `Provider` member    | Default base URL                                       | Credential          |
| ------------------ | -------------------- | ------------------------------------------------------ | ------------------- |
| Anthropic          | `Provider.ANTHROPIC` | `https://api.anthropic.com/v1`                          | `ANTHROPIC_API_KEY` |
| Google Gemini      | `Provider.GEMINI`    | `https://generativelanguage.googleapis.com/v1beta`      | `GEMINI_API_KEY`    |
| Sarvam             | `Provider.SARVAM`    | `https://api.sarvam.ai/v1`                              | `SARVAM_API_KEY`    |
| OpenAI             | `Provider.OPENAI`    | `https://api.openai.com/v1`                             | `OPENAI_API_KEY`    |
| Ollama             | `Provider.OLLAMA`    | `http://localhost:11434/v1`                             | not required        |
| LM Studio          | `Provider.LMSTUDIO`  | `http://localhost:1234/v1`                              | not required        |

Every default is overridable through `base_url` and `api_key`.

## Tool calling

Declare a tool once. The same `ToolSpec` produces each provider's wire format and drives
conformance validation.

```python
from llm_port import ToolSpec

read_file = ToolSpec.from_function_dict({
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Read a UTF-8 text file.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
            },
            "required": ["path"],
        },
    },
})

reply = client.chat(
    [{"role": "user", "content": "Read README.md."}],
    tools=[read_file],
)

for call in reply.tool_calls:
    print(call.id, call.name, call.arguments)
```

A spec can also be derived from a function's signature and docstring:

```python
def read_file(path: str, encoding: str = "utf-8") -> str:
    """Read a UTF-8 text file."""
    ...

read_file_spec = ToolSpec.from_callable(read_file)
```

`llm-port` validates tool-call structure but does not execute tools. Authorization, execution,
and semantic validation remain the application's responsibility.

### Returning results

Feed results back with a tool message keyed by the call id, then call again:

```python
from llm_port import Message

messages = [Message.user("Read README.md.")]
reply = client.chat(messages, tools=[read_file_spec])

messages.append(reply)
for call in reply.tool_calls:
    output = my_dispatch_table[call.name](**call.arguments)  # your code, your authorization
    messages.append(Message.tool(call.id, output))

final = client.chat(messages, tools=[read_file_spec])
```

## Tool-call conformance

Weak and locally hosted models frequently emit tool calls as prose, fenced JSON, or
pseudo-XML rather than in the provider's structured field. The conformance layer sits between
the adapter and your application and applies, in order:

1. **Recovery** — parse tool-shaped text into candidate calls when the provider returned none
   structurally. Recovered calls carry `origin="recovered"` so you can treat them differently.
2. **Validation** — check arguments against the declared schema.
3. **Repair** — coerce obvious mismatches (a JSON string where an object was declared, a numeric
   string where a number was declared), then spend up to `tool_repair_attempts` corrective round
   trips before raising `ToolCallValidationError`.

Each stage is configurable:

```python
LLMConfig(
    provider=Provider.OLLAMA,
    model_name="your-local-model",
    recover_text_tool_calls=True,   # parse tool calls out of plain text
    strict_tools=True,              # reject calls that violate their schema
    tool_repair_attempts=1,         # bounded corrective retries
    constrained_decoding=False,     # enforce schemas at decode time where supported
)
```

## Streaming

```python
for event in client.chat_stream(messages, tools=[read_file]):
    if event.kind == "content":
        print(event.text, end="", flush=True)
    elif event.kind == "tool_calls":
        pending_calls = event.tool_calls
    elif event.kind == "usage":
        usage = event.usage
    elif event.kind == "done":
        finish_reason = event.finish_reason
```

Tool calls are streamed by providers as argument fragments. `llm-port` accumulates those and
emits a single `tool_calls` event holding fully decoded arguments, so your code never parses a
partial JSON string.

## Errors

Every provider and transport failure is normalized onto one hierarchy rooted at `LLMPortError`:

```
LLMPortError
├── ConfigurationError        unusable configuration, missing credential
├── TransportError            no usable response
│   └── TimeoutError
├── ProviderError             the provider returned an error (carries status_code, body)
│   ├── AuthenticationError   401
│   ├── PermissionDeniedError 403
│   ├── NotFoundError         404 (unknown model or endpoint)
│   ├── RateLimitError        429 (carries retry_after)
│   ├── ServerError           5xx
│   ├── ContextLengthError    request exceeded the context window
│   └── ContentFilterError    provider refused on safety grounds
├── ResponseFormatError       response could not be decoded into port types
└── ToolCallError
    ├── ToolCallRecoveryError    tool-shaped text that could not be recovered
    └── ToolCallValidationError  recovered call violated its schema
```

Transport failures, `429`, and `5xx` are retried under the configured `RetryPolicy` with
exponential backoff and jitter; everything else is raised immediately.

```python
from llm_port import LLMPortError, RateLimitError

try:
    reply = client.chat(messages)
except RateLimitError as exc:
    wait_for(exc.retry_after)
except LLMPortError as exc:
    log.error("llm call failed", exc_info=exc)
```

## Scope

`llm-port` owns provider conversion, transport behavior, streaming, tool-call conformance, and
provider-neutral errors. It does not provide an agent loop, tool execution, conversation storage,
or automatic provider routing.

## Development

```bash
make setup            # create a venv at .venv and install llm-port with dev extras
make test             # run the offline unit test suite with coverage
make integration-test # run live provider tests (requires credentials)
make lint             # ruff check and format --check
make format           # apply formatting and autofixable lint rules
make typecheck        # mypy, strict mode
make check            # lint, typecheck, and test — what CI runs
make build            # build the sdist and wheel into dist/
make cleanup          # remove the venv, build output, and caches
```

`make help` lists every target. The default test suite is offline: unit tests stub the transport
and never open a socket. Live provider tests are opt-in — they live in `tests/integration`, carry
the `integration` marker, and skip themselves when the relevant credential is absent.

### Continuous integration

`.github/workflows/ci.yml` runs on every push and pull request to `main`: ruff and mypy, the
offline unit suite across Python 3.12 and 3.13 on Linux plus 3.12 on macOS, and a distribution
build that installs the wheel into a clean virtualenv and imports it. It mirrors `make check`,
so a green `make check` locally should stay green in CI.

Live provider tests run from `.github/workflows/integration.yml`, which is manual
(`workflow_dispatch`) and weekly only. It reads provider credentials from repository secrets
named after each provider's environment variable, gated behind an `integration` environment.

### Layout

```
src/llm_port/
├── client.py        LLMClient: the public entry point
├── config.py        Provider, LLMConfig, RetryPolicy
├── types.py         Message, ToolCall, Usage, StreamEvent
├── tools.py         ToolSpec and its per-provider renderings
├── errors.py        the exception hierarchy
├── conformance/     tool-call recovery, validation, and repair
└── providers/       one adapter per provider wire format
```

## Contributing

Issues and pull requests are welcome. Please run `make check` before opening a PR; new provider
adapters should ship with offline tests covering request construction, response parsing, streaming,
and error mapping.

## License

Licensed under the [MIT License](LICENSE).
