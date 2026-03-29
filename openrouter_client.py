#!/usr/bin/env python3
"""
openrouter_client.py - OpenRouter API integration for LLM completions

Used for generating talent mise-en-scene, analyzing harness performance,
and other AI-powered features.
"""

import os
import json
from typing import Optional, Dict, Any, List
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://openrouter.ai/api/v1"


def get_api_key() -> str:
    """Get OpenRouter API key from environment."""
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise ValueError("OPENROUTER_API_KEY not found in .env or environment")
    return key


def generate_completion(
    prompt: str,
    model: str = "anthropic/claude-3.5-sonnet",
    max_tokens: int = 500,
    temperature: float = 0.7,
    response_format: Optional[Dict] = None
) -> str:
    """
    Generate a completion using OpenRouter.
    
    Args:
        prompt: The prompt text
        model: Model to use (default: Claude 3.5 Sonnet)
        max_tokens: Maximum tokens to generate
        temperature: Sampling temperature
        response_format: Optional JSON schema for structured output
    
    Returns:
        Generated text
    """
    headers = {
        "Authorization": f"Bearer {get_api_key()}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/tycho",  # Required by OpenRouter
        "X-Title": "Tycho Video Generator"
    }
    
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature
    }
    
    if response_format:
        payload["response_format"] = response_format
    
    response = requests.post(
        f"{BASE_URL}/chat/completions",
        headers=headers,
        json=payload,
        timeout=60
    )
    response.raise_for_status()
    
    data = response.json()
    return data['choices'][0]['message']['content']


def generate_talent_mise_en_scene(celebrity_name: str) -> Dict[str, Any]:
    """
    Generate mise-en-scene for a celebrity using LLM.
    
    Returns a dict with:
    - adjectives: List of top 5 adjectives
    - emotional_saliences: Dict of emotional attributes
    - bumper_style: Recommended bumper style
    - user_editable: Flag indicating this was auto-generated
    
    Args:
        celebrity_name: Name of the celebrity (e.g., "Jude Law")
    
    Returns:
        Dict with mise-en-scene data
    """
    prompt = f"""give me the top 5 adjectives and emotional saliences for the following celebrity: {celebrity_name}. This is not conversational and will be used for prompt engineering.

Provide the response in this exact JSON format:
{{
    "adjectives": ["adj1", "adj2", "adj3", "adj4", "adj5"],
    "emotional_saliences": {{
        "primary_tone": "e.g., brooding, whimsical, intense",
        "energy_level": "high/medium/low",
        "emotional_temperature": "warm/cool/neutral",
        "comedic_vs_dramatic": "comedic/balanced/dramatic",
        "vintage_vs_modern": "vintage/balanced/modern"
    }},
    "bumper_style": "brief description of recommended bumper style"
}}"""
    
    try:
        response = generate_completion(
            prompt=prompt,
            model="anthropic/claude-3.5-sonnet",
            max_tokens=400,
            temperature=0.7
        )
        
        # Parse JSON from response
        # Sometimes the model wraps in markdown code blocks
        content = response.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        
        data = json.loads(content.strip())
        data['user_editable'] = True
        data['auto_generated'] = True
        data['celebrity_name'] = celebrity_name
        
        return data
        
    except Exception as e:
        print(f"[OpenRouter] Error generating mise-en-scene: {e}")
        # Return fallback data
        return {
            "adjectives": ["charismatic", "versatile", "compelling", "professional", "memorable"],
            "emotional_saliences": {
                "primary_tone": "balanced",
                "energy_level": "medium",
                "emotional_temperature": "neutral",
                "comedic_vs_dramatic": "balanced",
                "vintage_vs_modern": "balanced"
            },
            "bumper_style": "classic professional documentary style",
            "user_editable": True,
            "auto_generated": False,
            "celebrity_name": celebrity_name,
            "error": str(e)
        }


def update_talent_mise_en_scene(
    talent_id: int,
    mise_en_scene: Dict[str, Any]
) -> bool:
    """
    Update the mise_en_scene for a talent in the database.
    
    Args:
        talent_id: Database ID of the talent
        mise_en_scene: Dict with mise-en-scene data
    
    Returns:
        True if successful
    """
    from database import get_db
    
    db = get_db()
    
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE talent 
            SET mise_en_scene = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (json.dumps(mise_en_scene), talent_id))
        conn.commit()
        return cursor.rowcount > 0


def get_or_generate_mise_en_scene(
    talent_id: int,
    celebrity_name: str,
    force_regenerate: bool = False
) -> Dict[str, Any]:
    """
    Get existing mise_en_scene or generate new one.
    
    Args:
        talent_id: Database ID of the talent
        celebrity_name: Name for generation
        force_regenerate: Whether to regenerate even if exists
    
    Returns:
        Mise-en-scene dict
    """
    from database import get_db
    
    db = get_db()
    talent = db.get_talent_by_id(talent_id)
    
    if talent and talent.mise_en_scene and not force_regenerate:
        try:
            return json.loads(talent.mise_en_scene)
        except json.JSONDecodeError:
            pass
    
    # Generate new
    print(f"[OpenRouter] Generating mise-en-scene for {celebrity_name}...")
    mise_en_scene = generate_talent_mise_en_scene(celebrity_name)
    
    # Save to database
    update_talent_mise_en_scene(talent_id, mise_en_scene)
    
    return mise_en_scene


def format_mise_en_scene_for_prompt(mise_en_scene: Dict[str, Any]) -> str:
    """
    Format mise_en_scene data for use in video generation prompts.
    
    Args:
        mise_en_scene: The mise-en-scene dict
    
    Returns:
        Formatted string for prompts
    """
    if not mise_en_scene:
        return ""
    
    parts = []
    
    # Add adjectives
    adjectives = mise_en_scene.get('adjectives', [])
    if adjectives:
        parts.append(f"Style: {', '.join(adjectives)}")
    
    # Add emotional saliences
    emotional = mise_en_scene.get('emotional_saliences', {})
    if emotional:
        if emotional.get('primary_tone'):
            parts.append(f"Tone: {emotional['primary_tone']}")
        if emotional.get('energy_level'):
            parts.append(f"Energy: {emotional['energy_level']}")
        if emotional.get('comedic_vs_dramatic'):
            parts.append(f"Balance: {emotional['comedic_vs_dramatic']}")
    
    # Add bumper style if available
    bumper = mise_en_scene.get('bumper_style', '')
    if bumper:
        parts.append(f"Bumper: {bumper}")
    
    return "; ".join(parts)


if __name__ == "__main__":
    # Test the client
    print("Testing OpenRouter client...")
    
    # Test mise-en-scene generation
    result = generate_talent_mise_en_scene("Jude Law")
    print(f"\nGenerated mise-en-scene for Jude Law:")
    print(json.dumps(result, indent=2))
    
    # Test formatting
    formatted = format_mise_en_scene_for_prompt(result)
    print(f"\nFormatted for prompt:")
    print(formatted)
