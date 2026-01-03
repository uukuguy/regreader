curl -s http://localhost:11434/api/chat -H "Content-Type: application/json" -d '{
  "model": "Qwen3-Coder-30B-A3B-Instruct:Q4_K_M",
  "stream": false,
  "messages": [{"role":"user","content":"What is the temperature in Tokyo? Use the tool."}],
  "tools": [{
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
  }]
}'

# """
# curl -s http://localhost:11434/api/chat -H "Content-Type: application/json" -d '{
#   "model": "Qwen3-Coder-30B-A3B-Instruct:Q4_K_M",
#   "stream": false,
#   "messages": [
#     {"role":"user","content":"What is the temperature in Tokyo? Use the tool."},
#     {"role":"assistant","content":"","tool_calls":[{"id":"call_fx3qwivo","type":"function","function":{"name":"get_temperature","arguments":{"city":"Tokyo"}}}]},
#     {"role":"tool","content":"{\"city\":\"Tokyo\",\"temperature_c\":7,\"source\":\"demo\"}"}
#   ]
# }'

# curl -s http://localhost:11434/api/chat -H "Content-Type: application/json" -d '{
#   "model": "Qwen3-Coder-30B-A3B-Instruct:Q4_K_M",
#   "stream": false,
#   "messages": [
#     {"role":"user","content":"What is the temperature in Tokyo? Use the tool."},
#     {"role":"assistant","content":"","tool_calls":[{"id":"call_fx3qwivo","type":"function","function":{"name":"get_temperature","arguments":{"city":"Tokyo"}}}]},
#     {"role":"user","content":"<tool_response>{\"city\":\"Tokyo\",\"temperature_c\":7,\"source\":\"demo\"}</tool_response>"}
#   ]
# }'


# """