"""Shared agent loop: runs Claude with tools until it calls a "submit" tool.

A manual loop instead of the SDK's tool runner, because the runner executes a
turn's tool calls one at a time; here they all run at once.
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context

import anthropic

MODEL = "claude-sonnet-5-5"
MAX_TURNS = 40


def configured_model() -> str:
    """Read after dotenv initialization; callers may configure each run."""
    return os.environ.get("ANTHROPIC_MODEL") or MODEL


def _run_tool(tools_by_name: dict, call) -> dict:
    tool = tools_by_name.get(call.name)
    try:
        if tool is None:
            raise ValueError(f"Unknown tool: {call.name}")
        return {"type": "tool_result", "tool_use_id": call.id, "content": tool.call(call.input)}
    except Exception as e:
        return {"type": "tool_result", "tool_use_id": call.id, "content": f"Error: {e}", "is_error": True}


def validate_max_workers(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10:
        raise ValueError("max_workers must be an integer between 1 and 10")
    return value


# Models that accept the server-side refusal fallback (see the Claude API docs); others run without it.
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}


def run_agent(
    system: str, prompt: str, tools: list, submit_tool, label: str, *,
    model: str | None = None, effort: str = "medium", max_workers: int = 4, max_turns: int = MAX_TURNS,
) -> dict:
    """Run the agent and return the input of its successful `submit_tool` call."""
    validate_max_workers(max_workers)
    if isinstance(max_turns, bool) or not isinstance(max_turns, int) or not 1 <= max_turns <= MAX_TURNS:
        raise ValueError(f"max_turns must be an integer between 1 and {MAX_TURNS}")
    model = model or configured_model()
    client = anthropic.Anthropic()
    tools_by_name = {t.name: t for t in tools}
    messages = [{"role": "user", "content": prompt}]
    start = time.monotonic()

    def log(msg: str) -> None:
        print(f"[{label}] {msg}", file=sys.stderr)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for _ in range(max_turns):
            t0 = time.monotonic()
            extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"} if model in FALLBACK_MODELS else {}
            response = client.beta.messages.create(
                model=model,
                max_tokens=16000,
                system=system,
                tools=[t.to_dict() for t in tools],
                output_config={"effort": effort},
                messages=messages,
                **extra,
            )
            model_secs = time.monotonic() - t0
            if response.stop_reason == "refusal":
                raise RuntimeError(f"{label}: request was declined: {response.stop_details}")
            messages.append({"role": "assistant", "content": response.content})

            calls = [b for b in response.content if b.type == "tool_use"]
            if not calls:
                break
            for c in calls:
                log(f"-> {c.name}: {json.dumps(c.input)[:110]}")
            t0 = time.monotonic()
            # Every worker needs its own copied Context. Session objects inside
            # that context remain shared within this run, but never between runs.
            # A submission can cite retrievals from the same model response, so
            # finish all retrievals before validating any submission.
            results = [None] * len(calls)
            pending = {
                index: pool.submit(copy_context().run, _run_tool, tools_by_name, call)
                for index, call in enumerate(calls) if call.name != submit_tool.name
            }
            for index, future in pending.items():
                results[index] = future.result()
            successful_submission = None
            for index, call in enumerate(calls):
                if call.name != submit_tool.name:
                    continue
                if successful_submission is not None:
                    results[index] = {
                        "type": "tool_result", "tool_use_id": call.id,
                        "content": "A report has already been submitted in this turn.", "is_error": True,
                    }
                    continue
                results[index] = _run_tool(tools_by_name, call)
                if not results[index].get("is_error"):
                    successful_submission = index
            log(f"   model {model_secs:.0f}s, {len(calls)} tool call(s) {time.monotonic() - t0:.0f}s")
            for c, r in zip(calls, results):
                if r.get("is_error"):
                    log(f"   ! {c.name} failed: {str(r['content'])[:200]}")
            messages.append({"role": "user", "content": results})

            if successful_submission is not None:
                log(f"done in {time.monotonic() - start:.0f}s")
                return dict(calls[successful_submission].input)
        else:
            raise RuntimeError(f"{label}: did not finish within {max_turns} turns")

    raise RuntimeError(f"{label}: finished without calling {submit_tool.name}")
