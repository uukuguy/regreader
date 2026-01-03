#!/usr/bin/env bash

export OPENAI_MODEL_NAME=openai/${OPENAI_MODEL_NAME}

echo "OPENAI_BASE_URL: $OPENAI_BASE_URL"
# echo first 15 and last 6 chars of OPENAI_API_KEY
echo "OPENAI_API_KEY: ${OPENAI_API_KEY:0:15}********${OPENAI_API_KEY: -6}"
echo "OPENAI_MODEL_NAME: $OPENAI_MODEL_NAME"
