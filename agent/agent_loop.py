"""Shared agent loop: runs Claude with tools until it calls a "submit" tool.

A manual loop instead of the SDK's tool runner, because the runner executes a
turn's tool calls one at a time; here they all run at once.
"""

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import anthropic

MODEL = "claude-opus-5-5"
MAX_TURNS = 40


def _run_tool(tools_by_name: dict, call) -> dict:
    tool = tools_by_name.get(call.name)
    try:
        if tool is None:
            raise ValueError(f"Unknown tool: {call.name}")
        return {"type": "tool_result", "tool_use_id": call.id, "content": tool.call(call.input)}
    except Exception as e:
        return {"type": "tool_result", "tool_use_id": call.id, "content": f"Error: {e}", "is_error": True}


def run_agent(system: str, prompt: str, tools: list, submit_tool, label: str) -> dict:
    """Run the agent and return the input of its successful `submit_tool` call."""
    client = anthropic.Anthropic()
    tools_by_name = {t.name: t for t in tools}
    messages = [{"role": "user", "content": prompt}]
    start = time.monotonic()

    def log(msg: str) -> None:
        print(f"[{label}] {msg}", file=sys.stderr)

    with ThreadPoolExecutor(max_workers=10) as pool:
        for _ in range(MAX_TURNS):
            t0 = time.monotonic()
            response = client.beta.messages.create(
                model=MODEL,
                max_tokens=16000,
                system=system,
                tools=[t.to_dict() for t in tools],
                output_config={"effort": "medium"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                messages=messages,
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
            results = list(pool.map(lambda c: _run_tool(tools_by_name, c), calls))
            log(f"   model {model_secs:.0f}s, {len(calls)} tool call(s) {time.monotonic() - t0:.0f}s")
            messages.append({"role": "user", "content": results})

            for c, r in zip(calls, results):
                if c.name == submit_tool.name and not r.get("is_error"):
                    log(f"done in {time.monotonic() - start:.0f}s")
                    return dict(c.input)
        else:
            raise RuntimeError(f"{label}: did not finish within {MAX_TURNS} turns")

    raise RuntimeError(f"{label}: finished without calling {submit_tool.name}")
