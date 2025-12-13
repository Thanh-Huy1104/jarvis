import asyncio
import os
import sys
import logging
from typing import List

# Add project root to path so we can import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.orchestrator import Orchestrator
from app.core.state import InMemorySessionStore

# Configure detailed logging to see the "Thinking"
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("StressTest")

async def run_scenario(name: str, prompt: str, orch: Orchestrator):
    print(f"\n\n{'='*20} SCENARIO: {name} {'='*20}")
    print(f"🤖 User: {prompt}")
    print("-" * 60)
    
    session_id = "test-session-001"
    
    # We ignore audio generation for this test to focus on logic
    audio_cache = {}
    full_response_accumulator = ""
    
    async for event in orch.stream_text_turn(
        session_id=session_id,
        user_text=prompt,
        audio_cache=audio_cache
    ):
        # OPTION 1: Streamed Tokens (if supported by graph)
        if event["type"] == "token":
            print(event["text"], end="", flush=True)
            full_response_accumulator += event["text"]
            
        # OPTION 2: Final Text (Standard ReAct/invoke mode)
        elif event["type"] == "done":
            final_text = event.get("assistant_text", "")
            if final_text and not full_response_accumulator:
                # If we didn't get tokens, print the full block
                print(final_text, end="", flush=True)
                full_response_accumulator = final_text
            print("\n[DONE]")
            
        elif event["type"] == "error":
            print(f"\n❌ ERROR: {event}")

    # --- DIAGNOSTIC CHECK ---
    # Check if the LLM tried to call a tool but the System failed to parse it.
    if "<tool_call>" in full_response_accumulator or "<tool_code>" in full_response_accumulator:
        print("\n\n⚠️  DIAGNOSTIC WARNING: Raw <tool_call> tags detected in text output!")
        print("    -> The LLM generated a tool call, but vLLM/Adapter treated it as plain text.")
        print("    -> Action: Check your vLLM --tool-call-parser setting or LLM Adapter logic.")
    
    # Check if response was suspiciously empty (e.g., tool error with no fallback)
    if not full_response_accumulator.strip():
         print("\n⚠️  WARNING: Response was empty. This usually means the Agent called a tool but failed to summarize the result.")

    print("\n" + "-" * 60)

async def main():
    print("🚀 Initializing Jarvis System for Stress Testing...")
    
    # 1. Initialize Stores
    session_store = InMemorySessionStore()
    
    # 2. Build Orchestrator (This connects to MCP and vLLM)
    try:
        orch = Orchestrator.make_default(session_store)
        await orch.start()
    except Exception as e:
        print(f"❌ Failed to start Orchestrator. Is vLLM running? Is 'uv' installed?\nError: {e}")
        return

    # --- SCENARIO 1: The "Parallel Fan-Out" Test ---
    # Goal: See if the Graph triggers multiple tool calls in ONE Step.
    # Expectation: You should see logs for executing multiple weather calls simultaneously.
    await run_scenario(
        "Parallel Tool Execution",
        "What is the weather currently in Tokyo, New York, and London?",
        orch
    )

    # --- SCENARIO 2: The "Sandbox & Correction" Test ---
    # Goal: See if the Agent can write code, fail, and fix it.
    # We ask it to do something that requires a library or specific syntax.
    await run_scenario(
        "Code Generation & Self-Correction",
        "Write a python script to calculate the 100th Fibonacci number. "
        "Make sure to print ONLY the final number. "
        "Use the 'math' library if possible, otherwise use a loop. "
        "Ensure any explanation text is properly commented out with #.",
        orch
    )

    # --- SCENARIO 3: The "Memory Injection" Test ---
    # Goal: Teach it a fact, then verify it persists in the session/vector store.
    await run_scenario(
        "Memory Storage",
        "My secret code is 'BLUE-OMEGA-99'. Remember this.",
        orch
    )
    
    await run_scenario(
        "Memory Retrieval",
        "What is my secret code? Please output it in reverse string format using Python.",
        orch
    )

    # --- SCENARIO 4: System Interaction & Chaining ---
    # Goal: Verify the agent can use shell commands and then use that data in another tool (add_note).
    await run_scenario(
        "System & File Ops",
        "Check the current system uptime using a shell command, and then save that uptime into my notes file.",
        orch
    )

    # --- SCENARIO 5: Data Analysis (Pure Python) ---
    # Goal: Stress test the sandbox with a heavier computation task.
    await run_scenario(
        "Data Analysis",
        "Generate a list of 50 random integers between 1 and 1000. "
        "Calculate the mean, median, and standard deviation. "
        "Print the results clearly.",
        orch
    )

    # --- SCENARIO 6: Conditional Logic ---
    # Goal: Test if the agent can interpret tool output and make a decision based on it.
    await run_scenario(
        "Conditional Logic",
        "Check the weather in Antarctica. "
        "If the temperature is below 0 degrees Celsius, tell me to 'Bring a parka'. "
        "If it is above 0, tell me 'Global warming is real'.",
        orch
    )

    # --- SCENARIO 7: Adversarial / Impossible Request ---
    # Goal: See how the agent handles requests for tools it doesn't have.
    await run_scenario(
        "Adversarial Request",
        "Teleport me to Mars immediately using your physics engine.",
        orch
    )
    
    # Cleanup
    await orch.stop()
    print("\n✅ Stress Test Complete.")

if __name__ == "__main__":
    if not os.getenv("VLLM_BASE_URL"):
        print("⚠️  WARNING: VLLM_BASE_URL not set. Defaulting to localhost:8000")
    
    asyncio.run(main())