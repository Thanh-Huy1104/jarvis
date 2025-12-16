"""Code extraction and parsing utilities"""

import json
import re
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.adapters.llm_vllm import VllmAdapter

logger = logging.getLogger(__name__)


def extract_code(text: str, llm: 'VllmAdapter') -> str:
    """Extract Python code from markdown code blocks"""
    if not text:
        return ""
    
    # Remove any thinking tags first
    text = llm.sanitize_thought_process(text)
    
    # Try standard python code block with newlines
    pattern = r'```python\s*\n(.*?)\n```'
    matches = re.findall(pattern, text, re.DOTALL)
    if matches:
        return max(matches, key=len).strip()
    
    # Try without language specifier but with newlines
    pattern = r'```\s*\n(.*?)\n```'
    matches = re.findall(pattern, text, re.DOTALL)
    if matches:
        # Filter for Python-like code
        for match in sorted(matches, key=len, reverse=True):
            if any(kw in match for kw in ['import', 'def', 'print', 'for', 'if', '=']):
                return match.strip()
    
    # Try inline code blocks (no newlines)
    pattern = r'```python(.*?)```'
    matches = re.findall(pattern, text, re.DOTALL)
    if matches:
        return max(matches, key=len).strip()
    
    # Try generic code block (no language, no newlines)
    pattern = r'```(.*?)```'
    matches = re.findall(pattern, text, re.DOTALL)
    if matches:
        for match in sorted(matches, key=len, reverse=True):
            if any(kw in match for kw in ['import', 'def', 'print', 'for', 'if', '=']):
                return match.strip()
    
    logger.warning("No code block found in response")
    logger.debug(f"Raw text: {text[:300]}...")
    return ""


def generate_skill_name(description: str) -> str:
    """Generate a skill name from task description"""
    # Simple slug generation
    slug = re.sub(r'[^a-z0-9]+', '_', description.lower())[:50]
    return slug.strip('_')


def extract_json(text: str, llm: 'VllmAdapter') -> dict:
    """Extract JSON object from text (handles markdown code blocks)"""
    if not text:
        return {}
    
    # Remove thinking tags
    text = llm.sanitize_thought_process(text)
    
    # Try to find JSON in code blocks first
    json_pattern = r'```(?:json)?\s*\n?(\{.*?\})\s*\n?```'
    matches = re.findall(json_pattern, text, re.DOTALL)
    if matches:
        try:
            return json.loads(matches[0])
        except json.JSONDecodeError:
            pass
    
    # Try to find raw JSON object
    json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
    matches = re.findall(json_pattern, text, re.DOTALL)
    for match in matches:
        try:
            return json.loads(match)
        except json.JSONDecodeError:
            continue
    
    logger.warning("No valid JSON found in text")
    return {}
