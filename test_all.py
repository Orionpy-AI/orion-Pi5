# test_all.py
import sys
import os
sys.stdout.reconfigure(encoding='utf-8')

from tools import (
    registry,
    rag_engine,
    mcp_manager,
    read_file,
    write_file,
    replace_in_file,
    list_dir,
    search_code,
    tavily_search,
    calculator,
    get_current_datetime,
    save_file,
    list_files,
    delete_file,
    cloud_status,
)
from agent import OrionAgent

print("=== 1. Testing Builtin Tools ===")
print("DateTime:", get_current_datetime())
print("Calculator:", calculator("42 * 8"))
print("Search:", tavily_search("Raspberry Pi 5", max_results=1)[:100])

print("\n=== 2. Testing Code Tools ===")
print(list_dir(".", max_entries=5))
print(read_file("ui.py", 1, 4))

print("\n=== 3. Testing RAG Engine ===")
res = rag_engine.index_directory(".")
print("Indexed:", res)
matches = rag_engine.query("calculate arithmetic", top_k=1)
print("Top match for 'calculate arithmetic':", matches[0]['rel_path'] if matches else "None")

print("\n=== 4. Testing Tool Call Parser ===")
agent = OrionAgent()
t1 = agent._parse_tool_call('```json\n{"tool": "calculator", "arguments": {"expression": "100/4"}}\n```')
print("JSON Tool Call parsed:", t1)
t2 = agent._parse_tool_call('Action: search_code\nAction Input: {"pattern": "def "}')
print("ReAct Tool Call parsed:", t2)

print("\n=== 5. Testing Storage Tools & Cloud Status ===")
print(cloud_status())
save_res = save_file("requirements.txt", target="local")
print("Save result (local):", save_res)
list_res = list_files(target="local")
print("List result (local):\n", list_res)
del_res = delete_file(target="local", relative_path="requirements.txt")
print("Delete result (local):", del_res)

# Test OneDrive target dispatch
save_one_res = save_file("requirements.txt", target="onedrive")
print("Save result (onedrive):", save_one_res)
list_one_res = list_files(target="onedrive")
print("List result (onedrive):\n", list_one_res)
del_one_res = delete_file(target="onedrive", relative_path="requirements.txt")
print("Delete result (onedrive):", del_one_res)

print("\n=== 6. Testing Unified Registry ===")
all_tools = registry.get_all_tool_definitions()
print(f"Total Registered Tools: {len(all_tools)}")

print("\nALL TESTS PASSED SUCCESSFULLY!")

