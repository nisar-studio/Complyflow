"""
ComplyFlow — ADK PoC (Proof of Concept)

Minimal test to validate:
  1. google-adk 2.8.0 is importable
  2. ADK Agent connects to Gemini via GEMINI_API_KEY + GEMINI_MODEL env vars
  3. A tool is registered and invoked autonomously by the agent
  4. Structured result is returned

Run with:
    python poc_adk.py

Set env vars first:
    $env:GEMINI_API_KEY = "your-key"
    $env:GEMINI_MODEL = "gemini-2.5-flash"   # or whichever model you are using
"""
from __future__ import annotations

import json
import os
import asyncio
import sys

# ── 1. Validate environment ──────────────────────────────────────
api_key = os.environ.get("GEMINI_API_KEY", "")
model_name = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")

if not api_key:
    print("ERROR: GEMINI_API_KEY environment variable is not set.")
    print("Set it with:  $env:GEMINI_API_KEY = 'your-key-here'")
    sys.exit(1)

print(f"✓ GEMINI_API_KEY present (length={len(api_key)})")
print(f"✓ GEMINI_MODEL = {model_name}")

# ── 2. Import ADK ────────────────────────────────────────────────
try:
    import google.adk as adk
    from google.adk.agents import LlmAgent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types as genai_types
    print(f"✓ google-adk version: {adk.__version__}")
except ImportError as e:
    print(f"ERROR importing google-adk: {e}")
    print("Run: pip install google-adk==2.8.0")
    sys.exit(1)

# ── 3. Define a minimal proof-of-concept tool ───────────────────
def poc_extract_sample_requirement(document_text: str) -> dict:
    """
    Proof-of-concept tool: extracts a single sample requirement from text.
    Returns a structured dict with requirement_id, title, and description.

    Args:
        document_text: Raw text content of a requirements document snippet.

    Returns:
        A dict containing the first extracted requirement.
    """
    # This is intentionally simple — just returns a hardcoded extract
    # to prove the ADK tool invocation round-trip works.
    return {
        "requirement_id": "REQ-POC-001",
        "title": "Business Registration",
        "description": "Vendor must provide a valid business registration certificate.",
        "required_evidence": "Business registration certificate issued by competent authority",
        "priority": "HIGH",
        "source_reference": "Section 1.1 of requirements document",
        "input_length": len(document_text),
    }

# ── 4. Build ADK Agent ───────────────────────────────────────────
agent = LlmAgent(
    name="complyflow_poc_agent",
    model=model_name,
    description="ComplyFlow proof-of-concept agent for ADK/Gemini validation.",
    instruction=(
        "You are a compliance analyst. When given a requirements document snippet, "
        "call the poc_extract_sample_requirement tool to extract the first requirement. "
        "Then summarize what you found in one sentence."
    ),
    tools=[poc_extract_sample_requirement],
)

print(f"✓ ADK Agent created: {agent.name}")
print(f"✓ Tools registered: {[t.__name__ if callable(t) else str(t) for t in agent.tools]}")

# ── 5. Run the agent ─────────────────────────────────────────────
SAMPLE_REQUIREMENTS_TEXT = """
NovaTech Vendor Certification Requirements

1.1 Business Registration
Vendors must submit a current business registration certificate issued by the
relevant government authority. The certificate must be valid at the time of submission.

1.2 Insurance Certificate
Vendors must provide a current general liability insurance certificate with a
minimum coverage of USD 2,000,000. The certificate must name NovaTech as an
additional insured party.
"""

USER_MESSAGE = (
    f"Please analyze this requirements document snippet and extract the first requirement:\n\n"
    f"{SAMPLE_REQUIREMENTS_TEXT}"
)

APP_NAME = "complyflow_poc"
SESSION_ID = "poc_session_001"
USER_ID = "poc_user"

async def run_poc():
    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=SESSION_ID,
    )

    runner = Runner(
        agent=agent,
        app_name=APP_NAME,
        session_service=session_service,
    )

    user_content = genai_types.Content(
        role="user",
        parts=[genai_types.Part(text=USER_MESSAGE)],
    )

    print("\n" + "─" * 60)
    print("Running ADK Agent...")
    print("─" * 60)

    tool_called = False
    final_text = ""

    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=SESSION_ID,
        new_message=user_content,
    ):
        # Print all events for visibility
        if hasattr(event, "content") and event.content:
            for part in event.content.parts:
                if hasattr(part, "function_call") and part.function_call:
                    fc = part.function_call
                    print(f"\n✓ TOOL CALLED: {fc.name}")
                    print(f"  Args: {json.dumps(dict(fc.args), indent=2)[:300]}")
                    tool_called = True
                elif hasattr(part, "function_response") and part.function_response:
                    fr = part.function_response
                    print(f"\n✓ TOOL RESULT: {fr.name}")
                    print(f"  Response: {json.dumps(dict(fr.response), indent=2)[:300]}")
                elif hasattr(part, "text") and part.text:
                    final_text = part.text

        if hasattr(event, "is_final_response") and event.is_final_response():
            break

    print("\n" + "─" * 60)
    print("Agent Final Response:")
    print(final_text)
    print("─" * 60)

    if tool_called:
        print("\n✅ ADK PoC PASSED: Agent successfully called a tool via Gemini.")
    else:
        print("\n⚠️  WARNING: Agent did not call the tool. Check model and instructions.")

    return tool_called

if __name__ == "__main__":
    result = asyncio.run(run_poc())
    sys.exit(0 if result else 1)
