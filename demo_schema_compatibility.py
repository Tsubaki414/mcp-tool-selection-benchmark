#!/usr/bin/env python3
"""
Demo: Cross-Model Schema Compatibility Test
Shows that the same tool schema can work on Claude but fail on GPT-4o
"""

import os
from pathlib import Path

# Load API keys from .env
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                k, v = line.strip().split('=', 1)
                os.environ[k] = v

import anthropic
import openai

# ============================================================
# The problematic tool schema (common in real MCP servers)
# ============================================================
TOOL_SCHEMA = {
    "name": "zapper_balance",
    "description": "Check DeFi portfolio balance across networks",
    "parameters": {
        "address": {
            "type": "string",
            "description": "Wallet address to query"
        },
        "networks": {
            "type": "array",  # ⚠️ Missing "items" property!
            "description": "Networks to include (e.g., ethereum, polygon)"
        }
    }
}

def test_claude():
    """Test the schema on Claude"""
    client = anthropic.Anthropic()
    
    # Convert to Claude format
    claude_tool = {
        "name": TOOL_SCHEMA["name"],
        "description": TOOL_SCHEMA["description"],
        "input_schema": {
            "type": "object",
            "properties": TOOL_SCHEMA["parameters"],
            "required": ["address"]
        }
    }
    
    print("Testing Claude Sonnet 4.6...")
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=256,
            tools=[claude_tool],
            messages=[{"role": "user", "content": "Check wallet 0xABC123 balance on ethereum and polygon"}]
        )
        
        # Check response
        for block in response.content:
            if block.type == "tool_use":
                print(f"✅ SUCCESS: Claude invoked {block.name}")
                print(f"   Arguments: {block.input}")
                return True
            elif block.type == "text":
                print(f"✅ SUCCESS: Claude accepted schema")
                print(f"   Response: {block.text[:100]}...")
                return True
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def test_gpt4():
    """Test the same schema on GPT-4o"""
    client = openai.OpenAI()
    
    # Convert to OpenAI format
    openai_tool = {
        "type": "function",
        "function": {
            "name": TOOL_SCHEMA["name"],
            "description": TOOL_SCHEMA["description"],
            "parameters": {
                "type": "object",
                "properties": TOOL_SCHEMA["parameters"],
                "required": ["address"]
            }
        }
    }
    
    print("\nTesting GPT-4o...")
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Check wallet 0xABC123 balance on ethereum and polygon"}],
            tools=[openai_tool]
        )
        
        if response.choices[0].message.tool_calls:
            call = response.choices[0].message.tool_calls[0]
            print(f"✅ SUCCESS: GPT-4o invoked {call.function.name}")
            return True
        else:
            print(f"✅ SUCCESS: GPT-4o accepted schema")
            return True
    except openai.BadRequestError as e:
        print(f"❌ REJECTED: {e.message}")
        return False
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

if __name__ == "__main__":
    print("=" * 70)
    print("CROSS-MODEL SCHEMA COMPATIBILITY TEST")
    print("=" * 70)
    print(f"\nTool: {TOOL_SCHEMA['name']}")
    print(f"Issue: 'networks' parameter is type 'array' without 'items' defined")
    print("-" * 70)
    
    claude_ok = test_claude()
    gpt_ok = test_gpt4()
    
    print("\n" + "=" * 70)
    print("RESULT SUMMARY")
    print("=" * 70)
    print(f"Claude Sonnet 4.6: {'✅ PASS' if claude_ok else '❌ FAIL'}")
    print(f"GPT-4o:            {'✅ PASS' if gpt_ok else '❌ FAIL'}")
    
    if claude_ok and not gpt_ok:
        print("\n⚠️  FINDING: Same schema works on Claude but fails on GPT-4o!")
        print("   This is a cross-model compatibility issue that developers")
        print("   may not discover until users report failures.")
