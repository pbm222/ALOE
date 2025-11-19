# utils/llm.py
import os
import json
import time
from typing import Any, Dict, Optional

from dotenv import load_dotenv, find_dotenv
from groq import Groq

# Load env (.env.local in project root)
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
    """
    Call Groq chat completion and try hard to parse a JSON object.
    If parsing fails, return {"_error": "...", "_raw": "<model output>"}.
    """
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
            )
            content = resp.choices[0].message.content or ""
            text = content.strip()

            # Try direct JSON first
            import json
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                # Try to strip ```json ... ``` fences if present
                if text.startswith("```"):
                    # remove ```json or ``` and trailing ```
                    lines = text.splitlines()
                    # drop first and last fence lines
                    if len(lines) >= 2:
                        inner = "\n".join(lines[1:-1]).strip()
                    else:
                        inner = text
                    try:
                        return json.loads(inner)
                    except json.JSONDecodeError:
                        pass

                # As a last attempt, extract between first '{' and last '}'
                if "{" in text and "}" in text:
                    inner = text[text.find("{"): text.rfind("}") + 1]
                    try:
                        return json.loads(inner)
                    except json.JSONDecodeError:
                        pass

                # Give up, but keep raw content for debugging
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