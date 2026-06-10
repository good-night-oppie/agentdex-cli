"""Evaluation Script - Using Azure OpenAI API for Grading (Skip Failed Samples)

Same as eval.py but skips samples that fail grading (API errors, JSON parse errors,
empty model output) instead of writing them as score=0. Failed samples are not written
to the output file, so re-running will automatically retry them.

Input File:
    JSONL file with model outputs, each line contains:
    {"idx": 0, "messages": [...], "model_output": "...", "rubrics": [...]}

Output File:
    outputs/{model_name}_graded.jsonl

Usage:
    python eval_ignore_none.py --input outputs/model_output.jsonl --judge-model gpt-5.1
    python eval_ignore_none.py --input outputs/model_output.jsonl --workers 5
"""

import json
import os
import argparse
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

from api_client import create_client


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


def build_rubrics_text(rubrics):
    if not rubrics:
        return "No specific rubrics provided."

    lines = []
    for i, rubric in enumerate(rubrics, 1):
        if isinstance(rubric, dict):
            criteria = rubric.get("rubric_criteria", "").strip()
        else:
            criteria = str(rubric).strip()
        if criteria:
            lines.append(f"{i}. {criteria}")

    return "\n".join(lines) if lines else "No specific rubrics provided."


def call_judge_api(client, model, rubrics_text, model_output, max_retries=3, retry_delay=3):
    grading_prompt = (
        "Starting now, you are a rigorous instruction-following grading teacher. Your task is to accurately grade and score student answers based on the 【Rubrics】.\n\n"
        "Grading Criteria\n"
        "This is a strict, all-or-nothing grading system. The final score is binary.\n"
        "To receive a score of 1, the student's answer must perfectly satisfy every single requirement listed in the 【Rubrics】.\n"
        "If even one requirement is not fully met, the final score will be 0.\n"
        "Grading Process\n"
        "Please strictly follow the steps below for analysis—no steps may be skipped:\n"
        "Step 1: Analyze the Standard Answer\n"
        "List all explicit requirements in the 【Rubrics】 item by item (including format, content, quantity, order, etc.).\n"
        "Identify implicit requirements in the 【Rubrics】 (e.g., language style, logical structure).\n"
        "Define specific evaluation criteria for each requirement (e.g., \"must include X,\" \"must not exceed Y\").\n"
        "Step 2: Check Each Requirement Against the Student's Answer\n"
        "For every requirement in the 【Rubrics】, verify one by one whether the student's answer fully satisfies it.\n"
        "Step 3: Self-Reflection\n"
        "Before giving the final score, you must conduct the following checks:\n"
        "  Completeness Check: Whether all requirements in the standard answer have been reviewed with no omissions.\n"
        "  Strictness Check: Whether the evaluation strictly adheres to the \"fully satisfied\" standard without relaxing requirements due to subjective judgment.\n"
        "  Consistency Check: Whether the grading rationale aligns logically with the final score.\n"
        "  Objectivity Check: Whether judgments are based on objective facts rather than subjective speculation.\n"
        "Output Format Requirements\n"
        "【Grading Rationale】: xxx\n"
        "【List of Requirement Satisfaction Status】: [x₁, x₂, …, xᵢ, …, xₙ] (where n is the total number of requirements in the 【Rubrics】, and xᵢ indicates whether the student's answer meets the i-th requirement, with values \"yes\"/\"no\")\n"
        "【Overall Score】: x points (x is an integer, either 0 or 1.)\n\n"
        "Content to Be Graded\n"
        f"【Rubrics】:\n{rubrics_text}\n"
        f"【Student Response】:\n{model_output}\n"
        "\nPlease strictly output ONLY the following JSON format (do not output any other content):\n"
        "{\n"
        '  "Grading Rationale": "Your detailed grading rationale",\n'
        '  "List of Requirement Satisfaction Status": ["yes", "no", ...],\n'
        '  "Overall Score": 0 or 1\n'
        "}\n"
    )

    messages = [{"role": "user", "content": grading_prompt}]

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
            )
            result_text = response.choices[0].message.content.strip()

            if result_text.startswith("```json"):
                result_text = result_text[7:]
            if result_text.startswith("```"):
                result_text = result_text[3:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
            result_text = result_text.strip()

            return result_text

        except Exception as e:
            error_msg = str(e)
            if attempt < max_retries - 1:
                log(f"   API call failed (attempt {attempt + 1}/{max_retries}): {error_msg[:100]}")
                time.sleep(retry_delay)
            else:
                log(f"   API call failed after {max_retries} attempts: {error_msg[:100]}")
                return None

    return None


def process_single_item(args):
    """Process a single item. Returns (idx, result, error).

    On any failure (empty output, API error, JSON parse error),
    returns (idx, None, error_msg) so the caller can skip it.
    """
    item, client, judge_model, max_retries = args
    idx = item.get("idx", -1)

    model_output = item.get("model_output", "")
    rubrics = item.get("rubrics", [])

    if not model_output or not model_output.strip():
        log(f"   [idx={idx}] Skipped: empty model output")
        return idx, None, "Empty model output"

    rubrics_text = build_rubrics_text(rubrics)

    for parse_attempt in range(max_retries):
        grading_result = call_judge_api(
            client, judge_model, rubrics_text, model_output, max_retries
        )

        if not grading_result:
            log(f"   [idx={idx}] API call failed (attempt {parse_attempt + 1}/{max_retries})")
            if parse_attempt < max_retries - 1:
                time.sleep(2)
                continue
            else:
                return idx, None, "API call failed"

        try:
            result_json = json.loads(grading_result)

            if "Overall Score" not in result_json:
                raise ValueError("Missing 'Overall Score' field")

            result = {
                **item,
                "grading_rationale": result_json.get("Grading Rationale", ""),
                "requirement_status": result_json.get("List of Requirement Satisfaction Status", []),
                "score": result_json.get("Overall Score", "")
            }
            return idx, result, None

        except (json.JSONDecodeError, ValueError) as e:
            log(f"   [idx={idx}] JSON parse failed (attempt {parse_attempt + 1}/{max_retries}): {e}")
            if parse_attempt < max_retries - 1:
                time.sleep(2)
            else:
                return idx, None, f"JSON parse failed: {e}"

    return idx, None, "Unknown error"


def calculate_statistics(output_path, total_input):
    if not os.path.exists(output_path):
        return

    data = load_jsonl(output_path)

    graded = len(data)
    skipped = total_input - graded
    score_0 = sum(1 for item in data if item.get("score") == 0)
    score_1 = sum(1 for item in data if item.get("score") == 1)

    log(f"\nFinal Statistics:")
    log(f"   Total input samples: {total_input}")
    log(f"   Successfully graded: {graded}")
    log(f"   Skipped (failed): {skipped}")
    log(f"   Score 0: {score_0}")
    log(f"   Score 1: {score_1}")

    if graded > 0:
        solving_rate = score_1 / graded
        log(f"\nSolving Rate (graded only): {solving_rate:.4f} ({score_1}/{graded})")
    if total_input > 0:
        solving_rate_all = score_1 / total_input
        log(f"Solving Rate (all input):   {solving_rate_all:.4f} ({score_1}/{total_input})")

    log("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Evaluation Script - Skip Failed Samples (Auto-detect Azure/OpenAI)")
    parser.add_argument("--input", type=str, required=True, help="Input JSONL file path")
    parser.add_argument("--output", type=str, default=None, help="Output JSONL file path")
    parser.add_argument("--judge-model", type=str, default="gpt-5.1", help="Judge model name")
    parser.add_argument("--base-url", type=str, default=None,
                        help="API Base URL. Supports OpenAI, Azure (auto-detected), and custom APIs")
    parser.add_argument("--api-key", type=str, default=None, help="API Key (optional, defaults to env var)")
    parser.add_argument("--workers", type=int, default=1, help="Number of concurrent workers")
    parser.add_argument("--max-retries", type=int, default=3, help="Max retries per item")
    args = parser.parse_args()

    if args.output is None:
        base_name = os.path.splitext(os.path.basename(args.input))[0]
        args.output = f"outputs/{base_name}_graded.jsonl"

    log("=" * 60)
    log("Evaluation Task (skip failed samples)")
    log("=" * 60)
    log(f"Input file: {args.input}")
    log(f"Output file: {args.output}")
    log(f"Judge model: {args.judge_model}")
    log(f"Workers: {args.workers}")
    log("=" * 60)

    api_key = args.api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        log("Error: Please set OPENAI_API_KEY or use --api-key argument")
        return

    base_url = args.base_url or os.getenv("OPENAI_BASE_URL")
    client = create_client(api_key, base_url)

    log("Loading data...")
    data = load_jsonl(args.input)
    total_input = len(data)
    log(f"   Total {total_input} samples")

    completed_indices = set()
    if os.path.exists(args.output):
        existing_data = load_jsonl(args.output)
        completed_indices = {item.get("idx") for item in existing_data if item.get("idx") is not None}
        log(f"Found {len(completed_indices)} completed, resuming remaining")

    pending_items = [item for item in data if item.get("idx") not in completed_indices]

    if not pending_items:
        log("All samples already evaluated")
        calculate_statistics(args.output, total_input)
        return

    log(f"Starting evaluation ({len(pending_items)} pending)...")

    tasks = [(item, client, args.judge_model, args.max_retries) for item in pending_items]

    success_count = 0
    skip_count = 0

    if args.workers == 1:
        for task in tqdm(tasks, desc="Evaluating"):
            idx, result, error = process_single_item(task)
            if result is not None:
                append_jsonl(result, args.output)
                success_count += 1
            else:
                log(f"   [idx={idx}] Skipped: {error}")
                skip_count += 1
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(process_single_item, task): task[0].get("idx") for task in tasks}

            with tqdm(total=len(tasks), desc="Evaluating") as pbar:
                for future in as_completed(futures):
                    try:
                        idx, result, error = future.result()
                        if result is not None:
                            append_jsonl(result, args.output)
                            success_count += 1
                        else:
                            log(f"   [idx={idx}] Skipped: {error}")
                            skip_count += 1
                    except Exception as e:
                        log(f"   Exception: {str(e)}")
                        skip_count += 1
                    pbar.update(1)

    log("=" * 60)
    log(f"Evaluation completed!")
    log(f"   Success: {success_count}")
    log(f"   Skipped: {skip_count}")
    log(f"   Output: {args.output}")

    calculate_statistics(args.output, total_input)


if __name__ == "__main__":
    main()
