#!/bin/bash

export OPENAI_API_PORT=11434
export OPENAI_BASE_URL=http://localhost:${OPENAI_API_PORT}/v1
export OPENAI_API_KEY=sk-unknown
# export OPENAI_MODEL_NAME=DeepSeek-R1-Distill-Qwen-7B:Q8_0
# export OPENAI_MODEL_NAME=Qwen2.5-7B-Instruct:Q8_0
# export OPENAI_MODEL_NAME=Qwen2.5-72B-Instruct:Q4_K_M
# export OPENAI_MODEL_NAME=Mistral-Small-24B-Instruct-2501:Q8_0
# export OPENAI_MODEL_NAME=QwQ-32B:Q4_K_M
# export OPENAI_MODEL_NAME=Qwen3-30B-A3B:Q8_0
# export OPENAI_MODEL_NAME=Qwen3-4B:Q8_0


export OPENAI_MODEL_NAME=Qwen3-Coder-30B-A3B-Instruct:Q4_K_M
# export OPENAI_MODEL_NAME=Qwen3-4B-Instruct-2507:Q8_0
# export OPENAI_MODEL_NAME=Qwen3-30B-A3B-Instruct-2507:Q4_K_M

# export OPENAI_MODEL_NAME=ollama_chat/${OPENAI_MODEL_NAME}
export OPENAI_MODEL_NAME=openai/${OPENAI_MODEL_NAME}

# for crewai

# export SERPER_API_KEY=86ab1680704dcc0df3e640e7514c5ff2b7302cc5

echo "OPENAI_BASE_URL: $OPENAI_BASE_URL"
# echo first 15 and last 6 chars of OPENAI_API_KEY
echo "OPENAI_API_KEY: ${OPENAI_API_KEY:0:15}********${OPENAI_API_KEY: -6}"
echo "OPENAI_MODEL_NAME: $OPENAI_MODEL_NAME"
