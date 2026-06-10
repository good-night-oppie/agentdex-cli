"""Challenger agent: generate new tasks and rubrics for CL-bench contexts.

For each unique context in CL-bench-context-dedup.jsonl, calls an LLM to
generate a new task and corresponding evaluation rubrics based on abstract
rules (no few-shot examples). Output is compatible with CL-bench's eval pipeline.

Usage:
    python challenger.py --model gpt-5.2 --max-samples 3   # test run
    python challenger.py --model gpt-5.2 --workers 8        # full run
"""

import copy
import json
import os
import re
import argparse
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from pathlib import Path

from api_client import create_client


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def get_timestamp():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def log(message):
    print(f"[{get_timestamp()}] {message}")


def load_jsonl(file_path):
    data = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def append_jsonl(item, file_path):
    os.makedirs(os.path.dirname(file_path) if os.path.dirname(file_path) else ".", exist_ok=True)
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# API call with retry
# ---------------------------------------------------------------------------

def call_openai_api(client, messages, model, max_retries=3, retry_delay=3):
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
            )
            return response.choices[0].message.content, None
        except Exception as e:
            error_msg = str(e)
            if attempt < max_retries - 1:
                log(f"   Call failed (attempt {attempt + 1}): {error_msg[:100]}")
                time.sleep(retry_delay)
            else:
                log(f"   Final failure: {error_msg[:200]}")
                return None, error_msg
    return None, "Unknown error"


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _load_prompt(filename: str) -> str:
    """Load a prompt from prompts/ directory relative to this script."""
    prompt_path = Path(__file__).parent / "prompts" / filename
    return prompt_path.read_text(encoding="utf-8").strip()


CHALLENGER_SYSTEM_PROMPT = _load_prompt("challenger.txt")


def summarize_messages(messages: list[dict], max_chars: int = 8000) -> str:
    """Summarize context messages for the prompt, truncating if too long.

    Set max_chars=0 to disable truncation entirely.
    """
    parts = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if max_chars and len(content) > 3000:
            content = content[:1500] + "\n...[truncated]...\n" + content[-1000:]
        parts.append(f"[{role}]: {content}")

    text = "\n\n".join(parts)
    if max_chars and len(text) > max_chars:
        text = text[:max_chars] + "\n...[truncated]..."
    return text


def build_challenger_prompt(context_messages: list[dict], num_tasks: int = 1) -> list[dict]:
    """Build the LLM prompt for generating task(s) and rubrics.

    Uses abstract rules only — no few-shot examples from the dataset.
    """
    context_summary = summarize_messages(context_messages, max_chars=0)

    user_prompt = (
        f"## Conversation Context\n\n{context_summary}\n\n"
        f"## Your Task\n\n"
        f"Based on the conversation context above, generate exactly {num_tasks} "
        f"evaluation task(s), each with its own rubrics, following the rules in your instructions. "
        f"Each task should test a DIFFERENT aspect of the context. "
        f"Output ONLY the JSON object."
    )

    return [
        {"role": "system", "content": CHALLENGER_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def parse_challenger_response(response_text: str) -> dict | None:
    """Parse LLM response to extract {tasks: [{task, rubrics}, ...]}.

    Supports both new multi-task format and old single-task format (for backward
    compatibility).
    """
    # Try to find JSON block
    # First try code block
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL)
    if match:
        text = match.group(1)
    else:
        # Try raw JSON
        match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if match:
            text = match.group(0)
        else:
            return None

    try:
        data = json.loads(text)

        # Support both old format (single task) and new format (multiple tasks)
        if "tasks" in data and isinstance(data["tasks"], list):
            raw_tasks = data["tasks"]
        elif "task" in data and "rubrics" in data:
            # Backward compatibility: wrap single task in list
            raw_tasks = [{"task": data["task"], "rubrics": data["rubrics"]}]
        else:
            return None

        validated = []
        for t in raw_tasks:
            task_str = t.get("task", "").strip()
            rubrics = t.get("rubrics", [])
            if not task_str or not rubrics:
                continue
            if isinstance(rubrics, list) and all(isinstance(r, str) for r in rubrics):
                validated.append({"task": task_str, "rubrics": rubrics})

        if not validated:
            return None
        return {"tasks": validated}
    except (json.JSONDecodeError, AttributeError):
        return None


# ---------------------------------------------------------------------------
# Message assembly
# ---------------------------------------------------------------------------

def append_task_to_messages(messages: list[dict], new_task: str) -> list[dict]:
    """Append new task to messages with <|task|> delimiter.

    - If last turn is user: append <|task|> + task to that turn's content
    - Otherwise: add a new user turn with <|task|> + task
    """
    messages = copy.deepcopy(messages)

    if messages and messages[-1].get("role") == "user":
        messages[-1]["content"] = messages[-1]["content"] + "<|task|>" + new_task
    else:
        messages.append({"role": "user", "content": "<|task|>" + new_task})

    return messages


# ---------------------------------------------------------------------------
# Single context processing
# ---------------------------------------------------------------------------

def process_single_context(args):
    idx, item, client, model = args

    messages = item.get("messages", [])
    if not messages:
        return idx, None, "No messages found"

    # Build prompt and call LLM
    prompt_messages = build_challenger_prompt(messages)
    response_text, error = call_openai_api(client, prompt_messages, model)
    if error:
        return idx, None, f"API error: {error}"

    # Parse response
    parsed = parse_challenger_response(response_text)
    if not parsed:
        return idx, None, f"Parse error. Raw response: {response_text[:200]}"

    # Assemble output
    new_messages = append_task_to_messages(messages, parsed["task"])

    result = {
        "messages": new_messages,
        "rubrics": parsed["rubrics"],
        "metadata": item.get("metadata", {}),
        "idx": idx,
    }
    return idx, result, None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Challenger: generate new tasks and rubrics for CL-bench contexts"
    )
    parser.add_argument("--model", type=str, default="gpt-5.2", help="Model name")
    parser.add_argument("--input", type=str, default="CL-bench-context-dedup.jsonl", help="Deduped context file")
    parser.add_argument("--output", type=str, default="CL-bench-challenged.jsonl", help="Output file")
    parser.add_argument("--base-url", type=str, default=None,
                        help="API Base URL. Supports OpenAI, Azure (auto-detected), and custom APIs")
    parser.add_argument("--api-key", type=str, default=None, help="API Key")
    parser.add_argument("--workers", type=int, default=1, help="Concurrent workers")
    parser.add_argument("--max-samples", type=int, default=None, help="Max samples (for testing)")
    parser.add_argument("--retry-delay", type=int, default=3, help="Retry delay in seconds")
    args = parser.parse_args()

    log(f"Input: {args.input}")
    log(f"Output: {args.output}")
    log(f"Model: {args.model}")
    log(f"Workers: {args.workers}")

    # Load input data
    log("Loading deduped contexts...")
    data = load_jsonl(args.input)
    log(f"   {len(data)} contexts")

    if args.max_samples:
        data = data[:args.max_samples]
        log(f"   Limited to {args.max_samples} samples")

    # Setup API client
    api_key = args.api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        log("Error: Please set OPENAI_API_KEY or use --api-key")
        return

    base_url = args.base_url or os.getenv("OPENAI_BASE_URL")
    client = create_client(api_key, base_url)

    # Checkpoint/resume
    completed_indices = set()
    if os.path.exists(args.output):
        existing = load_jsonl(args.output)
        completed_indices = {item.get("idx") for item in existing if item.get("idx") is not None}
        log(f"Found {len(completed_indices)} completed, resuming remaining")

    tasks = [
        (idx, item, client, args.model)
        for idx, item in enumerate(data)
        if idx not in completed_indices
    ]

    if not tasks:
        log("All contexts already processed")
        return

    log(f"Generating tasks for {len(tasks)} contexts...")

    success_count = 0
    fail_count = 0

    if args.workers == 1:
        for task in tqdm(tasks, desc="Challenger"):
            idx, result, error = process_single_context(task)
            if result:
                append_jsonl(result, args.output)
                success_count += 1
            else:
                log(f"   Context {idx} failed: {error}")
                fail_count += 1
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(process_single_context, task): task[0] for task in tasks}
            with tqdm(total=len(tasks), desc="Challenger") as pbar:
                for future in as_completed(futures):
                    idx = futures[future]
                    try:
                        idx, result, error = future.result()
                        if result:
                            append_jsonl(result, args.output)
                            success_count += 1
                        else:
                            log(f"   Context {idx} failed: {error}")
                            fail_count += 1
                    except Exception as e:
                        log(f"   Context {idx} exception: {str(e)}")
                        fail_count += 1
                    pbar.update(1)

    log("=" * 50)
    log(f"Challenger completed!")
    log(f"   Success: {success_count}")
    log(f"   Failed: {fail_count}")
    log(f"   Output: {args.output}")


if __name__ == "__main__":
    main()
