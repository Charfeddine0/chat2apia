"""
Example ChatGPT Plus client using the chat2api proxy.

Features:
- Single-shot or interactive chat mode.
- Streams responses chunk-by-chunk for fast feedback.
- Accepts configuration from environment variables or CLI flags.

Usage (one-off prompt):
    CHATGPT_ACCESS_TOKEN="your_access_token" \
    CHAT2API_BASE_URL="http://127.0.0.1:5005" \
    python examples/chatgpt_plus_chat.py "اكتب لي نكتة قصيرة"

Interactive usage:
    python examples/chatgpt_plus_chat.py

Environment variables:
    CHATGPT_ACCESS_TOKEN: AccessToken or RefreshToken for your ChatGPT Plus account.
    CHAT2API_BASE_URL: chat2api base URL (default: http://127.0.0.1:5005).
    CHATGPT_MODEL: Model name to request (default: gpt-4o).
"""

import argparse
import json
import os
import sys
from typing import Iterable, List, MutableSequence

import requests


def stream_chat(prompt: str, *, client: requests.Session, base_url: str, model: str, token: str, system_prompt: str | None,
                history: MutableSequence[dict], stream: bool = True) -> str:
    messages: List[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    messages.extend(history)
    messages.append({"role": "user", "content": prompt})

    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
    }

    response = client.post(
        f"{base_url}/v1/chat/completions",
        headers=headers,
        json=payload,
        stream=stream,
        timeout=60,
    )
    response.raise_for_status()

    output = []
    if stream:
        for delta in iter_deltas(response):
            output.append(delta)
            print(delta, end="", flush=True)
        print()
    else:
        data = response.json()
        output_text = data["choices"][0]["message"]["content"]
        output.append(output_text)
        print(output_text)

    history.append({"role": "assistant", "content": "".join(output)})
    return "".join(output)


def iter_deltas(response: requests.Response) -> Iterable[str]:
    for line in response.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        if line.strip() == "data: [DONE]":
            break

        data = json.loads(line[6:])
        delta = data["choices"][0]["delta"].get("content")
        if delta:
            yield delta


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Chat with ChatGPT Plus through chat2api")
    parser.add_argument("prompt", nargs="?", help="Single prompt to send. If omitted, an interactive REPL starts.")
    parser.add_argument("--model", default=os.getenv("CHATGPT_MODEL", "gpt-4o"), help="Model name to request.")
    parser.add_argument("--base-url", default=os.getenv("CHAT2API_BASE_URL", "http://127.0.0.1:5005"),
                        help="chat2api base URL.")
    parser.add_argument("--token", default=os.getenv("CHATGPT_ACCESS_TOKEN", ""),
                        help="AccessToken or RefreshToken for your ChatGPT Plus account.")
    parser.add_argument("--system", default=None, help="Optional system prompt for steering responses.")
    parser.add_argument("--no-stream", action="store_true", help="Disable streaming; print the full reply at once.")
    return parser.parse_args()


def validate_base_url(url: str) -> str:
    cleaned = url.rstrip("/")
    if not cleaned.startswith("http://") and not cleaned.startswith("https://"):
        sys.exit("Base URL must start with http:// or https://")
    return cleaned


def main() -> None:
    args = parse_args()

    base_url = validate_base_url(args.base_url)
    token = args.token
    model = args.model
    system_prompt = args.system
    history: MutableSequence[dict] = []

    client = requests.Session()

    if args.prompt:
        stream_chat(
            args.prompt,
            client=client,
            base_url=base_url,
            model=model,
            token=token,
            system_prompt=system_prompt,
            history=history,
            stream=not args.no_stream,
        )
        return

    print("Starting interactive chat. Type ':quit' to exit.")
    if system_prompt:
        print(f"System prompt set: {system_prompt}\n")

    while True:
        try:
            user_input = input("You: ")
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if user_input.strip() in {":quit", ":exit"}:
            print("Goodbye!")
            break
        if not user_input.strip():
            continue

        history.append({"role": "user", "content": user_input})
        try:
            stream_chat(
                user_input,
                client=client,
                base_url=base_url,
                model=model,
                token=token,
                system_prompt=system_prompt,
                history=history,
                stream=not args.no_stream,
            )
        except requests.HTTPError as exc:  # pragma: no cover - runtime helper
            print(f"Request failed: {exc.response.status_code} - {exc.response.text}")
        except requests.RequestException as exc:  # pragma: no cover - runtime helper
            print(f"Network error: {exc}")


if __name__ == "__main__":
    main()
