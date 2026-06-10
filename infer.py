"""CL-bench Inference with Standard OpenAI API + Skill Injection.

Process message-format JSONL data through OpenAI-compatible APIs.
For the pure-API path (no OpenCode server), skills are loaded from skills/**/SKILL.md
and injected into the system message — mirroring what OpenCode does natively.

Output format is fully compatible with CL-bench's eval.py.

Usage:
    # With skills
    python infer.py --model gpt-5.2 --input CL-bench-with-task-delimiter.jsonl

    # Without skills (baseline)
    python infer.py --model gpt-5.2 --no-skills --input CL-bench-with-task-delimiter.jsonl
"""

import copy
import json
import os
import argparse
import time
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

from api_client import create_client

import yaml


# ---------------------------------------------------------------------------
# Utility functions
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
# Skill loading (mirrors OpenCode native behavior for the pure-API path)
# ---------------------------------------------------------------------------

def load_skills_by_context(skills_dir: Path) -> dict[str, dict]:
    """Load reasoner skills from skills_dir, indexed by context_id (directory name).

    Each skill lives in a UUID-named directory matching a context_id.
    Returns a dict mapping context_id -> {name, description, body}.
    Skips _-prefixed directories (templates/drafts).
    """
    if not skills_dir.exists():
        return {}

    skills = {}
    for skill_md in sorted(skills_dir.rglob("SKILL.md")):
        if skill_md.parent.name.startswith("_"):
            continue
        text = skill_md.read_text(encoding="utf-8")
        lines = text.split("\n")

        if not lines or lines[0].strip() != "---":
            continue

        closing_idx = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                closing_idx = i
                break
        if closing_idx is None:
            continue

        try:
            meta = yaml.safe_load("\n".join(lines[1:closing_idx])) or {}
        except yaml.YAMLError:
            continue

        context_id = skill_md.parent.name
        skills[context_id] = {
            "name": str(meta.get("name", context_id)),
            "description": str(meta.get("description", "")).strip(),
            "body": "\n".join(lines[closing_idx + 1:]).strip(),
        }
    return skills


def inject_skills_into_messages(messages: list[dict], skills: list[dict]) -> list[dict]:
    """Inject skill instructions into the messages list for standard API calls.

    Prepends skill catalog to the first system message's content.
    """
    if not skills:
        return messages

    sections = []
    for skill in skills:
        sections.append(
            f"### Skill: {skill['name']}\n"
            f"**When to use**: {skill['description']}\n\n"
            f"{skill['body']}"
        )

    skill_text = (
        "\n\n## Available Skills\n\n"
        "You have access to the following specialized skills. "
        "When a task matches a skill's description, follow its instructions.\n\n"
        + "\n\n---\n\n".join(sections)
    )

    messages = copy.deepcopy(messages)
    for msg in messages:
        if msg.get("role") == "system":
            msg["content"] = msg.get("content", "") + "\n" + skill_text
            return messages

    messages.insert(0, {"role": "system", "content": skill_text.strip()})
    return messages


# ---------------------------------------------------------------------------
# API call
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
# Single task processing
# ---------------------------------------------------------------------------

def process_single_case(args):
    idx, item, client, model, skills_by_context = args

    messages = item.get("messages")
    if not messages:
        return idx, None, "No messages found"

    # Look up skill by context_id for this sample
    context_id = item.get("metadata", {}).get("context_id", "")
    matched_skills = []
    if skills_by_context and context_id and context_id in skills_by_context:
        matched_skills = [skills_by_context[context_id]]

    if matched_skills:
        messages = inject_skills_into_messages(messages, matched_skills)

    response_text, error = call_openai_api(client, messages, model)
    if error:
        return idx, None, error

    result = {
        "idx": idx,
        "messages": item.get("messages"),  # Store original messages
        "model_output": response_text,
        "rubrics": item.get("rubrics", [])
    }
    return idx, result, None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Azure OpenAI API Inference for CL-bench (with Skills)")
    parser.add_argument("--model", type=str, default="gpt-5.2", help="Model name")
    parser.add_argument("--input", type=str, default="CL-bench-with-task-delimiter.jsonl", help="Input file path")
    parser.add_argument("--output", type=str, default=None, help="Output file path")
    parser.add_argument("--base-url", type=str, default=None,
                        help="API Base URL. Supports OpenAI, Azure (auto-detected), and custom APIs")
    parser.add_argument("--api-key", type=str, default=None, help="API Key (optional, defaults to env var)")
    parser.add_argument("--workers", type=int, default=1, help="Number of concurrent workers")
    parser.add_argument("--max-samples", type=int, default=None, help="Max samples to process (for testing)")
    parser.add_argument("--retry-delay", type=int, default=3, help="Retry delay in seconds")
    parser.add_argument("--no-skills", action="store_true", help="Disable skill injection (baseline mode)")
    parser.add_argument("--skills-dir", type=str, default="skills/reasoner", help="Directory containing reasoner skills (default: skills/reasoner)")
    args = parser.parse_args()

    if args.output is None:
        model_name_safe = args.model.replace("/", "_").replace(":", "_")
        suffix = "baseline" if args.no_skills else "skill"
        args.output = f"outputs/{model_name_safe}_{suffix}.jsonl"

    # Load skills indexed by context_id
    skills_by_context = {} if args.no_skills else load_skills_by_context(Path(args.skills_dir))
    if skills_by_context:
        log(f"Loaded {len(skills_by_context)} reasoner skill(s) from {args.skills_dir}")
    elif not args.no_skills:
        log(f"No skills found in {args.skills_dir}")

    log(f"Input file: {args.input}")
    log(f"Output file: {args.output}")
    log(f"Model: {args.model}")
    log(f"Workers: {args.workers}")

    api_key = args.api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        log("Error: Please set OPENAI_API_KEY or use --api-key argument")
        return

    base_url = args.base_url or os.getenv("OPENAI_BASE_URL")
    client = create_client(api_key, base_url)

    log("Loading data...")
    data = load_jsonl(args.input)
    log(f"   Total {len(data)} samples")

    if args.max_samples:
        data = data[:args.max_samples]
        log(f"   Limited to {args.max_samples} samples")

    completed_indices = set()
    if os.path.exists(args.output):
        existing_data = load_jsonl(args.output)
        completed_indices = {item.get("idx") for item in existing_data if item.get("idx") is not None}
        log(f"Found {len(completed_indices)} completed, resuming remaining")

    tasks = [(idx, item, client, args.model, skills_by_context) for idx, item in enumerate(data) if idx not in completed_indices]

    if not tasks:
        log("All samples already processed")
        return

    log(f"Starting inference ({len(tasks)} pending)...")

    success_count = 0
    fail_count = 0

    if args.workers == 1:
        for task in tqdm(tasks, desc="Inference"):
            idx, result, error = process_single_case(task)
            if result:
                append_jsonl(result, args.output)
                success_count += 1
            else:
                log(f"   Sample {idx} failed: {error}")
                fail_count += 1
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(process_single_case, task): task[0] for task in tasks}
            with tqdm(total=len(tasks), desc="Inference") as pbar:
                for future in as_completed(futures):
                    idx = futures[future]
                    try:
                        idx, result, error = future.result()
                        if result:
                            append_jsonl(result, args.output)
                            success_count += 1
                        else:
                            log(f"   Sample {idx} failed: {error}")
                            fail_count += 1
                    except Exception as e:
                        log(f"   Sample {idx} exception: {str(e)}")
                        fail_count += 1
                    pbar.update(1)

    log("=" * 50)
    log(f"Inference completed!")
    log(f"   Success: {success_count}")
    log(f"   Failed: {fail_count}")
    log(f"   Output: {args.output}")


if __name__ == "__main__":
    main()
