echo "Testing non-streaming request with function calling..."
curl -s http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ollama" \
  -d '{
    "model":"Qwen3-4B-Instruct-2507:Q8_0",
    "messages":[{"role":"user","content":"hi"}],
    "tools":[{"type":"function","function":{"name":"t","description":"d","parameters":{"type":"object","properties":{}}}}],
    "stream": false
  }'
echo ""
echo "Testing streaming request with function calling..."
curl -s http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ollama" \
  -d '{
    "model":"Qwen3-4B-Instruct-2507:Q8_0",
    "messages":[{"role":"user","content":"hi"}],
    "tools":[{"type":"function","function":{"name":"t","description":"d","parameters":{"type":"object","properties":{}}}}],
    "stream": true
  }'