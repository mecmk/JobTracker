#!/usr/bin/env python3
"""
Agentic Job Application Tracker
Usage:
  python main.py analyze <url>              # analyse a job posting
  python main.py analyze <url> --resume cv.txt
  python main.py list                       # show all tracked applications
  python main.py show <id>                  # show full details for one application
  python main.py status <id> <status>       # update status (applied/rejected/offer/etc.)
"""

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

import database as db
import tools as tool_module
import agent

console = Console()

DEFAULT_RESUME = Path(__file__).parent / "resume.txt"


def cmd_analyze(args: argparse.Namespace) -> None:
    resume_path = Path(args.resume)
    if not resume_path.exists():
        console.print(f"[red]Resume not found:[/red] {resume_path}")
        console.print(
            f"[dim]Create {resume_path} with your resume text, "
            "or pass --resume <path>[/dim]"
        )
        sys.exit(1)

    resume_text = resume_path.read_text(encoding="utf-8")
    if len(resume_text.strip()) < 50:
        console.print("[red]Resume file appears empty.[/red]")
        sys.exit(1)

    db.init_db()
    tool_module.set_resume(resume_text)
    agent.run_agent(args.url)


def cmd_list(args: argparse.Namespace) -> None:
    db.init_db()
    apps = db.list_applications(args.limit)
    if not apps:
        console.print("[dim]No applications tracked yet. Run: python main.py analyze <url>[/dim]")
        return

    table = Table(title=f"Tracked Applications ({len(apps)})", show_lines=False)
    table.add_column("ID",      style="dim", justify="right", width=4)
    table.add_column("Company", min_width=14)
    table.add_column("Role",    min_width=20)
    table.add_column("Score",   justify="center", width=7)
    table.add_column("Status",  width=10)
    table.add_column("Date",    width=10)

    for app in apps:
        score_val = app.get("overall_score")
        if score_val is not None:
            colour = "green" if score_val >= 70 else "yellow" if score_val >= 50 else "red"
            score_str = f"[{colour}]{score_val}[/{colour}]"
        else:
            score_str = "[dim]—[/dim]"

        table.add_row(
            str(app["id"]),
            (app.get("company") or "—")[:22],
            (app.get("role") or "—")[:36],
            score_str,
            app.get("status") or "tracked",
            (app.get("created_at") or "")[:10],
        )

    console.print(table)


def cmd_show(args: argparse.Namespace) -> None:
    db.init_db()
    app = db.get_application(args.id)
    if not app:
        console.print(f"[red]Application #{args.id} not found.[/red]")
        sys.exit(1)

    console.rule(f"[bold]Application #{app['id']}[/bold]")
    console.print(f"[bold]Role:[/bold]    {app.get('role') or '—'}")
    console.print(f"[bold]Company:[/bold] {app.get('company') or '—'}")
    console.print(f"[bold]URL:[/bold]     {app.get('url')}")
    console.print(f"[bold]Status:[/bold]  {app.get('status')}")
    console.print(f"[bold]Date:[/bold]    {(app.get('created_at') or '')[:19]}")

    console.rule("[bold]Scores[/bold]")
    overall = app.get("overall_score")
    colour = "green" if (overall or 0) >= 70 else "yellow" if (overall or 0) >= 50 else "red"
    console.print(f"  Overall:    [{colour}]{overall}/100[/{colour}]")
    console.print(f"  Skills:     {app.get('skill_score')}/100")
    console.print(f"  Experience: {app.get('exp_score')}/100")

    if app.get("matched_skills"):
        console.print(f"\n[green]✓ Matched:[/green] {', '.join(app['matched_skills'])}")
    if app.get("missing_skills"):
        console.print(f"[red]✗ Missing:[/red] {', '.join(app['missing_skills'])}")

    if app.get("strengths"):
        console.print("\n[bold]Strengths:[/bold]")
        for s in app["strengths"]:
            console.print(f"  • {s}")

    if app.get("weaknesses"):
        console.print("\n[bold]Weaknesses:[/bold]")
        for w in app["weaknesses"]:
            console.print(f"  • {w}")

    suggestions = app.get("suggestions") or {}
    edits = suggestions.get("edits", [])
    if edits:
        console.rule("[bold]Bullet Improvements[/bold]")
        for i, edit in enumerate(edits, 1):
            priority = edit.get("priority", "?")
            colour = "red" if priority == "high" else "yellow" if priority == "medium" else "dim"
            console.print(f"\n[bold]{i}. [{colour}]{priority.upper()}[/{colour}] — {edit.get('section', '')}[/bold]")
            console.print(f"  [dim]Before:[/dim] {edit.get('original', '')}")
            console.print(f"  [green]After:[/green]  {edit.get('improved', '')}")
            console.print(f"  [dim]Why: {edit.get('reason', '')}[/dim]")

    new_bullets = suggestions.get("new_bullets_to_add", [])
    if new_bullets:
        console.rule("[bold]New Bullets to Add[/bold]")
        for b in new_bullets:
            console.print(f"  + {b}")

    if suggestions.get("overall_tip"):
        console.rule("[bold]Overall Tip[/bold]")
        console.print(suggestions["overall_tip"])


def cmd_status(args: argparse.Namespace) -> None:
    db.init_db()
    db.update_status(args.id, args.status)
    console.print(f"[green]✓[/green] Application #{args.id} → [bold]{args.status}[/bold]")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="job_tracker",
        description="Agentic Job Application Tracker powered by Claude",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # analyze
    p_analyze = sub.add_parser("analyze", help="Analyse a job posting URL")
    p_analyze.add_argument("url", help="Job posting URL")
    p_analyze.add_argument(
        "--resume",
        default=str(DEFAULT_RESUME),
        help="Path to resume text file (default: resume.txt)",
    )

    # list
    p_list = sub.add_parser("list", help="List all tracked applications")
    p_list.add_argument("--limit", type=int, default=20, help="Max rows to show")

    # show
    p_show = sub.add_parser("show", help="Show full details for an application")
    p_show.add_argument("id", type=int, help="Application ID")

    # status
    p_status = sub.add_parser("status", help="Update application status")
    p_status.add_argument("id", type=int)
    p_status.add_argument(
        "status",
        choices=["tracked", "applied", "phone_screen", "interview", "offer", "rejected", "withdrawn"],
    )

    args = parser.parse_args()

    if args.command == "analyze":
        cmd_analyze(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "show":
        cmd_show(args)
    elif args.command == "status":
        cmd_status(args)


if __name__ == "__main__":
    main()
