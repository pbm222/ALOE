# utils/llm.py
import os
import json
import time
from typing import Any, Dict, Optional

from dotenv import load_dotenv, find_dotenv
from groq import Groq

from utils.metrics import LLM_USAGE

load_dotenv(".env.local")
env_path = find_dotenv()
if env_path:
    load_dotenv(env_path)

api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    raise RuntimeError("GROQ_API_KEY is not set. Put it in .env.local or export it.")

model_name = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

client = Groq(api_key=api_key)


def ask_json(system_prompt: str, user_prompt: str, model: Optional[str] = None) -> Dict[str, Any]:
    m = model or model_name

    for attempt in range(5):
        try:
            resp = client.chat.completions.create(
                model=m,
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt + "\nYou MUST respond with ONLY a valid JSON object. No markdown, no explanation.",
                    },
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                stream=False,
            )

            usage = getattr(resp, "usage", None)
            if usage is not None:
                # OpenAI style: usage.prompt_tokens, usage.completion_tokens
                prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
                completion_tokens = getattr(usage, "completion_tokens", 0) or 0

                if prompt_tokens is None and isinstance(usage, dict):
                    prompt_tokens = usage.get("prompt_tokens", 0)
                if completion_tokens is None and isinstance(usage, dict):
                    completion_tokens = usage.get("completion_tokens", 0)

                prompt_tokens = prompt_tokens or 0
                completion_tokens = completion_tokens or 0

                LLM_USAGE.prompt_tokens += prompt_tokens
                LLM_USAGE.completion_tokens += completion_tokens
                LLM_USAGE.calls += 1

            content = resp.choices[0].message.content or ""
            text = content.strip()

            import json
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                if text.startswith("```"):
                    lines = text.splitlines()
                    if len(lines) >= 2:
                        inner = "\n".join(lines[1:-1]).strip()
                    else:
                        inner = text
                    try:
                        return json.loads(inner)
                    except json.JSONDecodeError:
                        pass

                if "{" in text and "}" in text:
                    inner = text[text.find("{"): text.rfind("}") + 1]
                    try:
                        return json.loads(inner)
                    except json.JSONDecodeError:
                        pass

                print(f"[red]Groq returned non-JSON:[/red] {text[:200]}...")
                return {"_error": "json_parse_failed", "_raw": text}

        except Exception as e:
            msg = str(e)
            if "429" in msg or "rate limit" in msg.lower():
                wait = 2 ** attempt
                print(f"[yellow]Groq rate limited: {msg} – retrying in {wait}s[/yellow]")
                time.sleep(wait)
                continue
            print(f"[red]Groq error: {msg}[/red]")
            return {"_error": msg}

    return {"_error": "max_retries_exceeded"}