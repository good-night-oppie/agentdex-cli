#!/bin/bash


# api key
export OPENAI_BASE_URL=""
export OPENAI_API_KEY=""


INPUT="./CL-bench-context-dedup.jsonl"

python selfplay_loop.py \
    --challenger-model gpt-4.1 \
    --reasoner-model gpt-4.1 \
    --judge-model gpt-5.1 \
    --proposer-model gpt-4.1 \
    --generator-model gpt-4.1 \
    --input "$INPUT" \
    --output outputs/loop_data/loop_gpt-4.1-judge5-1.jsonl \
    --num-iterations 5 \
    --num-tasks 5 \
    --skills-dir skills-from-4.1-judge5-1 \
    --workers 32


INPUT="./CL-bench-with-task-delimiter.jsonl"

python infer.py \
    --model gpt-4.1 \
    --input "$INPUT" \
    --workers 32 \
    --skills-dir skills-from-4.1-judge5-1/reasoner \
    --output outputs/gpt-4.1-skills-from-4.1-judge5-1.jsonl

python eval_ignore_none.py \
    --input outputs/gpt-4.1-skills-from-4.1-judge5-1.jsonl \
    --judge-model gpt-5.1 \
    --workers 32
