# utils/metrics.py

from dataclasses import dataclass, asdict

@dataclass
class LlmUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def to_dict(self):
        d = asdict(self)
        d["total_tokens"] = self.total_tokens
        return d


LLM_USAGE = LlmUsage()

def reset_llm_usage() -> None:
    LLM_USAGE.prompt_tokens = 0
    LLM_USAGE.completion_tokens = 0
    LLM_USAGE.calls = 0
