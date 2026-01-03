export OPENAI_BASE_URL=https://api.siliconflow.cn/v1
export OPENAI_API_KEY=sk-ictpwlunwjhfapgfpwevvkaiiorpzvspkxtpyfjtwmpetjaw

# 南阳站故障 29.4 s
# export OPENAI_MODEL_NAME=Qwen/Qwen3-Coder-480B-A35B-Instruct

# 
# export OPENAI_MODEL_NAME="Qwen/Qwen3-235B-A22B-Instruct-2507"

# 18.3s
# export OPENAI_MODEL_NAME=Qwen/Qwen3-Coder-30B-A3B-Instruct

export OPENAI_MODEL_NAME=Qwen/Qwen3-30B-A3B-Instruct-2507

# 南阳站故障 21.3 s
# export OPENAI_MODEL_NAME=Pro/deepseek-ai/DeepSeek-V3.2
# export OPENAI_MODEL_NAME=deepseek-ai/DeepSeek-V3.2

# 南阳站故障 80.4 s 更详细，含系统构成、功能描述
# export OPENAI_MODEL_NAME=Pro/moonshotai/Kimi-K2-Instruct-0905
# export OPENAI_MODEL_NAME=Pro/moonshotai/Kimi-K2-Thinking

# 南阳站故障 15.3 s
# export OPENAI_MODEL_NAME=Pro/zai-org/GLM-4.7

export OPENAI_MODEL_NAME=openai/${OPENAI_MODEL_NAME}

echo "OPENAI_BASE_URL: $OPENAI_BASE_URL"
# echo first 15 and last 6 chars of OPENAI_API_KEY
echo "OPENAI_API_KEY: ${OPENAI_API_KEY:0:15}********${OPENAI_API_KEY: -6}"
echo "OPENAI_MODEL_NAME: $OPENAI_MODEL_NAME"
