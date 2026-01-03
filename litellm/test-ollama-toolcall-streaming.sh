#!/usr/bin/env bash
set -euo pipefail

BASE="http://localhost:11434/v1/chat/completions"
MODEL="Qwen3-4B-Instruct-2507:Q8_0"

TOOLS='[
  {
    "type":"function",
    "function":{
      "name":"get_temperature",
      "description":"Get the current temperature for a city",
      "parameters":{
        "type":"object",
        "required":["city"],
        "properties":{"city":{"type":"string"}}
      }
    }
  }
]'

echo "=== Non-streaming (should return tool_calls) ==="
curl -s "$BASE" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ollama" \
  -d "{
    \"model\":\"$MODEL\",
    \"stream\": false,
    \"messages\":[
      {\"role\":\"user\",\"content\":\"Call the get_temperature tool with city=Tokyo. Output only the tool call.\"}
    ],
    \"tools\": $TOOLS
  }" | sed 's/\\\\n/\n/g'

echo
echo "=== Streaming (check delta.tool_calls + index) ==="
curl -N "$BASE" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ollama" \
  -d "{
    \"model\":\"$MODEL\",
    \"stream\": true,
    \"messages\":[
      {\"role\":\"user\",\"content\":\"Call the get_temperature tool with city=Tokyo. Output only the tool call.\"}
    ],
    \"tools\": $TOOLS
  }"
echo
