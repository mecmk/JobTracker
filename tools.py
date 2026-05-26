"""
Tool implementations + JSON definitions for the main agent.

score_resume and suggest_bullet_improvements make nested Claude calls
with structured (Pydantic) output and prompt caching on the JD text.
"""

from __future__ import annotations

import json
from urllib.parse import urlparse

import anthropic
import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel

import database as db

client = anthropic.Anthropic()

# ── global resume context (set once before agent runs) ─────────────────────

_resume_text: str = ""


def set_resume(text: str) -> None:
    global _resume_text
    _resume_text = text


# ── Pydantic schemas for structured output ─────────────────────────────────


class ResumeScore(BaseModel):
    overall_score: int          # 0-100
    skill_match_score: int      # 0-100
    experience_score: int       # 0-100
    matched_skills: list[str]
    missing_skills: list[str]
    strengths: list[str]
    weaknesses: list[str]
    summary: str


class BulletEdit(BaseModel):
    section: str       # e.g. "Work Experience – Acme Corp"
    original: str
    improved: str
    reason: str
    priority: str      # "high" | "medium" | "low"


class BulletSuggestions(BaseModel):
    edits: list[BulletEdit]
    new_bullets_to_add: list[str]
    overall_tip: str


# ── Tool implementations ────────────────────────────────────────────────────


def scrape_job_posting(url: str) -> dict:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (JobTracker/1.0)"}
        r = httpx.get(url, headers=headers, follow_redirects=True, timeout=20)
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        # Try common JD containers first
        jd_text = ""
        for sel in [
            "[class*='job-description']", "[class*='description']",
            "[id*='job-description']", "article", "main", ".posting-content",
        ]:
            found = soup.select(sel)
            if found:
                candidate = "\n".join(e.get_text(separator="\n", strip=True) for e in found[:2])
                if len(candidate) > 400:
                    jd_text = candidate
                    break

        if len(jd_text) < 400:
            jd_text = soup.get_text(separator="\n", strip=True)

        # Deduplicate blank lines and cap at ~600 lines
        lines = [l.strip() for l in jd_text.split("\n") if l.strip()]
        jd_text = "\n".join(lines[:600])

        h1 = soup.find("h1")
        role = (h1.get_text(strip=True) if h1 else "").strip()[:120] or "Unknown Role"

        # Company: og:site_name > og:title fallback > domain
        company = ""
        for meta in soup.find_all("meta"):
            prop = meta.get("property", "") or meta.get("name", "")
            if prop in ("og:site_name",):
                company = meta.get("content", "")[:80]
                break
        if not company:
            for meta in soup.find_all("meta"):
                if meta.get("property") == "og:title":
                    parts = (meta.get("content") or "").split("|")
                    company = parts[-1].strip()[:80] if len(parts) > 1 else ""
                    break
        if not company:
            company = urlparse(url).netloc.replace("www.", "").split(".")[0].capitalize()

        return {"url": url, "company": company, "role": role, "jd_text": jd_text}

    except Exception as exc:
        return {"error": str(exc)}


def score_resume(jd_text: str) -> dict:
    if not _resume_text:
        return {"error": "No resume loaded. Call set_resume() before running the agent."}

    response = client.messages.parse(
        model="claude-opus-4-7",
        max_tokens=2048,
        system=(
            "You are an expert technical recruiter. Score the resume against the job "
            "description objectively. Use the full 0-100 range; a perfect match is rare."
        ),
        messages=[
            {
                "role": "user",
                "content": [
                    # Cache the JD — reused in the suggestions call
                    {
                        "type": "text",
                        "text": f"Job Description:\n{jd_text}",
                        "cache_control": {"type": "ephemeral"},
                    },
                    # Cache the resume — stable across all calls for this session
                    {
                        "type": "text",
                        "text": f"Resume:\n{_resume_text}",
                        "cache_control": {"type": "ephemeral"},
                    },
                    {
                        "type": "text",
                        "text": "Score this resume against the job description above.",
                    },
                ],
            }
        ],
        output_format=ResumeScore,
    )

    return response.parsed_output.model_dump()


def suggest_bullet_improvements(jd_text: str, role: str = "", company: str = "") -> dict:
    if not _resume_text:
        return {"error": "No resume loaded."}

    role_line = f"Role: {role} at {company}\n\n" if role else ""

    response = client.messages.parse(
        model="claude-opus-4-7",
        max_tokens=4096,
        system=(
            "You are an expert resume writer. Rewrite bullets to be more impactful "
            "for this specific role: strong action verbs, quantified results where possible, "
            "keywords from the JD woven in naturally. Prioritize changes by impact."
        ),
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"{role_line}Job Description:\n{jd_text}",
                        "cache_control": {"type": "ephemeral"},
                    },
                    {
                        "type": "text",
                        "text": f"Resume:\n{_resume_text}",
                        "cache_control": {"type": "ephemeral"},
                    },
                    {
                        "type": "text",
                        "text": "Suggest specific bullet improvements for this resume.",
                    },
                ],
            }
        ],
        output_format=BulletSuggestions,
    )

    return response.parsed_output.model_dump()


def save_application(
    url: str, company: str, role: str, jd_text: str, score: dict, suggestions: dict
) -> dict:
    try:
        app_id = db.save_application(url, company, role, jd_text, score, suggestions)
        return {"success": True, "application_id": app_id}
    except Exception as exc:
        return {"error": str(exc)}


def list_saved_applications(limit: int = 10) -> dict:
    try:
        apps = db.list_applications(limit)
        return {"applications": apps, "count": len(apps)}
    except Exception as exc:
        return {"error": str(exc)}


# ── Tool JSON definitions (sent to the main agent) ──────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "scrape_job_posting",
        "description": (
            "Fetch a job posting URL and extract the job description text, "
            "company name, and role title."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The full job posting URL"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "score_resume",
        "description": (
            "Score the user's resume against a job description. "
            "Returns overall score (0-100), skill match, experience match, "
            "matched/missing skills, strengths, and weaknesses."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "jd_text": {"type": "string", "description": "Full job description text"},
            },
            "required": ["jd_text"],
        },
    },
    {
        "name": "suggest_bullet_improvements",
        "description": (
            "Suggest specific resume bullet rewrites tailored to the job description. "
            "Returns prioritized edits with original, improved, and reasoning."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "jd_text":  {"type": "string", "description": "Full job description text"},
                "role":     {"type": "string", "description": "Job title"},
                "company":  {"type": "string", "description": "Company name"},
            },
            "required": ["jd_text"],
        },
    },
    {
        "name": "save_application",
        "description": "Log the complete job application analysis to the SQLite tracker database.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url":         {"type": "string"},
                "company":     {"type": "string"},
                "role":        {"type": "string"},
                "jd_text":     {"type": "string"},
                "score":       {"type": "object", "description": "Output from score_resume"},
                "suggestions": {"type": "object", "description": "Output from suggest_bullet_improvements"},
            },
            "required": ["url", "company", "role", "jd_text", "score", "suggestions"],
        },
    },
    {
        "name": "list_saved_applications",
        "description": "List previously tracked job applications from the database.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max rows to return (default 10)",
                },
            },
        },
    },
]


# ── Dispatcher ──────────────────────────────────────────────────────────────


def execute_tool(name: str, inputs: dict) -> dict:
    if name == "scrape_job_posting":
        return scrape_job_posting(inputs["url"])
    elif name == "score_resume":
        return score_resume(inputs["jd_text"])
    elif name == "suggest_bullet_improvements":
        return suggest_bullet_improvements(
            inputs["jd_text"],
            inputs.get("role", ""),
            inputs.get("company", ""),
        )
    elif name == "save_application":
        return save_application(
            inputs["url"],
            inputs["company"],
            inputs["role"],
            inputs["jd_text"],
            inputs["score"],
            inputs["suggestions"],
        )
    elif name == "list_saved_applications":
        return list_saved_applications(inputs.get("limit", 10))
    else:
        return {"error": f"Unknown tool: {name}"}
