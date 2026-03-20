"""Unified LLM client supporting Anthropic and OpenRouter providers."""
import json
import logging
import time

from src.config import ANTHROPIC_API_KEY, MODEL, OPENROUTER_API_KEY, PROVIDER
from src.cost_tracker import CostTracker

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAYS = [1, 2, 4]


def _create_client():
    """Create the appropriate API client based on PROVIDER config."""
    if PROVIDER == "openrouter":
        import openai
        return openai.OpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
        )
    else:
        import anthropic
        return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def _get_retry_exceptions():
    """Get the retryable exception types for the current provider."""
    if PROVIDER == "openrouter":
        import openai
        return (openai.APIError, openai.APIConnectionError, openai.RateLimitError)
    else:
        import anthropic
        return (anthropic.APIError, anthropic.APIConnectionError, anthropic.RateLimitError)


def _make_request(client, prompt: str, max_tokens: int = 4096) -> tuple[str, int, int, float | None]:
    """Make an API request and return (text, input_tokens, output_tokens, actual_cost_or_none)."""
    if PROVIDER == "openrouter":
        resp = client.chat.completions.create(
            model=MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.choices[0].message.content
        input_tokens = resp.usage.prompt_tokens
        output_tokens = resp.usage.completion_tokens
        # OpenRouter may include actual cost in usage
        actual_cost = None
        if hasattr(resp.usage, 'total_cost'):
            actual_cost = resp.usage.total_cost
        elif hasattr(resp, '_raw_response'):
            # Check headers for x-openrouter-cost
            try:
                headers = resp._raw_response.headers
                if 'x-openrouter-cost' in headers:
                    actual_cost = float(headers['x-openrouter-cost'])
            except Exception:
                pass
    else:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text
        input_tokens = resp.usage.input_tokens
        output_tokens = resp.usage.output_tokens
        actual_cost = None  # Anthropic doesn't return cost
    return text, input_tokens, output_tokens, actual_cost


def _extract_json(text: str) -> str:
    """Extract JSON from LLM response, handling markdown code blocks."""
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    return text.strip()


def call_llm(
    prompt: str,
    cost_tracker: CostTracker,
    call_type: str,
    level: int,
    max_tokens: int = 4096,
    client=None,
) -> dict:
    """Make an LLM API call with retry logic. Returns parsed JSON dict.

    Args:
        prompt: The prompt text to send
        cost_tracker: CostTracker instance for recording usage
        call_type: Type of call for cost tracking ("decompose", "vv", "judge", "refine")
        level: Level number for cost tracking
        max_tokens: Maximum tokens in response
        client: Optional pre-created client (reuse across calls for efficiency)
    """
    if client is None:
        client = _create_client()

    retry_exceptions = _get_retry_exceptions()

    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"API call: {call_type} L{level} (attempt {attempt + 1})")
            logger.debug(f"Prompt length: {len(prompt)} chars")

            text, input_tokens, output_tokens, actual_cost = _make_request(client, prompt, max_tokens)

            logger.debug(f"Response length: {len(text)} chars")
            cost_tracker.record(
                call_type=call_type,
                level=level,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                actual_cost=actual_cost,
            )

            json_text = _extract_json(text)
            return json.loads(json_text)

        except retry_exceptions as e:
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAYS[attempt]
                logger.warning(f"API error (attempt {attempt + 1}): {e}. Retrying in {delay}s...")
                time.sleep(delay)
            else:
                logger.error(f"API call failed after {MAX_RETRIES} attempts: {e}")
                raise
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from API response: {e}")
            logger.debug(f"Raw response: {text}")
            raise


def create_client():
    """Public factory for creating a reusable client."""
    return _create_client()
