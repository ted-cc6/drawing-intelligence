"""The Q&A agent's loop (ADR 0011): tool calls, the answer check, the limits, the conversation's memory."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

from drawing_intelligence.llm.client import LLMClient
from drawing_intelligence.qa.data import DrawingData
from drawing_intelligence.qa.grounding import Corpus, check_answer
from drawing_intelligence.qa.tools import SCHEMAS, ToolBox

log = logging.getLogger(__name__)
SYSTEM = resources.files(__package__).joinpath("prompts/system.md").read_text(encoding="utf-8")
# the engineer's own message must give a verdict before record_feedback may run (prompt-injection guard)
_FEEDBACK_ASKED = re.compile(
    r"\b(feedback|false (alarm|positive)|not (a|an) (real )?(issue|problem)|real issue|"
    r"is (correct|right|wrong)|"
    r"(mark|record|log)\b.*\b(correct|incorrect|wrong|unsure|false)|incorrect|unsure)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Limits:
    max_tool_calls: int = 10
    max_regenerations: int = 4
    max_cost_usd: float = 0.50


@dataclass
class Answer:
    text: str
    verified: bool
    problems: list[str]
    tool_calls: list[str]
    regenerations: int
    cost_usd: float  # billed (cache hits are free)
    stopped_by: str | None = None  # "tool_calls" | "cost" when a limit ended the turn

    def display(self) -> str:
        out = self.text
        if self.stopped_by:
            limit = self.stopped_by.replace("_", " ")
            out += f"\n\n(stopped at the {limit} limit; the answer may be incomplete)"
        if not self.verified:
            out += "\n\n⚠ Couldn't verify: " + "; ".join(self.problems)
        return out


@dataclass
class Conversation:
    data: DrawingData
    client: LLMClient
    model: str | None = None
    thinking: str | None = None
    limits: Limits = field(default_factory=Limits)
    feedback_path: Path | None = None
    history: list[dict[str, Any]] = field(default_factory=list)  # compacted earlier turns
    corpus: Corpus = field(default_factory=Corpus)
    tools: ToolBox = field(init=False)

    def __post_init__(self) -> None:
        self.tools = ToolBox(self.data, self.feedback_path)
        self.overview = self.data.overview()
        self.corpus.add(self.overview)

    def system_message(self) -> dict[str, Any]:
        return {"role": "system", "content": f"{SYSTEM}\nOVERVIEW\n{self.overview}"}

    def ask(self, question: str) -> Answer:
        self.corpus.add(question)
        self.tools.feedback_allowed = bool(_FEEDBACK_ASKED.search(question))
        messages = [self.system_message(), *self.history, {"role": "user", "content": question}]
        used: list[str] = []
        regenerations = 0
        cost = 0.0
        stopped_by = None
        text, problems = "", ["no answer"]
        while True:
            if cost >= self.limits.max_cost_usd:
                stopped_by = "cost"
                break
            tools = SCHEMAS if len(used) < self.limits.max_tool_calls else []
            resp = self.client.chat(
                messages, tools, role="qa", node="qa", model=self.model, thinking=self.thinking
            )
            cost += 0.0 if resp.cached else resp.cost_usd
            if resp.tool_calls:
                messages.append(
                    {
                        "role": "assistant",
                        "content": resp.text or None,
                        "tool_calls": [
                            {
                                "id": c["id"],
                                "type": "function",
                                "function": {"name": c["name"], "arguments": c["arguments"]},
                            }
                            for c in resp.tool_calls
                        ],
                    }
                )
                for c in resp.tool_calls:
                    if len(used) >= self.limits.max_tool_calls:
                        result: dict[str, Any] = {
                            "error": "tool-call limit reached",
                            "hint": "answer now with what you have",
                        }
                        stopped_by = "tool_calls"
                    else:
                        used.append(f"{c['name']}({_short(c['arguments'])})")
                        result = self.tools.call(c["name"], c["arguments"])
                    content = json.dumps(result, ensure_ascii=False)
                    self.corpus.add(content)
                    messages.append({"role": "tool", "tool_call_id": c["id"], "content": content})
                continue
            text = resp.text.strip()
            problems = check_answer(text, self.data, self.tools.lookups, self.corpus)
            if not problems or regenerations >= self.limits.max_regenerations:
                break
            regenerations += 1
            messages.append({"role": "assistant", "content": text})
            messages.append(
                {
                    "role": "user",
                    "content": "Your answer failed the check: "
                    + "; ".join(problems)
                    + ". Rewrite it: cite IDs exactly as the tools print them and quote only numbers a "
                    "tool returned (call a tool if you need one). Do not mention this check.",
                }
            )
        if problems:
            log.warning("unverified Q&A answer: %s", "; ".join(problems))
        self._remember(question, text, used)
        return Answer(text, not problems, problems, used, regenerations, round(cost, 6), stopped_by)

    def _remember(self, question: str, text: str, used: list[str]) -> None:
        """Keep the question and answer; earlier tool results shrink to one line (fetchable again)."""
        self.history.append({"role": "user", "content": question})
        if used:
            self.history.append(
                {
                    "role": "system",
                    "content": "Tools used for the next answer (results dropped; "
                    "call them again if needed): " + ", ".join(used),
                }
            )
        self.history.append({"role": "assistant", "content": text or "(no answer)"})


def _short(arguments: str | dict[str, Any]) -> str:
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else arguments
    except ValueError:
        return str(arguments)[:40]
    return ", ".join(f"{k}={v}" for k, v in args.items())[:60]
