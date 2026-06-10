"""Adversarial co-evolution loop for CL-bench.

Two agents compete: Challenger generates tasks+rubrics, Reasoner solves them.
The losing side receives a new skill via Proposer analysis. Skills accumulate
per context_id over 5 iterations, driving co-evolution.

Usage:
    python adversarial_loop.py --max-samples 1 --num-iterations 2   # test
    python adversarial_loop.py --max-samples 10 --num-iterations 5  # small run
"""

import copy
import json
import os
import re
import argparse
import threading
import time
import random
from datetime import datetime
from pathlib import Path
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

from api_client import create_client

from challenger import (
    CHALLENGER_SYSTEM_PROMPT,
    build_challenger_prompt,
    parse_challenger_response,
    append_task_to_messages,
    summarize_messages,
    call_openai_api,
    load_jsonl,
    append_jsonl,
)
from infer import inject_skills_into_messages
from eval import build_rubrics_text, call_judge_api

import yaml


# ---------------------------------------------------------------------------
# Skill loading (local version — infer.py no longer exports load_skills)
# ---------------------------------------------------------------------------

def load_skills(skills_dir: Path, pattern: str = "SKILL.md") -> list[dict]:
    """Load skill files matching pattern from a directory. Returns list of skill dicts.

    Each dict has keys: name, description, body.
    Skips files without valid YAML front-matter.
    """
    if not skills_dir.exists():
        return []

    results = []
    for skill_md in sorted(skills_dir.glob(pattern)):
        if skill_md.parent.name.startswith("_"):
            continue
        text = skill_md.read_text(encoding="utf-8")
        lines = text.split("\n")

        if not lines or lines[0].strip() != "---":
            # No front-matter — use raw content as body
            results.append({
                "name": skill_md.parent.name,
                "description": "",
                "body": text.strip(),
            })
            continue

        closing_idx = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                closing_idx = i
                break
        if closing_idx is None:
            results.append({
                "name": skill_md.parent.name,
                "description": "",
                "body": text.strip(),
            })
            continue

        try:
            meta = yaml.safe_load("\n".join(lines[1:closing_idx])) or {}
        except yaml.YAMLError:
            meta = {}

        results.append({
            "name": str(meta.get("name", skill_md.parent.name)),
            "description": str(meta.get("description", "")).strip(),
            "body": "\n".join(lines[closing_idx + 1:]).strip(),
        })
    return results


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def get_timestamp():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def log(message):
    print(f"[{get_timestamp()}] {message}")


# ---------------------------------------------------------------------------
# Proposer prompt
# ---------------------------------------------------------------------------

def _load_prompt(filename: str) -> str:
    """Load a prompt from prompts/ directory relative to this script."""
    prompt_path = Path(__file__).parent / "prompts" / filename
    return prompt_path.read_text(encoding="utf-8").strip()


CHALLENGER_PROPOSER_PROMPT = _load_prompt("challenger_proposer.txt")
REASONER_PROPOSER_PROMPT = _load_prompt("reasoner_proposer.txt")
CHALLENGER_GENERATOR_PROMPT = _load_prompt("challenger_generator.txt")
REASONER_GENERATOR_PROMPT = _load_prompt("reasoner_generator.txt")


def _format_rubric_status(rubrics, requirement_status):
    """Format per-rubric pass/fail status."""
    if requirement_status and len(requirement_status) == len(rubrics):
        lines = []
        for i, (rubric, status) in enumerate(zip(rubrics, requirement_status), 1):
            lines.append(f"  {i}. [{status}] {rubric}")
        return "\n".join(lines)
    return build_rubrics_text(rubrics)


def _format_skills_summary(existing_skills):
    """Format existing skills for proposer context."""
    if existing_skills:
        return "\n".join(
            f"- **{s['name']}**: {s['description']}" for s in existing_skills
        )
    return "(None — first iteration)"


def build_proposer_prompt(
    loser: str,
    context_messages: list[dict],
    all_task_results: list[dict],
    failure_traces: list[dict],
    existing_skills: list[dict],
    iteration: int,
) -> list[dict]:
    """Build prompt for the role-specific Proposer agent.

    Args:
        all_task_results: list of dicts, each with keys:
            - task_idx, task, rubrics, reasoner_output, judge_score,
              judge_rationale, requirement_status
        failure_traces: subset of all_task_results relevant to the loser
            (passed tasks for challenger, failed tasks for reasoner).
    """
    system_prompt = (
        CHALLENGER_PROPOSER_PROMPT if loser == "challenger"
        else REASONER_PROPOSER_PROMPT
    )

    skills_summary = _format_skills_summary(existing_skills)
    context_text = summarize_messages(context_messages, max_chars=0)

    # Build overview of all tasks
    summary_parts = []
    for tr in all_task_results:
        status = "PASSED" if tr["judge_score"] == 1 else "FAILED"
        summary_parts.append(
            f"- Task {tr['task_idx']}: [{status}] {tr['task'][:120]}..."
        )
    tasks_overview = "\n".join(summary_parts)

    # Build detailed traces for the relevant subset
    trace_parts = []
    for trace in failure_traces:
        task_rubrics = trace["rubrics"]
        rubrics_text = build_rubrics_text(task_rubrics)
        status_text = _format_rubric_status(task_rubrics, trace["requirement_status"])
        failed_indices = [
            i + 1 for i, s in enumerate(trace["requirement_status"])
            if str(s).lower() == "no"
        ]
        trace_parts.append(
            f"#### Task {trace['task_idx']} (failed rubrics: {failed_indices})\n"
            f"**Task**: {trace['task']}\n\n"
            f"**Rubrics**:\n{rubrics_text}\n\n"
            f"**Reasoner's Response**:\n{trace['reasoner_output']}\n\n"
            f"**Judge's Evaluation**:\n{trace['judge_rationale']}\n\n"
            f"**Per-Rubric Status**:\n{status_text}"
        )
    traces_section = "\n\n---\n\n".join(trace_parts)

    if loser == "challenger":
        analysis_instruction = (
            f"The Challenger generated {len(all_task_results)} tasks. "
            f"The Reasoner PASSED {len(failure_traces)} of them, meaning those tasks were too easy. "
            f"Analyze the PASSED tasks below to identify why they failed to challenge the Reasoner. "
            f"Look for patterns: were rubrics too lenient? Were tasks too straightforward? "
            f"Were there not enough complexity factors? Was there insufficient diversity across tasks?"
        )
    else:
        analysis_instruction = (
            f"The Challenger generated {len(all_task_results)} tasks. "
            f"The Reasoner FAILED {len(failure_traces)} of them. "
            f"Analyze the FAILED tasks below to identify common failure patterns across different tasks. "
            f"Look for recurring weaknesses: content gaps, format errors, constraint violations, "
            f"reasoning errors, or task misunderstanding."
        )

    user_prompt = (
        f"## Round {iteration} Failure Analysis\n\n"
        f"### Conversation Context\n{context_text}\n\n"
        f"### All Tasks Overview\n{tasks_overview}\n\n"
        f"### Analysis Focus\n{analysis_instruction}\n\n"
        f"### Detailed Traces for Analysis\n{traces_section}\n\n"
        f"### Existing Skills for {loser.capitalize()}\n{skills_summary}\n\n"
        f"Analyze the failure pattern and propose a skill improvement. Output ONLY the JSON object."
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def build_generator_prompt(
    loser: str,
    proposer_output: dict,
    existing_skills: list[dict],
) -> list[dict]:
    """Build prompt for the role-specific Generator agent."""
    system_prompt = (
        CHALLENGER_GENERATOR_PROMPT if loser == "challenger"
        else REASONER_GENERATOR_PROMPT
    )

    skills_summary = _format_skills_summary(existing_skills)

    user_prompt = (
        f"## Skill Proposal\n\n"
        f"**Action**: {proposer_output.get('action', 'create')}\n"
        f"**Target skill**: {proposer_output.get('target_skill', 'N/A')}\n"
        f"**Skill name**: {proposer_output['skill_name']}\n"
        f"**Description**: {proposer_output['skill_description']}\n\n"
        f"### Proposed Skill\n{proposer_output['proposed_skill']}\n\n"
        f"### Justification\n{proposer_output['justification']}\n\n"
        f"### Existing Skills\n{skills_summary}\n\n"
        f"Implement the skill as a complete SKILL.md. Output ONLY the JSON object."
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def parse_json_response(response_text: str, required_keys: list[str]) -> dict | None:
    """Parse JSON from LLM response. Tries code block first, then raw JSON."""
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL)
    if match:
        text = match.group(1)
    else:
        match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if match:
            text = match.group(0)
        else:
            return None

    try:
        data = json.loads(text)
        if all(data.get(k) for k in required_keys):
            return data
        return None
    except (json.JSONDecodeError, AttributeError):
        return None


def parse_proposer_response(response_text: str) -> dict | None:
    """Parse Proposer JSON response."""
    return parse_json_response(
        response_text,
        ["skill_name", "skill_description", "proposed_skill", "justification"],
    )


def parse_generator_response(response_text: str) -> dict | None:
    """Parse Generator JSON response."""
    return parse_json_response(response_text, ["skill_content"])


# ---------------------------------------------------------------------------
# Skill I/O
# ---------------------------------------------------------------------------

def load_skill_for_context(
    role: str, context_id: str, skills_base_dir: str = "skills",
    max_iteration: int = None
) -> list[dict]:
    """Load skills for a specific role/context_id.

    - Reasoner: Load skill-iter-{max_iteration}.md (contains cumulative content)
    - Challenger: Load single SKILL.md file (original behavior)

    Returns list of skill dicts.
    """
    skill_dir = Path(skills_base_dir) / role / context_id

    if role == "reasoner" and max_iteration is not None:
        # Load the latest cumulative reasoner skill file
        skill_path = skill_dir / f"skill-iter-{max_iteration}.md"
        if skill_path.exists():
            return load_skills(skill_dir, pattern=f"skill-iter-{max_iteration}.md")
        return []
    else:
        # Load single SKILL.md (challenger or reasoner without iteration)
        return load_skills(skill_dir)


def generate_and_save_skill(
    role: str,
    context_id: str,
    skill_content: str,
    iteration: int,
    skills_base_dir: str = "skills",
) -> str:
    """Write skill from Generator output. Returns file path.

    - Reasoner: Save to skill-iter-{iteration}.md with cumulative content
      (includes all skills from iteration 1 to current iteration)
    - Challenger: Append to SKILL.md (original behavior)
    """
    skill_dir = Path(skills_base_dir) / role / context_id
    skill_dir.mkdir(parents=True, exist_ok=True)

    if role == "reasoner":
        # Reasoner: cumulative file per iteration
        # Load previous iteration's content if exists
        if iteration > 1:
            prev_skill_path = skill_dir / f"skill-iter-{iteration - 1}.md"
            if prev_skill_path.exists():
                existing = prev_skill_path.read_text(encoding="utf-8")
                new_section = f"\n\n## Round {iteration} Update\n\n{skill_content}"
                cumulative_content = existing.rstrip() + new_section
            else:
                # Fallback: just use new content
                cumulative_content = skill_content
        else:
            # First iteration: just use new content
            cumulative_content = skill_content

        skill_path = skill_dir / f"skill-iter-{iteration}.md"
        skill_path.write_text(cumulative_content, encoding="utf-8")
    else:
        # Challenger: append to single SKILL.md
        skill_path = skill_dir / "SKILL.md"
        if skill_path.exists():
            existing = skill_path.read_text(encoding="utf-8")
            new_section = f"\n\n## Round {iteration} Update\n\n{skill_content}"
            skill_path.write_text(existing.rstrip() + new_section, encoding="utf-8")
        else:
            skill_path.write_text(skill_content, encoding="utf-8")

    return str(skill_path)


def save_hard_and_easy_tasks(
    context_id: str,
    task_results: list[dict],
    iteration: int,
    skills_base_dir: str = "skills",
    role: str = "reasoner"
):
    """Save hardest and easiest tasks from this iteration.

    Hardest: failed task with lowest rubric pass rate
    Easiest: random passed task with fewest rubrics
    """
    skill_dir = Path(skills_base_dir) / role / context_id
    skill_dir.mkdir(parents=True, exist_ok=True)

    hard_set_path = skill_dir / "hard_set.jsonl"
    easy_set_path = skill_dir / "easy_set.jsonl"

    # Find hardest task (failed with lowest pass rate)
    failed_tasks = [t for t in task_results if t["judge_score"] == 0]
    if failed_tasks:
        def calc_pass_rate(task):
            req_status = task.get("requirement_status", [])
            if not req_status:
                return 0.0
            passed = sum(1 for s in req_status if str(s).lower() == "yes")
            return passed / len(req_status)

        hardest = min(failed_tasks, key=calc_pass_rate)
        hardest_record = {
            "context_id": context_id,
            "iteration": iteration,
            "task": hardest["task"],
            "rubrics": hardest["rubrics"],
            "reasoner_output": hardest["reasoner_output"],
            "judge_score": hardest["judge_score"],
            "requirement_status": hardest["requirement_status"],
            "pass_rate": calc_pass_rate(hardest)
        }
        append_jsonl(hardest_record, hard_set_path)

    # Find easiest task (random passed task with fewest rubrics)
    passed_tasks = [t for t in task_results if t["judge_score"] == 1]
    if passed_tasks:
        min_rubrics = min(len(t["rubrics"]) for t in passed_tasks)
        candidates = [t for t in passed_tasks if len(t["rubrics"]) == min_rubrics]
        easiest = random.choice(candidates)

        easiest_record = {
            "context_id": context_id,
            "iteration": iteration,
            "task": easiest["task"],
            "rubrics": easiest["rubrics"],
            "reasoner_output": easiest["reasoner_output"],
            "judge_score": easiest["judge_score"],
            "requirement_status": easiest["requirement_status"],
            "num_rubrics": len(easiest["rubrics"])
        }
        append_jsonl(easiest_record, easy_set_path)


# ---------------------------------------------------------------------------
# Core agent steps
# ---------------------------------------------------------------------------

def challenger_generate(client, model, context_messages, challenger_skills, num_tasks=5):
    """Challenger generates multiple tasks, each with its own rubrics."""
    prompt_messages = build_challenger_prompt(context_messages, num_tasks=num_tasks)

    # Inject challenger skills into system prompt
    if challenger_skills:
        prompt_messages = inject_skills_into_messages(prompt_messages, challenger_skills)

    response_text, error = call_openai_api(client, prompt_messages, model)
    if error:
        return [], f"Challenger API error: {error}"

    parsed = parse_challenger_response(response_text)
    if not parsed:
        return [], f"Challenger parse error: {response_text[:200]}"

    return parsed["tasks"], None


def reasoner_solve(client, model, context_messages, task, reasoner_skills):
    """Reasoner solves the task."""
    messages_with_task = append_task_to_messages(context_messages, task)

    if reasoner_skills:
        messages_with_task = inject_skills_into_messages(
            messages_with_task, reasoner_skills
        )

    response_text, error = call_openai_api(client, messages_with_task, model)
    if error:
        return "", f"Reasoner API error: {error}"

    return response_text, None


def judge_evaluate(client, judge_model, rubrics, model_output, max_retries=3):
    """Judge evaluates reasoner output. Returns (score, rationale, req_status, error)."""
    rubrics_text = build_rubrics_text(rubrics)

    for attempt in range(1, max_retries + 1):
        result_text = call_judge_api(client, judge_model, rubrics_text, model_output)

        if not result_text:
            log(f"    Judge API failed (attempt {attempt}/{max_retries})")
            if attempt < max_retries:
                time.sleep(2)
                continue
            return 0, "Judge API failed", [], f"Judge API failed after {max_retries} attempts"

        try:
            result_json = json.loads(result_text)
            score = int(result_json.get("Overall Score", 0))
            rationale = result_json.get("Grading Rationale", "")
            status = result_json.get("List of Requirement Satisfaction Status", [])
            return score, rationale, status, None
        except (json.JSONDecodeError, ValueError) as e:
            log(f"    Judge parse error (attempt {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                time.sleep(2)

    return 0, "Judge parse failed", [], f"Judge parse error after {max_retries} attempts"


def propose_and_generate_skill(
    client, proposer_model, generator_model,
    context_id, context_messages, all_task_results,
    failure_traces, loser,
    existing_skills, iteration, skills_base_dir="skills",
    max_retries=3,
):
    """Two-step: Proposer analyzes failure(s) → Generator implements SKILL.md."""
    # Step 1: Proposer (with retry on parse failure)
    proposer_messages = build_proposer_prompt(
        loser, context_messages, all_task_results,
        failure_traces, existing_skills, iteration,
    )

    proposed = None
    for attempt in range(1, max_retries + 1):
        response_text, error = call_openai_api(client, proposer_messages, proposer_model)
        if error:
            log(f"    Proposer API error (attempt {attempt}/{max_retries}): {error}")
            if attempt < max_retries:
                time.sleep(2)
                continue
            return None, None, f"Proposer API error after {max_retries} attempts: {error}"

        proposed = parse_proposer_response(response_text)
        if proposed:
            break
        log(f"    Proposer parse error (attempt {attempt}/{max_retries}): {response_text[:200]}")
        if attempt < max_retries:
            time.sleep(2)

    if not proposed:
        return None, None, f"Proposer parse error after {max_retries} attempts"

    log(f"    Proposer → {proposed['action']} skill: {proposed['skill_name']}")

    # Step 2: Generator (with retry on parse failure)
    generator_messages = build_generator_prompt(loser, proposed, existing_skills)

    generated = None
    for attempt in range(1, max_retries + 1):
        response_text, error = call_openai_api(client, generator_messages, generator_model)
        if error:
            log(f"    Generator API error (attempt {attempt}/{max_retries}): {error}")
            if attempt < max_retries:
                time.sleep(2)
                continue
            return proposed, None, f"Generator API error after {max_retries} attempts: {error}"

        generated = parse_generator_response(response_text)
        if generated:
            break
        log(f"    Generator parse error (attempt {attempt}/{max_retries}): {response_text[:200]}")
        if attempt < max_retries:
            time.sleep(2)

    if not generated:
        return proposed, None, f"Generator parse error after {max_retries} attempts"

    skill_path = generate_and_save_skill(
        role=loser,
        context_id=context_id,
        skill_content=generated["skill_content"],
        iteration=iteration,
        skills_base_dir=skills_base_dir,
    )
    log(f"    Generator → {skill_path}")

    return proposed, generated, None


# Thread-safe file write lock
_write_lock = threading.Lock()


def append_jsonl_threadsafe(item, file_path):
    """Thread-safe version of append_jsonl."""
    with _write_lock:
        append_jsonl(item, file_path)


# ---------------------------------------------------------------------------
# Single context adversarial loop
# ---------------------------------------------------------------------------

def run_adversarial_rounds(
    context_item, client, challenger_model, reasoner_model,
    judge_model, proposer_model, generator_model, num_iterations=5,
    num_tasks=5, skills_base_dir="skills", output_path=None,
    start_iteration=1, skip_skill_selection=False,
):
    """Run adversarial co-evolution for a single context.

    Each round: Challenger generates `num_tasks` tasks (each with its own rubrics),
    Reasoner answers each task once. Both sides get skill updates independently:
    passed tasks → Challenger skill, failed tasks → Reasoner skill.

    Args:
        start_iteration: Which iteration to start from (for resume support).
    """
    messages = context_item["messages"]
    metadata = context_item.get("metadata", {})
    context_id = metadata.get("context_id", "unknown")

    rounds = []

    for iteration in range(start_iteration, num_iterations + 1):
        log(f"  [{context_id[:12]}...] Round {iteration}/{num_iterations}")

        # 1. Load current skills
        challenger_skills = load_skill_for_context("challenger", context_id, skills_base_dir)
        # Load previous iteration's skills (iteration-1) since current iteration's skills
        # are only generated at the end of this round
        reasoner_skills = load_skill_for_context(
            "reasoner", context_id, skills_base_dir,
            max_iteration=iteration - 1 if iteration > 1 else None
        )

        # 2. Challenger generates multiple tasks, each with its own rubrics
        tasks, error = [], None
        for challenger_try in range(1, 4):
            tasks, error = challenger_generate(
                client, challenger_model, messages, challenger_skills, num_tasks=num_tasks
            )
            if not error:
                break
            log(f"    Challenger attempt {challenger_try}/3 failed: {error}")
            time.sleep(2)
        if error:
            log(f"    Challenger failed after 3 attempts, skipping round")
            continue
        log(f"    Challenger → {len(tasks)} tasks")

        # 3. Reasoner answers each task once, Judge evaluates each
        task_results = []
        for task_idx, task_item in enumerate(tasks, 1):
            task_text = task_item["task"]
            task_rubrics = task_item["rubrics"]

            reasoner_output, error = reasoner_solve(
                client, reasoner_model, messages, task_text, reasoner_skills
            )
            if error:
                log(f"    Reasoner failed on task {task_idx}: {error}")
                task_results.append({
                    "task_idx": task_idx,
                    "task": task_text,
                    "rubrics": task_rubrics,
                    "reasoner_output": "",
                    "judge_score": 0,
                    "judge_rationale": f"Reasoner API error: {error}",
                    "requirement_status": [],
                })
                continue

            score, rationale, req_status, judge_error = judge_evaluate(
                client, judge_model, task_rubrics, reasoner_output
            )
            if judge_error:
                log(f"    Judge error on task {task_idx}: {judge_error}")

            task_results.append({
                "task_idx": task_idx,
                "task": task_text,
                "rubrics": task_rubrics,
                "reasoner_output": reasoner_output,
                "judge_score": score,
                "judge_rationale": rationale,
                "requirement_status": req_status,
            })
            log(f"    Task {task_idx}/{len(tasks)} → score={score}")

        if not task_results:
            log(f"    No task results produced, skipping round")
            continue

        # 4. Split results into passed and failed
        passed_tasks = [t for t in task_results if t["judge_score"] == 1]
        failed_tasks = [t for t in task_results if t["judge_score"] == 0]
        log(f"    Result: {len(passed_tasks)}/{len(task_results)} passed")

        # 5. Generate skills for both sides independently
        proposed_reasoner_skill = None
        proposed_challenger_skill = None

        # 5a. Reasoner skill: from failed tasks
        if failed_tasks:
            log(f"    Generating Reasoner skill from {len(failed_tasks)} failed tasks")
            proposed_reasoner_skill, _, error = propose_and_generate_skill(
                client, proposer_model, generator_model, context_id, messages,
                task_results, failed_tasks, "reasoner",
                reasoner_skills, iteration, skills_base_dir,
            )
            if error:
                log(f"    Reasoner Proposer/Generator failed: {error}")
        else:
            # Reasoner passed all tasks: copy previous skill to maintain continuity
            log(f"    Reasoner passed all {len(passed_tasks)} tasks, maintaining previous skill")
            skill_dir = Path(skills_base_dir) / "reasoner" / context_id
            skill_dir.mkdir(parents=True, exist_ok=True)

            if iteration > 1:
                prev_skill_path = skill_dir / f"skill-iter-{iteration - 1}.md"
                curr_skill_path = skill_dir / f"skill-iter-{iteration}.md"

                if prev_skill_path.exists():
                    # Copy previous skill and add note
                    content = prev_skill_path.read_text(encoding="utf-8")
                    note = (f"\n\n## Round {iteration} Update\n\n"
                           f"*No new skill generated - Reasoner passed all {len(passed_tasks)} tasks "
                           f"in this round. Previous skills remain effective.*\n")
                    curr_skill_path.write_text(content + note, encoding="utf-8")
                    log(f"    Copied skill-iter-{iteration-1}.md → skill-iter-{iteration}.md")
                else:
                    # Fallback: create placeholder
                    placeholder = (f"## Round {iteration}\n\n"
                                 f"*Reasoner passed all {len(passed_tasks)} tasks. "
                                 f"No previous skill file found.*\n")
                    curr_skill_path.write_text(placeholder, encoding="utf-8")
                    log(f"    Created placeholder skill-iter-{iteration}.md")
            else:
                # First iteration with all correct: create placeholder
                curr_skill_path = skill_dir / f"skill-iter-{iteration}.md"
                placeholder = (f"## Round {iteration}\n\n"
                             f"*Reasoner passed all {len(passed_tasks)} tasks in first round. "
                             f"No skill update needed.*\n")
                curr_skill_path.write_text(placeholder, encoding="utf-8")
                log(f"    Created placeholder skill-iter-{iteration}.md (first round, all correct)")

        # 5b. Challenger skill: from passed tasks
        if passed_tasks:
            log(f"    Generating Challenger skill from {len(passed_tasks)} passed tasks")
            proposed_challenger_skill, _, error = propose_and_generate_skill(
                client, proposer_model, generator_model, context_id, messages,
                task_results, passed_tasks, "challenger",
                challenger_skills, iteration, skills_base_dir,
            )
            if error:
                log(f"    Challenger Proposer/Generator failed: {error}")

        # 6. Record
        round_record = {
            "context_id": context_id,
            "iteration": iteration,
            "task_results": task_results,
            "num_tasks": len(task_results),
            "num_passed": len(passed_tasks),
            "num_failed": len(failed_tasks),
            "proposed_reasoner_skill": proposed_reasoner_skill,
            "proposed_challenger_skill": proposed_challenger_skill,
            "challenger_skills": [s["name"] for s in challenger_skills],
            "reasoner_skills": [s["name"] for s in reasoner_skills],
        }
        rounds.append(round_record)

        if output_path:
            append_jsonl_threadsafe(round_record, output_path)

        # Save hard and easy tasks for reasoner
        save_hard_and_easy_tasks(
            context_id=context_id,
            task_results=task_results,
            iteration=iteration,
            skills_base_dir=skills_base_dir,
            role="reasoner"
        )

    # After all iterations complete for this context, finalize best skill
    skill_dir = Path(skills_base_dir) / "reasoner" / context_id
    final_skill_path = skill_dir / "SKILL.md"

    if skip_skill_selection:
        # Use last iteration as best skill
        log(f"  [{context_id[:12]}...] All {num_iterations} rounds completed, using last iteration as best skill...")
        last_skill_path = skill_dir / f"skill-iter-{num_iterations}.md"

        if last_skill_path.exists():
            content = last_skill_path.read_text(encoding="utf-8")
            final_skill_path.write_text(content, encoding="utf-8")
            log(f"  [{context_id[:12]}...] ✅ Using iteration {num_iterations} (last) → SKILL.md")
        else:
            log(f"  [{context_id[:12]}...] ⚠️  skill-iter-{num_iterations}.md not found")
    else:
        # Select best skill through evaluation
        log(f"  [{context_id[:12]}...] All {num_iterations} rounds completed, selecting best skill...")
        best_skill_result = select_best_skill_for_context(
            context_id=context_id,
            num_iterations=num_iterations,
            skills_base_dir=skills_base_dir,
            client=client,
            reasoner_model=reasoner_model,
            judge_model=judge_model,
            context_messages=messages
        )

        if best_skill_result:
            # Copy best skill to SKILL.md
            best_iter = best_skill_result["best_iteration"]

            best_skill_path = skill_dir / f"skill-iter-{best_iter}.md"

            if best_skill_path.exists():
                content = best_skill_path.read_text(encoding="utf-8")
                final_skill_path.write_text(content, encoding="utf-8")

            log(f"  [{context_id[:12]}...] ✅ Best skill: iteration {best_iter} "
                f"(score={best_skill_result['best_score']:.4f}) → SKILL.md")

            # Save selection result to summary file
            summary_path = Path(skills_base_dir) / "skill_selection_summary.jsonl"
            append_jsonl(best_skill_result, summary_path)
        else:
            log(f"  [{context_id[:12]}...] ⚠️  No test sets found, skipping skill selection")

    return rounds


def select_best_skill_for_context(
    context_id: str,
    num_iterations: int,
    skills_base_dir: str,
    client,
    reasoner_model: str,
    judge_model: str,
    context_messages: list[dict]
) -> dict:
    """Test each skill version and select the best one.

    Returns: {
        "best_iteration": int,
        "best_score": float,
        "hard_accuracy": float,
        "easy_accuracy": float,
        "all_results": list[dict]
    }
    """
    skill_dir = Path(skills_base_dir) / "reasoner" / context_id
    hard_set_path = skill_dir / "hard_set.jsonl"
    easy_set_path = skill_dir / "easy_set.jsonl"

    # Load test sets
    hard_set = load_jsonl(hard_set_path) if hard_set_path.exists() else []
    easy_set = load_jsonl(easy_set_path) if easy_set_path.exists() else []

    if not hard_set and not easy_set:
        log(f"  [{context_id[:12]}...] No test sets found, skipping selection")
        return None

    results = []

    for iteration in range(1, num_iterations + 1):
        # Load cumulative skills (1 to iteration)
        skills = load_skill_for_context(
            "reasoner", context_id, skills_base_dir, max_iteration=iteration
        )

        # Test on hard set with API failure tracking
        hard_correct = 0
        hard_failed_api = 0
        for item in hard_set:
            output, _ = reasoner_solve(
                client, reasoner_model, context_messages,
                item["task"], skills
            )
            # Check if reasoner_solve failed (returns empty or error message)
            if not output or output.startswith("Error:"):
                hard_failed_api += 1
                continue

            score, _, _, _ = judge_evaluate(
                client, judge_model, item["rubrics"], output
            )
            # Check if judge_evaluate failed (returns -1 on error)
            if score == -1:
                hard_failed_api += 1
                continue

            if score == 1:
                hard_correct += 1

        # Calculate accuracy only on valid tests (with Laplace smoothing)
        hard_valid = len(hard_set) - hard_failed_api
        hard_acc = (hard_correct + 1) / (hard_valid + 1)

        # Warn if too many API failures
        if hard_valid > 0 and hard_failed_api / len(hard_set) > 0.3:
            log(f"  ⚠️  [{context_id[:12]}...] Iter {iteration}: {hard_failed_api}/{len(hard_set)} hard set API failures ({hard_failed_api/len(hard_set):.1%})")

        # Test on easy set with API failure tracking
        easy_correct = 0
        easy_failed_api = 0
        for item in easy_set:
            output, _ = reasoner_solve(
                client, reasoner_model, context_messages,
                item["task"], skills
            )
            # Check if reasoner_solve failed
            if not output or output.startswith("Error:"):
                easy_failed_api += 1
                continue

            score, _, _, _ = judge_evaluate(
                client, judge_model, item["rubrics"], output
            )
            # Check if judge_evaluate failed
            if score == -1:
                easy_failed_api += 1
                continue

            if score == 1:
                easy_correct += 1

        # Calculate accuracy only on valid tests (with Laplace smoothing)
        easy_valid = len(easy_set) - easy_failed_api
        easy_acc = (easy_correct + 1) / (easy_valid + 1)

        # Warn if too many API failures
        if easy_valid > 0 and easy_failed_api / len(easy_set) > 0.3:
            log(f"  ⚠️  [{context_id[:12]}...] Iter {iteration}: {easy_failed_api}/{len(easy_set)} easy set API failures ({easy_failed_api/len(easy_set):.1%})")

        # Combined score
        combined_score = hard_acc * easy_acc

        results.append({
            "iteration": iteration,
            "hard_accuracy": hard_acc,
            "easy_accuracy": easy_acc,
            "combined_score": combined_score,
            "hard_total": len(hard_set),
            "easy_total": len(easy_set),
            "hard_valid": hard_valid,
            "easy_valid": easy_valid,
            "hard_failed_api": hard_failed_api,
            "easy_failed_api": easy_failed_api
        })

        log(f"  [{context_id[:12]}...] Iter {iteration}: "
            f"hard={hard_acc:.2%} ({hard_correct}/{hard_valid}) "
            f"easy={easy_acc:.2%} ({easy_correct}/{easy_valid}) "
            f"combined={combined_score:.4f}")

    # Select best iteration
    best = max(results, key=lambda x: x["combined_score"])

    return {
        "context_id": context_id,
        "best_iteration": best["iteration"],
        "best_score": best["combined_score"],
        "hard_accuracy": best["hard_accuracy"],
        "easy_accuracy": best["easy_accuracy"],
        "all_results": results
    }


def finalize_best_skills(
    contexts: list[dict],
    num_iterations: int,
    skills_base_dir: str,
    client,
    reasoner_model: str,
    judge_model: str
):
    """For each context, select and save the best skill version."""
    log("=" * 60)
    log("Selecting best skills for each context...")
    log("=" * 60)

    selection_results = []

    for item in contexts:
        context_id = item.get("metadata", {}).get("context_id", "")
        if not context_id:
            continue

        context_messages = item.get("messages", [])

        result = select_best_skill_for_context(
            context_id=context_id,
            num_iterations=num_iterations,
            skills_base_dir=skills_base_dir,
            client=client,
            reasoner_model=reasoner_model,
            judge_model=judge_model,
            context_messages=context_messages
        )

        if result:
            selection_results.append(result)

            # Copy best skill to SKILL.md
            skill_dir = Path(skills_base_dir) / "reasoner" / context_id
            best_iter = result["best_iteration"]

            # Simply copy the best iteration file (already contains cumulative content)
            best_skill_path = skill_dir / f"skill-iter-{best_iter}.md"
            final_skill_path = skill_dir / "SKILL.md"

            if best_skill_path.exists():
                content = best_skill_path.read_text(encoding="utf-8")
                final_skill_path.write_text(content, encoding="utf-8")

            log(f"  [{context_id[:12]}...] Best: iteration {best_iter} "
                f"(score={result['best_score']:.4f}) → SKILL.md")

    # Save selection summary
    summary_path = Path(skills_base_dir) / "skill_selection_summary.jsonl"
    for result in selection_results:
        append_jsonl(result, summary_path)

    log(f"Selection summary saved to {summary_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Adversarial co-evolution loop for CL-bench"
    )
    parser.add_argument("--challenger-model", type=str, default="gpt-4.1")
    parser.add_argument("--reasoner-model", type=str, default="gpt-4.1")
    parser.add_argument("--judge-model", type=str, default="gpt-4.1")
    parser.add_argument("--proposer-model", type=str, default="gpt-4.1")
    parser.add_argument("--generator-model", type=str, default="gpt-4.1")
    parser.add_argument("--input", type=str, default="CL-bench-context-dedup.jsonl")
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--base-url", type=str, default=None,
                        help="API Base URL. Supports OpenAI, Azure (auto-detected), and custom APIs. "
                        "Azure format: https://xxx.cognitiveservices.azure.com/2024-12-01-preview")
    parser.add_argument("--api-key", type=str, default=None)
    parser.add_argument("--max-samples", type=int, default=None)
    parser.add_argument("--num-iterations", type=int, default=5)
    parser.add_argument("--num-tasks", type=int, default=5,
                        help="Number of tasks the Challenger generates per round")
    parser.add_argument("--skills-dir", type=str, default="skills")
    parser.add_argument("--workers", type=int, default=1,
                        help="Number of concurrent workers (parallel contexts)")
    parser.add_argument("--skip-skill-selection", action="store_true",
                        help="Skip automatic skill selection; use last iteration as best skill")
    args = parser.parse_args()

    if args.output is None:
        args.output = "outputs/adversarial_loop.jsonl"

    log("=" * 60)
    log("Adversarial Co-Evolution Loop")
    log("=" * 60)
    log(f"Challenger model: {args.challenger_model}")
    log(f"Reasoner model:   {args.reasoner_model}")
    log(f"Judge model:      {args.judge_model}")
    log(f"Proposer model:   {args.proposer_model}")
    log(f"Generator model:  {args.generator_model}")
    log(f"Input: {args.input}")
    log(f"Output: {args.output}")
    log(f"Iterations per context: {args.num_iterations}")
    log(f"Tasks per round: {args.num_tasks}")
    log(f"Skills dir: {args.skills_dir}")
    log(f"Workers: {args.workers}")
    log(f"Skill selection: {'DISABLED (using last iteration)' if args.skip_skill_selection else 'ENABLED (automatic selection)'}")
    log("=" * 60)

    api_key = args.api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        log("Error: Please set OPENAI_API_KEY or use --api-key")
        return

    # Create unified client (auto-detects Azure vs OpenAI)
    base_url = args.base_url or os.getenv("OPENAI_BASE_URL")
    client = create_client(api_key, base_url)

    data = load_jsonl(args.input)
    log(f"Loaded {len(data)} contexts")

    if args.max_samples:
        data = data[: args.max_samples]
        log(f"Limited to {args.max_samples} contexts")

    # Resume: track progress per context
    ctx_progress = {}
    if os.path.exists(args.output):
        existing = load_jsonl(args.output)
        for record in existing:
            cid = record["context_id"]
            iter_num = record["iteration"]
            ctx_progress[cid] = max(ctx_progress.get(cid, 0), iter_num)

        completed_contexts = {
            cid for cid, iter_num in ctx_progress.items()
            if iter_num >= args.num_iterations
        }
        partial_contexts = {
            cid: iter_num for cid, iter_num in ctx_progress.items()
            if iter_num < args.num_iterations
        }

        if completed_contexts:
            log(f"Resuming: {len(completed_contexts)} contexts fully completed")
        if partial_contexts:
            log(f"Resuming: {len(partial_contexts)} contexts partially completed")

    # Skip only fully completed contexts
    pending = [
        item for item in data
        if item.get("metadata", {}).get("context_id", "") not in ctx_progress
        or ctx_progress[item.get("metadata", {}).get("context_id", "")] < args.num_iterations
    ]

    if not pending:
        log("All contexts already processed")
        return

    log(f"Processing {len(pending)} contexts...")

    def _process_context(item):
        """Worker function for a single context."""
        context_id = item.get("metadata", {}).get("context_id", "unknown")
        try:
            # Determine starting iteration for this context
            start_iter = ctx_progress.get(context_id, 0) + 1
            if start_iter > 1:
                log(f"  [{context_id[:12]}...] Resuming from iteration {start_iter}")

            rounds = run_adversarial_rounds(
                context_item=item,
                client=client,
                challenger_model=args.challenger_model,
                reasoner_model=args.reasoner_model,
                judge_model=args.judge_model,
                proposer_model=args.proposer_model,
                generator_model=args.generator_model,
                num_iterations=args.num_iterations,
                num_tasks=args.num_tasks,
                skills_base_dir=args.skills_dir,
                output_path=args.output,
                start_iteration=start_iter,
                skip_skill_selection=args.skip_skill_selection,
            )
            return context_id, len(rounds), None
        except Exception as e:
            return context_id, 0, str(e)

    success_count = 0
    fail_count = 0

    if args.workers == 1:
        for i, item in enumerate(pending):
            context_id = item.get("metadata", {}).get("context_id", f"idx-{i}")
            log(f"Context {i + 1}/{len(pending)}: {context_id}")
            cid, num_rounds, error = _process_context(item)
            if error:
                log(f"  Context {cid} failed: {error}")
                fail_count += 1
            else:
                success_count += 1
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(_process_context, item): item
                for item in pending
            }
            with tqdm(total=len(pending), desc="Contexts") as pbar:
                for future in as_completed(futures):
                    try:
                        cid, num_rounds, error = future.result()
                        if error:
                            log(f"  Context {cid} failed: {error}")
                            fail_count += 1
                        else:
                            success_count += 1
                    except Exception as e:
                        log(f"  Context exception: {e}")
                        fail_count += 1
                    pbar.update(1)

    log("=" * 60)
    log("Adversarial loop completed!")
    log(f"   Success: {success_count}")
    log(f"   Failed: {fail_count}")
    log(f"Output: {args.output}")
    log(f"Skills: {args.skills_dir}/")
    log("=" * 60)
    if args.skip_skill_selection:
        log("Note: Skill selection was SKIPPED. Last iteration used as best skill for each context.")
    else:
        log("Note: Best skill selection was performed immediately after each context completed.")
        log(f"Selection summary saved to: {args.skills_dir}/skill_selection_summary.jsonl")


if __name__ == "__main__":
    main()
