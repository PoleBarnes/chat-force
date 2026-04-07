#!/usr/bin/env python3
"""chat-force — ticket-driven self-improving prototyping tool."""

import glob
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

try:
    from importlib.metadata import version as _pkg_version
    VERSION = _pkg_version("chat-force")
except Exception:
    VERSION = "dev"
TEMPLATES_DIR = Path(__file__).parent / "templates"
MECHANIC_PROMPT = TEMPLATES_DIR / "mechanic-prompt.md"
PM_PROMPT = TEMPLATES_DIR / "pm-prompt.md"

# Colors
BLUE = "\033[0;34m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
NC = "\033[0m"


def info(msg):
    print(f"{BLUE}[chat-force]{NC} {msg}")


def ok(msg):
    print(f"{GREEN}[chat-force]{NC} {msg}")


def warn(msg):
    print(f"{YELLOW}[chat-force]{NC} {msg}")


def error(msg):
    print(f"{RED}[chat-force]{NC} {msg}", file=sys.stderr)


def gen_session_id():
    return str(uuid.uuid4())


def run_cmd(args, **kwargs):
    return subprocess.run(args, **kwargs)


def require_claude():
    if shutil.which("claude") is None:
        error("Claude Code CLI not found.")
        sys.exit(1)


def require_project():
    if not Path("CLAUDE.md").exists():
        error("Not a chat-force project. Run 'chat-force init' first.")
        sys.exit(1)


def require_tracker():
    cfg_path = Path(".claude/chat-force.json")
    if cfg_path.exists():
        return

    info("No tracker configured. Which platform do you use?")
    tracker = _prompt_choice("Select", [("Linear", "linear"), ("Jira", "jira")])

    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps({"tracker": tracker}, indent=2) + "\n")
    ok(f"Tracker set to {tracker}")

    if not Path(".mcp.json").exists():
        tpl = TEMPLATES_DIR / "general"
        if tracker == "jira" and (tpl / ".mcp.jira.json").exists():
            shutil.copy2(tpl / ".mcp.jira.json", ".mcp.json")
        elif (tpl / ".mcp.json").exists():
            shutil.copy2(tpl / ".mcp.json", ".mcp.json")
        if Path(".mcp.json").exists():
            ok(f"Created .mcp.json ({tracker} MCP config)")


def read_tracker():
    cfg_path = Path(".claude/chat-force.json")
    if cfg_path.exists():
        return json.loads(cfg_path.read_text()).get("tracker", "(unknown)")
    return "(unknown)"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_mechanic(args):
    require_claude()
    require_project()

    session_id = args[0] if args else ""
    info("Launching mechanic review...")
    if session_id:
        info(f"Session: {session_id}")
    print()

    claude_args = []
    if MECHANIC_PROMPT.exists():
        claude_args += ["--system-prompt", str(MECHANIC_PROMPT)]

    if session_id:
        project_path = os.getcwd()
        project_key = project_path.replace("/", "-")
        session_file = Path.home() / ".claude" / "projects" / f"-{project_key}" / f"{session_id}.jsonl"
        if session_file.exists():
            info("Found session transcript.")
        else:
            info("Session file not found — mechanic will work from git state.")

    remaining = args[1:] if len(args) > 1 else []
    run_cmd(["claude"] + claude_args + remaining)


def _prompt_choice(prompt_msg, options):
    """Prompt user to pick from numbered options. Returns the chosen value."""
    for i, (label, _) in enumerate(options, 1):
        print(f"  {i}) {label}")
    try:
        choice = input(f"{BLUE}[chat-force]{NC} {prompt_msg}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(1)
    # Accept number or value
    for i, (label, value) in enumerate(options, 1):
        if choice == str(i) or choice.lower() == value:
            return value
    error(f"Invalid choice: {choice}")
    sys.exit(1)


def _prompt_input(prompt_msg, required=False):
    """Prompt user for a text input. Empty skips."""
    try:
        value = input(f"{BLUE}[chat-force]{NC} {prompt_msg}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""
    return value


def cmd_init(args):
    template = "general"
    tracker = None  # None means: prompt interactively
    project_name = ""
    i = 0
    while i < len(args):
        if args[i] == "--template" and i + 1 < len(args):
            template = args[i + 1]
            i += 2
        elif args[i] == "--tracker" and i + 1 < len(args):
            tracker = args[i + 1]
            i += 2
        elif not args[i].startswith("-") and not project_name:
            project_name = args[i]
            i += 1
        else:
            i += 1

    tpl = TEMPLATES_DIR / template
    if not tpl.is_dir():
        error(f"Template '{template}' not found.")
        sys.exit(1)

    if tracker and tracker not in ("linear", "jira"):
        error(f"Unknown tracker: {tracker} (use 'linear' or 'jira')")
        sys.exit(1)

    # If project name given, create/enter the directory
    if project_name:
        project_dir = Path(project_name)
        if project_dir.exists():
            os.chdir(project_dir)
            info(f"Using existing directory: {project_name}")
        else:
            project_dir.mkdir(parents=True)
            os.chdir(project_dir)
            ok(f"Created directory: {project_name}")

        # Init git if not already a repo
        if not Path(".git").exists():
            run_cmd(["git", "init"], capture_output=True)
            ok("  Initialized git repository")

    # Interactive tracker selection if not specified
    if tracker is None:
        print()
        info("Which ticket tracker do you use?")
        tracker = _prompt_choice("Select", [("Linear", "linear"), ("Jira", "jira")])

    info(f"Initializing project (template: {template}, tracker: {tracker})...")

    # CLAUDE.md
    if not Path("CLAUDE.md").exists() and (tpl / "CLAUDE.md").exists():
        shutil.copy2(tpl / "CLAUDE.md", "CLAUDE.md")
        ok("  Created CLAUDE.md")

    # MCP config — copy template then inject real API key
    if not Path(".mcp.json").exists():
        if tracker == "jira" and (tpl / ".mcp.jira.json").exists():
            shutil.copy2(tpl / ".mcp.jira.json", ".mcp.json")
        elif (tpl / ".mcp.json").exists():
            shutil.copy2(tpl / ".mcp.json", ".mcp.json")

        if Path(".mcp.json").exists():
            # Prompt for API credentials
            mcp_data = json.loads(Path(".mcp.json").read_text())
            updated = False

            if tracker == "linear":
                print()
                info("Linear API key required for MCP integration.")
                info("Get yours at: Linear → Settings → API → Personal API keys")
                api_key = _prompt_input("LINEAR_API_KEY (enter to skip)")
                if api_key:
                    mcp_data["mcpServers"]["linear"]["env"]["LINEAR_API_KEY"] = api_key
                    updated = True
                else:
                    warn("  Skipped — edit .mcp.json to add your LINEAR_API_KEY later")

            elif tracker == "jira":
                print()
                info("Jira credentials required for MCP integration.")
                info("Get an API token at: https://id.atlassian.com/manage-profile/security/api-tokens")
                jira_url = _prompt_input("Jira instance URL (enter to skip)")
                if jira_url:
                    jira_email = _prompt_input("Jira email")
                    jira_token = _prompt_input("Jira API token")
                    if jira_email and jira_token:
                        env = mcp_data["mcpServers"]["atlassian"]["env"]
                        env["JIRA_URL"] = jira_url
                        env["JIRA_EMAIL"] = jira_email
                        env["JIRA_API_TOKEN"] = jira_token
                        updated = True
                if not updated:
                    warn("  Skipped — edit .mcp.json to add your Jira credentials later")

            if updated:
                Path(".mcp.json").write_text(json.dumps(mcp_data, indent=2) + "\n")

            ok(f"  Created .mcp.json ({tracker} MCP config)")

    # .claude dirs
    for d in (".claude/rules", ".claude/skills", ".claude/agents"):
        Path(d).mkdir(parents=True, exist_ok=True)

    # settings.json
    src_settings = tpl / ".claude" / "settings.json"
    dst_settings = Path(".claude/settings.json")
    if src_settings.exists() and not dst_settings.exists():
        shutil.copy2(src_settings, dst_settings)
        ok("  Created .claude/settings.json")

    # Rules
    rules_dir = tpl / ".claude" / "rules"
    if rules_dir.exists():
        for rule in rules_dir.glob("*.md"):
            dst = Path(".claude/rules") / rule.name
            if not dst.exists():
                shutil.copy2(rule, dst)
                ok(f"  Created .claude/rules/{rule.name}")

    # Ticket templates
    tpl_templates = tpl / ".claude" / "ticket-templates"
    if tpl_templates.exists():
        Path(".claude/ticket-templates").mkdir(parents=True, exist_ok=True)
        for tmpl in tpl_templates.glob("*.json"):
            dst = Path(".claude/ticket-templates") / tmpl.name
            if not dst.exists():
                shutil.copy2(tmpl, dst)
                ok(f"  Created .claude/ticket-templates/{tmpl.name}")

    # Skills
    skills_dir = tpl / ".claude" / "skills"
    if skills_dir.exists():
        Path(".claude/skills").mkdir(parents=True, exist_ok=True)
        for skill in skills_dir.glob("*.md"):
            dst = Path(".claude/skills") / skill.name
            if not dst.exists():
                shutil.copy2(skill, dst)
                ok(f"  Created .claude/skills/{skill.name}")

    # Vault
    if not Path("vault").exists():
        for d in ("raw", "summaries/sources", "summaries/sessions",
                   "entities", "concepts", "decisions"):
            Path(f"vault/{d}").mkdir(parents=True, exist_ok=True)
        for vf in ("VAULT.md", "index.md", "log.md"):
            src = tpl / "vault" / vf
            if src.exists():
                shutil.copy2(src, f"vault/{vf}")
        ok("  Created vault/")

    # Project config
    cfg_path = Path(".claude/chat-force.json")
    if not cfg_path.exists():
        cfg_path.write_text(json.dumps({"tracker": tracker}, indent=2) + "\n")
        ok(f"  Created .claude/chat-force.json (tracker: {tracker})")

    # Mechanic log
    Path(".mechanic/log").mkdir(parents=True, exist_ok=True)
    ok("  Created .mechanic/log/")

    print()
    ok("Done! Edit CLAUDE.md, then run 'chat-force prototype'")


def cmd_create_ticket(args):
    require_project()
    require_tracker()

    template = ""
    interactive = False
    fields = []
    i = 0
    while i < len(args):
        if args[i] == "--template" and i + 1 < len(args):
            template = args[i + 1]
            i += 2
        elif args[i] == "--field" and i + 1 < len(args):
            fields.append(args[i + 1])
            i += 2
        elif args[i] == "--interactive":
            interactive = True
            i += 1
        else:
            error(f"Unknown arg: {args[i]}")
            sys.exit(1)

    if not template:
        error("Missing --template <name>")
        sys.exit(1)

    tpl_file = Path(f".claude/ticket-templates/{template}.json")
    if not tpl_file.exists():
        error(f"Template '{template}' not found.")
        error("Available templates:")
        for f in sorted(Path(".claude/ticket-templates").glob("*.json")):
            error(f"  {f.stem}")
        sys.exit(1)

    if interactive:
        require_claude()
        session_id = gen_session_id()
        info(f"Launching interactive ticket creation (template: {template})")
        prompt = (
            f"You are helping create a ticket from the '{template}' template. "
            f"Read the template at {tpl_file} to see what fields are required. "
            f"Interview the user for each required field one at a time. "
            f"When all fields are gathered, output the complete ticket as JSON "
            f"to stdout and save it to .ticket-context."
        )
        rc = run_cmd(["claude", "--session-id", session_id, "-p", prompt]).returncode
        sys.exit(rc)

    tpl_data = json.loads(tpl_file.read_text())

    # Parse fields
    provided = {}
    for fa in fields:
        if "=" not in fa:
            error(f"Invalid field format: {fa} (expected key=value)")
            sys.exit(1)
        k, v = fa.split("=", 1)
        provided[k] = v

    # Check required inputs
    required_names = [inp["name"] for inp in tpl_data.get("required_inputs", [])]
    missing = [n for n in required_names if n not in provided]
    if missing:
        error(f"Missing required fields: {', '.join(missing)}")
        error("Hint: use --interactive to gather fields via interview")
        sys.exit(1)

    ticket = {
        "template": template,
        "inputs": provided,
        "acceptance_criteria": tpl_data.get("acceptance_criteria", []),
        "required_artifacts": tpl_data.get("required_artifacts", []),
        "skills": tpl_data.get("skills", []),
    }
    print(json.dumps(ticket, indent=2))


def cmd_list_templates(args):
    require_project()

    tpl_dir = Path(".claude/ticket-templates")
    if not tpl_dir.exists():
        error("No ticket templates found. Run 'chat-force init' first.")
        sys.exit(1)

    info("Available ticket templates:")
    print()
    for f in sorted(tpl_dir.glob("*.json")):
        data = json.loads(f.read_text())
        desc = data.get("description", "(no description)")
        print(f"  {f.stem:<20s} {desc}")


def cmd_run(args):
    require_claude()
    require_project()

    extra_args = [a for a in args if a.startswith("-")]

    # Print welcome banner — we control this, not Claude
    print()
    print(f"  {BLUE}chat-force{NC} v{VERSION}")
    print()
    print(f"  This session runs three phases:")
    print(f"    {GREEN}1. BUILD{NC}   — You work with Claude to build the deliverable")
    print(f"    {YELLOW}2. REVIEW{NC}  — A PM agent checks output against acceptance criteria")
    print(f"    {BLUE}3. IMPROVE{NC} — A mechanic agent analyzes and improves the harness")
    print()
    print(f"  {GREEN}Phase 1: BUILD{NC} — starting now")
    print(f"  Give Claude a ticket ID (e.g. PROJ-42) or describe what to build.")
    print()

    # System prompt — work instructions only, no greeting
    system_prompt = (
        "You are a chat-force build agent in Phase 1 (BUILD).\n\n"
        "The user will give you either a ticket ID or a task description. "
        "If they give a ticket ID, pull it from the tracker via MCP. "
        "If they describe a task, confirm and start working.\n\n"
        "During work:\n"
        "- Read CLAUDE.md for project context\n"
        "- Read .claude/rules/ and .claude/skills/ for project rules and skills\n"
        "- Check git log and existing files — if previous work exists, don't redo it\n"
        "- Read vault/ for project knowledge\n"
        "- Follow the session-close checklist in CLAUDE.md before finishing\n"
        "- When done, commit your work\n"
    )

    prompt_file = Path(".chat-force-swarm-prompt.md")
    prompt_file.write_text(system_prompt)

    # Write minimal ticket context so Phase 2/3 have something to verify against
    if not Path(".ticket-context").exists():
        ctx = {"ticket_id": "session", "branch": "current", "attempt": 1}
        Path(".ticket-context").write_text(json.dumps(ctx, indent=2) + "\n")

    session_id = gen_session_id()

    print(f"  {NC}When done building, type {GREEN}/exit{NC} to move to the Review phase.")
    print(f"  {NC}(Don't use Ctrl+C — that aborts the entire sequence.)")
    print()

    # Status line script path from installed package
    statusline_script = Path(__file__).parent / "statusline.sh"

    # Session-scoped settings: custom status line
    session_settings = json.dumps({
        "statusLine": {
            "type": "command",
            "command": str(statusline_script),
        }
    })

    # Phase env var for status line
    env = os.environ.copy()
    env["CHAT_FORCE_PHASE"] = "build"

    # Launch claude interactively: Opus model, high effort, custom status line
    rc = run_cmd(
        ["claude", "--session-id", session_id,
         "--model", "opus",
         "--effort", "high",
         "--system-prompt", str(prompt_file),
         "--settings", session_settings]
        + extra_args,
        env=env,
    ).returncode

    if prompt_file.exists():
        prompt_file.unlink()

    if rc not in (0, 130):
        warn(f"Build phase exited with code {rc}")

    # Commit any uncommitted work
    result = run_cmd(["git", "status", "--porcelain"], capture_output=True, text=True)
    if result.stdout.strip():
        run_cmd(["git", "add", "-A"])
        run_cmd(["git", "commit", "-m", "WIP: chat-force session"])
        commit = run_cmd(["git", "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
        ok(f"Build committed: {commit}")

    # Phase 2: PM Verification
    print()
    print(f"  {'=' * 60}")
    print(f"  {YELLOW}Phase 2: REVIEW{NC} — PM verification")
    print(f"  Checking deliverables against acceptance criteria...")
    print(f"  {'=' * 60}")
    print()
    _run_pm_verification("session", "current")

    # Phase 3: Mechanic Reflection
    print()
    print(f"  {'=' * 60}")
    print(f"  {BLUE}Phase 3: IMPROVE{NC} — Mechanic analysis")
    print(f"  Analyzing session for harness improvements...")
    print(f"  {'=' * 60}")
    print()
    _run_mechanic_reflection("session", "current")

    print()
    print(f"  {'=' * 60}")
    ok("All three phases complete.")
    print(f"  {'=' * 60}")
    print()


def _write_ticket_context(ticket_id, branch):
    attempt = 1
    result = run_cmd(
        ["git", "log", "--oneline", f"--grep=WIP: {ticket_id}"],
        capture_output=True, text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        attempt = len(result.stdout.strip().splitlines()) + 1

    ctx = {
        "ticket_id": ticket_id,
        "branch": branch,
        "attempt": attempt,
    }

    # Try to read acceptance criteria from general template
    for tpl_file in glob.glob(".claude/ticket-templates/*.json"):
        data = json.loads(Path(tpl_file).read_text())
        if data.get("name") == "general":
            ctx["acceptance_criteria"] = data.get("acceptance_criteria", [])
            ctx["required_artifacts"] = data.get("required_artifacts", [])
            break

    Path(".ticket-context").write_text(json.dumps(ctx, indent=2) + "\n")


def _run_swarm(ticket_id, branch, extra_args):
    session_id = gen_session_id()
    info("=== Phase 1: Execution Swarm ===")
    info(f"Ticket: {ticket_id} | Branch: {branch} | Session: {session_id}")
    print()

    swarm_prompt = (
        f"You are executing ticket {ticket_id}. Read .ticket-context for the full "
        f"ticket details including acceptance criteria.\n\n"
        f"BEFORE STARTING WORK:\n"
        f"1. Check git log and the existing files on this branch. If previous work "
        f"exists, DO NOT redo it. Pick up where the last session left off.\n"
        f"2. Read the ticket's comment history (use list_comments for {ticket_id}) "
        f"to check for previous attempts. If prior attempts exist, read the PM Review "
        f"comments to understand what failed and why — do NOT repeat the same mistakes.\n"
        f"3. Run 'git diff main' or 'ls output/' to see what's already been produced.\n\n"
        f"Work to satisfy all acceptance criteria. When done, ensure all artifacts are "
        f"saved and committed."
    )

    # Write swarm instructions as system prompt. Launch claude interactively
    # so the user gets the full UI (spinner, tool calls, streaming output).
    # The system prompt tells Claude what to do; the user just types "go" or
    # their own instructions to start.
    prompt_file = Path(".chat-force-swarm-prompt.md")
    prompt_file.write_text(swarm_prompt)

    ctx_data = json.loads(Path(".ticket-context").read_text())
    desc = ctx_data.get("description", "")
    if desc:
        info(f"Task: {desc}")
    info("Type 'go' to start, or give additional instructions.")
    print()

    rc = run_cmd(
        ["claude", "--session-id", session_id,
         "--system-prompt", str(prompt_file)]
        + extra_args
    ).returncode

    if prompt_file.exists():
        prompt_file.unlink()
    print()
    if rc not in (0, 130):
        warn(f"Swarm exited with code {rc}")

    # Commit changes
    result = run_cmd(["git", "status", "--porcelain"], capture_output=True, text=True)
    if result.stdout.strip():
        run_cmd(["git", "add", "-A"])
        run_cmd(["git", "commit", "-m", f"WIP: {ticket_id} session"])
        commit = run_cmd(["git", "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
        ok(f"Swarm committed: {commit}")
    else:
        info("Swarm produced no changes.")


def _run_pm_verification(ticket_id, branch):
    session_id = gen_session_id()
    print()
    info("=== Phase 2: PM Verification ===")
    info(f"Ticket: {ticket_id} | Session: {session_id}")
    print()

    pm_args = []
    if PM_PROMPT.exists():
        pm_args += ["--system-prompt", str(PM_PROMPT)]

    pm_instruction = (
        f"Verify the deliverables for ticket {ticket_id}. Read .ticket-context "
        f"for acceptance criteria, then inspect the artifacts produced. "
        f"Present your pass/fail verdict per criterion."
    )

    env = os.environ.copy()
    env["CHAT_FORCE_PHASE"] = "review"
    rc = run_cmd(
        ["claude", "--session-id", session_id] + pm_args + ["-p", pm_instruction],
        env=env,
    ).returncode
    print()
    if rc not in (0, 130):
        warn(f"PM verification exited with code {rc}")

    ok("PM verification complete.")


def _run_mechanic_reflection(ticket_id, branch):
    session_id = gen_session_id()
    print()
    info("=== Phase 3: Mechanic Reflection ===")
    info(f"Ticket: {ticket_id} | Session: {session_id}")
    print()

    mechanic_args = []
    if MECHANIC_PROMPT.exists():
        mechanic_args += ["--system-prompt", str(MECHANIC_PROMPT)]

    mechanic_instruction = (
        f"Analyze the execution of ticket {ticket_id} on branch {branch}. "
        f"Read .ticket-context for the ticket details. Review git diff and "
        f"session artifacts, then propose harness improvements.\n\n"
        f"IMPORTANT: You are running in AUTO-COMMIT mode (non-interactive). "
        f"Do NOT wait for approval. Instead:\n"
        f"1. Analyze the session and identify improvements\n"
        f"2. Write ALL proposals to .mechanic/log/ as documented in your prompt\n"
        f"3. For each proposal, write the actual file (skill, rule, etc.) directly\n"
        f"4. Stage and commit everything with message: mechanic: <summary>\n"
        f"5. Do NOT skip the .mechanic/log/ entry — that's the audit trail\n"
        f"6. Check .mcp.json for tooling gaps — if the session struggled with a "
        f"missing capability, research and trial MCP servers as documented in your prompt"
    )

    env = os.environ.copy()
    env["CHAT_FORCE_PHASE"] = "improve"
    rc = run_cmd(
        ["claude", "--session-id", session_id] + mechanic_args + ["-p", mechanic_instruction],
        env=env,
    ).returncode
    print()
    if rc not in (0, 130):
        warn(f"Mechanic exited with code {rc}")

    result = run_cmd(["git", "status", "--porcelain"], capture_output=True, text=True)
    if result.stdout.strip():
        run_cmd(["git", "add", "-A"])
        run_cmd(["git", "commit", "-m", f"mechanic: {ticket_id} harness improvements"])
        commit = run_cmd(["git", "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
        ok(f"Mechanic committed: {commit}")
    else:
        info("Mechanic produced no changes.")


def cmd_status(args):
    require_project()
    require_tracker()

    result = run_cmd(["git", "branch", "--show-current"],
                     capture_output=True, text=True)
    branch = result.stdout.strip() if result.returncode == 0 else "(detached)"

    tracker = read_tracker()

    ticket_id = ""
    attempts = 0
    if branch.startswith("ticket/"):
        ticket_id = branch[len("ticket/"):]
        result = run_cmd(
            ["git", "log", "--oneline", f"--grep=WIP: {ticket_id}"],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            attempts = len(result.stdout.strip().splitlines())

    print()
    info("Project Status")
    print(f"  Branch:     {branch}")
    print(f"  Tracker:    {tracker}")

    if ticket_id:
        print(f"  Ticket:     {ticket_id}")
        print(f"  Attempts:   {attempts}")
        if Path(".ticket-context").exists():
            print("  Context:    .ticket-context (active session)")
    else:
        print("  Ticket:     (none — not on a ticket branch)")

    result = run_cmd(["git", "status", "--porcelain"], capture_output=True, text=True)
    changes = len(result.stdout.strip().splitlines()) if result.stdout.strip() else 0
    print(f"  Changes:    {changes} uncommitted file(s)")
    print()


def cmd_help():
    print(f"""chat-force v{VERSION} — self-improving prototyping tool

Usage:
  chat-force                            Launch session (init if needed, then build → review → improve)
  chat-force init [name] [--tracker linear|jira]
                                        Scaffold a new project
  chat-force status                     Show current branch, tracker, attempts
  chat-force create-ticket --template T Create ticket from template
  chat-force list-templates             List available ticket templates
  chat-force mechanic                   Manual mechanic review
  chat-force help                       This help""")


def main():
    args = sys.argv[1:]
    commands = {
        "init": cmd_init,
        "status": cmd_status,
        "create-ticket": cmd_create_ticket,
        "list-templates": cmd_list_templates,
        "mechanic": cmd_mechanic,
        "help": lambda _: cmd_help(),
        "--help": lambda _: cmd_help(),
        "-h": lambda _: cmd_help(),
        "version": lambda _: print(f"chat-force v{VERSION}"),
        "--version": lambda _: print(f"chat-force v{VERSION}"),
        "-v": lambda _: print(f"chat-force v{VERSION}"),
    }

    # No args or unrecognized first arg → default behavior
    if not args or args[0] not in commands:
        # Not initialized? Run init first.
        if not Path("CLAUDE.md").exists():
            cmd_init(args)
        # Then launch the three-phase session
        cmd_run(args)
        return

    cmd = args[0]
    rest = args[1:]
    commands[cmd](rest)


if __name__ == "__main__":
    main()
