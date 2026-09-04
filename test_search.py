# test_search.py
import sys
import os
sys.stdout.reconfigure(encoding='utf-8')

from tools import tavily_search

query = "What is the latest Raspberry Pi model in 2026?"
print(f"Executing Live Tavily API Query: '{query}'\n")
result = tavily_search(query, max_results=2)
print("=== LIVE RESPONSE FROM TAVILY API ===")
print(result)
