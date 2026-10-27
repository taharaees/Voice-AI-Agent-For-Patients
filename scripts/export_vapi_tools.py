import json

from app.voice.vapi import vapi_tool_schemas

print(json.dumps(vapi_tool_schemas(), indent=2))
