"""
ReadMark — AI summarization.

A thin, provider-abstracted layer. Anthropic Claude is the default provider;
`summarize_text()` dispatches on settings.AI_PROVIDER, so adding OpenAI or
Amazon Bedrock later means adding one function, not rewriting callers.

Each call returns token usage and an estimated USD cost, which the caller
persists (AIUsage) and exports as metrics for cost monitoring / FinOps.
"""

from dataclasses import dataclass
from html.parser import HTMLParser

from config import settings

# ── Pricing (USD per 1M tokens) ───────────────────────────────────────────
# Keep this in sync with https://docs.anthropic.com/en/docs/about-claude/pricing
PRICING = {
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},
    "claude-sonnet-5":           {"input": 3.00, "output": 15.00},
    "claude-opus-4-8":           {"input": 15.00, "output": 75.00},
}
_DEFAULT_PRICE = {"input": 1.00, "output": 5.00}

MAX_INPUT_CHARS = 12000  # keep prompts (and cost) bounded


@dataclass
class SummaryResult:
    summary: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


class AIError(Exception):
    """Raised when a summary cannot be produced (misconfig or provider error)."""


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    price = PRICING.get(model, _DEFAULT_PRICE)
    cost = (input_tokens / 1_000_000) * price["input"] + \
           (output_tokens / 1_000_000) * price["output"]
    return round(cost, 6)


class _TextExtractor(HTMLParser):
    """Minimal HTML → text so we don't ship a heavy parser dependency."""
    def __init__(self):
        super().__init__()
        self._skip = False
        self.chunks = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.chunks.append(data.strip())


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass
    return " ".join(parser.chunks)


_PROMPT = (
    "Summarize the following article in 3-4 concise sentences. "
    "Focus on the key points a reader would want before deciding to read it. "
    "Do not add preamble like 'This article'.\n\n---\n\n{content}"
)


async def summarize_text(content: str) -> SummaryResult:
    """Summarize article text using the configured AI provider."""
    if not settings.ai_enabled:
        raise AIError("AI summarization is not configured (missing API key).")

    content = content.strip()[:MAX_INPUT_CHARS]
    if len(content) < 40:
        raise AIError("Not enough article text to summarize.")

    if settings.AI_PROVIDER == "anthropic":
        return await _summarize_anthropic(content)
    raise AIError(f"Unsupported AI provider: {settings.AI_PROVIDER}")


async def _summarize_anthropic(content: str) -> SummaryResult:
    from anthropic import AsyncAnthropic  # imported lazily so the dep is optional

    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    try:
        msg = await client.messages.create(
            model=settings.AI_MODEL,
            max_tokens=settings.AI_MAX_TOKENS,
            messages=[{"role": "user", "content": _PROMPT.format(content=content)}],
        )
    except Exception as e:  # surface provider errors as a clean 502 upstream
        raise AIError(f"Anthropic request failed: {e}") from e

    text = "".join(block.text for block in msg.content if getattr(block, "type", "") == "text").strip()
    in_tok, out_tok = msg.usage.input_tokens, msg.usage.output_tokens
    return SummaryResult(
        summary=text,
        provider="anthropic",
        model=settings.AI_MODEL,
        input_tokens=in_tok,
        output_tokens=out_tok,
        cost_usd=estimate_cost(settings.AI_MODEL, in_tok, out_tok),
    )
