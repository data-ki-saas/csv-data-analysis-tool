"""Dev-time tool: draft SEO metadata for a new frontend page using the
configured LLM provider (src/llm/client.py). Run this whenever a page is
added under frontend/src/app/, then paste the output into that route's
`export const metadata` (Next.js Metadata API) — see CLAUDE.md.

Usage (from backend/):
    uv run python -m scripts.generate_seo --route /pricing \\
        --description "Pricing page listing free and paid tiers"
"""

import argparse
import asyncio
import json
import sys

from src.llm.client import get_llm_provider
from src.llm.providers.base import LLMProvider

DEFAULT_KEYWORDS = [
    "data intelligence",
    "business intelligence",
    "csv to charts",
    "interactive charts",
]

SYSTEM_PROMPT = (
    "You are an SEO copywriter for a CSV data-analysis SaaS product. Given a "
    "page's route and purpose, write metadata for Next.js's Metadata API. "
    "Weave in the target keywords naturally where relevant to the page's "
    "actual content -- never keyword-stuff or claim a feature the page "
    "doesn't have. Respond with ONLY a JSON object with keys: "
    '"title" (<=60 chars, no site name suffix), "description" (<=160 '
    'chars), "keywords" (5-10 strings). No markdown fences, no commentary.'
)


def build_prompt(route: str, description: str, keywords: list[str]) -> str:
    return (
        f"Route: {route}\n"
        f"Page purpose: {description}\n"
        f"Target keywords to consider: {', '.join(keywords)}\n"
    )


async def generate_metadata(
    route: str, description: str, keywords: list[str], provider: LLMProvider
) -> dict:
    prompt = build_prompt(route, description, keywords)
    response = await provider.complete(prompt, system=SYSTEM_PROMPT, max_tokens=512)
    return json.loads(response)


def render_snippet(metadata: dict) -> str:
    return (
        "export const metadata: Metadata = {\n"
        f"  title: {json.dumps(metadata.get('title', ''))},\n"
        f"  description: {json.dumps(metadata.get('description', ''))},\n"
        f"  keywords: {json.dumps(metadata.get('keywords', []))},\n"
        "};"
    )


async def _run(args: argparse.Namespace) -> None:
    provider = get_llm_provider()
    try:
        metadata = await generate_metadata(args.route, args.description, args.keywords, provider)
    except json.JSONDecodeError:
        print("Model did not return valid JSON.", file=sys.stderr)
        raise SystemExit(1)

    print(json.dumps(metadata, indent=2))
    print()
    print("Paste into that route's layout.tsx (or page.tsx if it's a server component):")
    print()
    print(render_snippet(metadata))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route", required=True, help='e.g. "/pricing"')
    parser.add_argument("--description", required=True, help="What the page does or shows")
    parser.add_argument(
        "--keywords",
        nargs="*",
        default=DEFAULT_KEYWORDS,
        help="Target keywords to consider (defaults to the product's core SEO keywords)",
    )
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()
