# JobTracker

An AI-powered job application tracker that analyzes job postings against your resume, scores your fit, and suggests targeted resume improvements.

## What it does

1. Scrapes a job posting URL
2. Scores your resume against the job description (overall, skills, experience)
3. Generates prioritized resume bullet rewrites tailored to the role
4. Saves everything to a local SQLite database so you can track your applications

## Requirements

- Python 3.8+
- An [Anthropic API key](https://console.anthropic.com/)
- A `resume.txt` file with your resume text

## Setup

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key_here
```

On Windows (PowerShell):
```powershell
$env:ANTHROPIC_API_KEY = "your_key_here"
```

## Usage

**Analyze a job posting:**
```bash
python main.py analyze <url>
python main.py analyze <url> --resume cv.txt   # custom resume file
```

**List tracked applications:**
```bash
python main.py list
python main.py list --limit 50
```

**View full analysis for an application:**
```bash
python main.py show <id>
```

**Update application status:**
```bash
python main.py status <id> <status>
```

Available statuses: `tracked`, `applied`, `phone_screen`, `interview`, `offer`, `rejected`, `withdrawn`

## Output

Each analysis produces:
- **Scores** — overall match, skills alignment, and experience fit (0–100)
- **Matched / missing skills** — what lines up and what doesn't
- **Resume improvements** — specific before/after bullet rewrites with priority and reasoning
- **New bullets to add** — suggestions for gaps in your current resume
- **Strategy tip** — a high-level framing note for the application

## Tech stack

| Layer | Library |
|---|---|
| AI | Anthropic Claude (claude-opus-4-7) |
| HTTP / scraping | httpx, BeautifulSoup4 |
| Structured output | Pydantic |
| Database | SQLite |
| CLI / formatting | Rich, argparse |
