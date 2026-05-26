"""
Core agentic loop.

The agent orchestrates four tools in sequence:
  scrape_job_posting → score_resume → suggest_bullet_improvements → save_application

Adaptive thinking is enabled so the model can reason carefully about
skill gaps and resume strategy before surfacing tool calls.
"""

from __future__ import annotations

import json

import anthropic
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule

import tools as tool_module

console = Console()
client = anthropic.Anthropic()

SYSTEM_PROMPT = """\
You are an expert job application coach.

When given a job URL, follow these steps **in order**:
1. Call `scrape_job_posting` to fetch the job description.
2. Call `score_resume` with the jd_text from step 1.
3. Call `suggest_bullet_improvements` with the jd_text, role, and company from step 1.
4. Call `save_application` with all data from steps 1-3.
5. Write a concise final report (Markdown) covering:
   - Match score breakdown (overall / skills / experience)
   - Top 3 missing skills to address
   - The 3 highest-priority bullet rewrites (show original → improved)
   - One concrete next action

Be direct. Do not repeat tool outputs verbatim — synthesise them.
"""

MAX_ITERATIONS = 12


def run_agent(job_url: str) -> None:
    messages: list[dict] = [
        {
            "role": "user",
            "content": f"Analyse this job posting and improve my resume for it: {job_url}",
        }
    ]

    console.print(Panel(f"[bold cyan]Job Tracker[/bold cyan]  →  {job_url}", expand=False))

    for iteration in range(MAX_ITERATIONS):
        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=4096,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            tools=tool_module.TOOL_DEFINITIONS,
            messages=messages,
        )

        # ── display text blocks ──────────────────────────────────────────
        for block in response.content:
            if block.type == "text" and block.text.strip():
                console.print(Markdown(block.text))

        # ── collect tool calls ───────────────────────────────────────────
        tool_calls = [b for b in response.content if b.type == "tool_use"]

        if not tool_calls:
            # No more tool calls → agent is done
            break

        # Append the full assistant turn (thinking + text + tool_use blocks)
        messages.append({"role": "assistant", "content": response.content})

        # ── execute tools ────────────────────────────────────────────────
        tool_results = []
        for tc in tool_calls:
            console.print(Rule(f"[cyan]{tc.name}[/cyan]", style="dim"))
            _print_tool_input(tc.name, tc.input)

            result = tool_module.execute_tool(tc.name, tc.input)

            is_error = isinstance(result, dict) and "error" in result
            if is_error:
                console.print(f"[red]✗ Error:[/red] {result['error']}")
            else:
                _print_tool_result(tc.name, result)

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": json.dumps(result) if isinstance(result, (dict, list)) else str(result),
                    **({"is_error": True} if is_error else {}),
                }
            )

        messages.append({"role": "user", "content": tool_results})

    else:
        console.print("[yellow]Warning: reached max iterations.[/yellow]")


# ── Display helpers ─────────────────────────────────────────────────────────


def _print_tool_input(name: str, inputs: dict) -> None:
    SKIP_KEYS = {"jd_text", "score", "suggestions"}  # too long to print
    preview = {k: v for k, v in inputs.items() if k not in SKIP_KEYS}
    if preview:
        console.print(f"  [dim]{json.dumps(preview, ensure_ascii=False)[:160]}[/dim]")


def _print_tool_result(name: str, result: dict) -> None:
    if name == "scrape_job_posting":
        company = result.get("company", "?")
        role = result.get("role", "?")
        chars = len(result.get("jd_text", ""))
        console.print(f"  [green]✓[/green] {role} @ {company}  ({chars:,} chars scraped)")

    elif name == "score_resume":
        s = result.get("overall_score", "?")
        sk = result.get("skill_match_score", "?")
        ex = result.get("experience_score", "?")
        colour = "green" if (result.get("overall_score") or 0) >= 70 else "yellow"
        console.print(
            f"  [green]✓[/green] Overall [{colour}]{s}/100[/{colour}]  "
            f"| Skills {sk}/100  | Experience {ex}/100"
        )
        missing = result.get("missing_skills", [])
        if missing:
            console.print(f"  [red]Missing:[/red] {', '.join(missing[:5])}")

    elif name == "suggest_bullet_improvements":
        edits = result.get("edits", [])
        console.print(f"  [green]✓[/green] {len(edits)} bullet edit(s) generated")
        for edit in edits[:2]:
            console.print(f"  [dim]  [{edit.get('priority','?')}] {edit.get('section','')[:40]}[/dim]")

    elif name == "save_application":
        app_id = result.get("application_id", "?")
        console.print(f"  [green]✓[/green] Saved as application [bold]#{app_id}[/bold]")

    else:
        console.print(f"  [green]✓[/green]")
