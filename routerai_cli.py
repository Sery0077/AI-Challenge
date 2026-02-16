#!/usr/bin/env python3
import argparse
import os
import sys

try:
    from openai import OpenAI
except Exception as exc:  # pragma: no cover - runtime dependency check
    print(
        "Missing dependency: openai. Install with: pip install openai",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc


BASE_URL = "https://routerai.ru/api/v1"
MODEL_ID = "deepseek/deepseek-v3.2"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Send a prompt to RouterAI using deepseek/deepseek-v3.2."
    )
    parser.add_argument(
        "prompt",
        nargs="+",
        help="Prompt text to send (use quotes for multi-word prompts).",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Stream the response tokens as they are generated.",
    )
    args = parser.parse_args()
    prompt = " ".join(args.prompt).strip()

    if not prompt:
        print("Prompt is empty.", file=sys.stderr)
        return 2

    api_key = os.environ.get("ROUTER_AI_API_KEY")
    if not api_key:
        print("ROUTER_AI_API_KEY is not set in the environment.", file=sys.stderr)
        return 2

    try:
        client = OpenAI(api_key=api_key, base_url=BASE_URL)
        if args.stream:
            stream = client.chat.completions.create(
                model=MODEL_ID,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
            )
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    print(delta.content, end="", flush=True)
            print()
        else:
            response = client.chat.completions.create(
                model=MODEL_ID,
                messages=[{"role": "user", "content": prompt}],
            )
            print(response.choices[0].message.content)
    except Exception as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
