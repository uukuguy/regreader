export OPENROUTER_BASE_URL="https://openrouter.ai/api/v1"
export OPENROUTER_API_KEY="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"

export OPENAI_BASE_URL=${OPENROUTER_BASE_URL}
export OPENAI_API_KEY=${OPENROUTER_API_KEY}


# export OPENAI_MODEL_NAME="openai/qwen/qwen3-30b-a3b-thinking-2507"
# 13.5s
# export OPENAI_MODEL_NAME="openai/qwen/qwen3-235b-a22b-2507"
# 16s
export OPENAI_MODEL_NAME="openai/qwen/qwen3-30b-a3b-instruct-2507"
# 17.5s
# export OPENAI_MODEL_NAME="openai/qwen/qwen3-coder-30b-a3b-instruct"
# 
# export OPENAI_MODEL_NAME="openai/qwen/qwen3-30b-a3b"
# 24.8s
# export OPENAI_MODEL_NAME="openai/qwen/qwen3-max"
# 14.7s
# export OPENAI_MODEL_NAME="openai/qwen/qwen3-coder"
# 29.0s
# export OPENAI_MODEL_NAME="openai/z-ai/glm-4.7"
# export GEMINI_MODEL_NAME="openai/google/gemini-2.5-flash"

# ---------- DeepSeek ----------
# export OPENAI_MODEL_NAME="deepseek/deepseek-chat-v3"
# export OPENAI_MODEL_NAME="deepseek/deepseek-r1"
# export OPENAI_MODEL_NAME="deepseek/deepseek-r1:free"

# ---------- Qwen ----------
# export OPENAI_MODEL_NAME="qwen/qwen-max"
# export OPENAI_MODEL_NAME="qwen/qwen-plus"
# export OPENAI_MODEL_NAME="qwen/qwen-2.5-coder-32b-instruct"


# # export OPENAI_MODEL_NAME="openrouter/optimus-alpha"
#
# export OPENAI_MODEL_NAME="qwen/qwq-32b"
# export OPENAI_MODEL_NAME="google/gemini-2.5-pro-exp-03-25:free"
#

echo "OPENAI_BASE_URL: $OPENAI_BASE_URL"
# echo first 15 and last 6 chars of OPENAI_API_KEY
echo "OPENAI_API_KEY: ${OPENAI_API_KEY:0:15}********${OPENAI_API_KEY: -6}"
echo "OPENAI_MODEL_NAME: $OPENAI_MODEL_NAME"
