#!/usr/bin/env python3
"""Digest this project's Claude Code and Codex sessions for a retro.

Prints, per session in the window: the user's messages, skills invoked,
denied or failed tool calls, and a count of tools used. Assistant text and
tool output are left out, so a cycle's sessions fit in one read.

Sessions run in the workflow repo, so these are its logs, whichever
project they worked on:

    python3 .agents/skills/retro/digest.py --since 2026-10-09T10:00 [--until ...]
    python3 .agents/skills/retro/digest.py --session <id>
"""

import argparse
from collections import Counter
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
WORK_LOGS = ROOT / ".scratch"  # each cycle keeps its worker logs in <project>/<cycle>/work/
# The host's sessions, then each project's worker containers' (tools/legion/README.md: Containers).
CLAUDE_LOGS = [Path.home() / ".claude/projects" / str(ROOT).replace("/", "-"),
               *sorted(WORK_LOGS.glob("*/sessions/claude/*/"))]
CODEX_LOGS = [Path.home() / ".codex/sessions", *sorted(WORK_LOGS.glob("*/sessions/codex"))]
SKIP = ("<local-command-caveat>", "<system-reminder>", "<command-message>", "Caveat:")


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(part.get("text", "")) for part in content
                         if isinstance(part, dict) and part.get("type") == "text")
    return ""


def short(text, limit):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit] + " …"


def digest(path, since, until):
    events, tools, times, title = [], Counter(), [], ""
    for line in path.open():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        stamp = record.get("timestamp", "")
        if record.get("type") == "ai-title":
            title = record.get("aiTitle") or title
        if not stamp or (since and stamp < since) or (until and stamp > until):
            continue
        message = record.get("message")
        if not isinstance(message, dict) or record.get("isSidechain"):
            continue
        content = message.get("content")
        when = stamp[5:16].replace("T", " ")
        if record.get("type") == "user" and not record.get("isMeta"):
            text = text_of(content).strip()
            if "<command-name>" in text:
                name = text.split("<command-name>")[1].split("</command-name>")[0]
                events.append(f"- {when} COMMAND {name}")
            elif "<bash-input>" in text:
                events.append(f"- {when} USER SHELL {short(text, 200)}")
            elif text and not text.startswith(SKIP):
                events.append(f"- {when} USER {short(text, 700)}")
            times.append(stamp)
        if isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "tool_use":
                    tools[part.get("name", "?")] += 1
                    if part.get("name") == "Skill":
                        events.append(f"- {when} SKILL {part.get('input', {}).get('skill')}")
                elif part.get("type") == "tool_result" and part.get("is_error"):
                    kind = "DENIED" if record.get("toolDenialKind") or "denied" in text_of(part.get("content")).lower() \
                        else "ERROR"
                    body = part.get("content")
                    body = body if isinstance(body, str) else text_of(body)
                    events.append(f"- {when} {kind} {short(body, 300)}")
    if not times and not events:
        return None
    head = f"## Session {path.stem}" + (f": {title}" if title else "")
    span = f"{min(times)[:16]} to {max(times)[:16]}" if times else ""
    counts = ", ".join(f"{name} {n}" for name, n in tools.most_common())
    return "\n".join([head, "", span, f"Tools: {counts}", ""] + events)


def digest_worker(path, since, until):
    """Summarize a plain-text tools/work.sh log using its timestamped name."""
    # <issue>[-<role>]-YYYYMMDD-HHMMSS[-<attempt id>]
    match = re.fullmatch(r"(.+)-(\d{8})-(\d{6})(?:-[0-9a-f]{8})?", path.stem)
    if not match:
        return None
    parts = [match[1]]
    stamp = match[2] + match[3]
    date = f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}T{stamp[8:10]}:{stamp[10:12]}"
    if (since and date < since) or (until and date > until):
        return None
    lines = path.read_text(errors="replace").splitlines()
    interesting = []
    final_start = max((i for i, line in enumerate(lines)
                       if line.strip() == "tokens used"), default=-1)
    for i, line in enumerate(lines):
        clean = line.strip()
        if not clean:
            continue
        low = clean.lower()
        is_signal = (low.startswith(("error:", "script error:", "fatal server error:",
                                     "you've hit your weekly limit"))
                     or "usage limit" in low or low.startswith("session id:"))
        is_prompt = clean.startswith("Read .agents/skills/implement/SKILL.md")
        is_final = final_start >= 0 and i > final_start and not clean.startswith("hook:")
        if is_signal or is_prompt or is_final:
            event = f"- {short(clean, 360)}"
            if event not in interesting:
                interesting.append(event)
    title = parts[0]
    return "\n".join([f"## Worker {title}", "", date, f"Source: {path.relative_to(ROOT)}", ""] + interesting[:24])


def codex_digest(path, since, until):
    """Summarize Codex's structured rollout log for this project."""
    events, times, session_id = [], [], path.stem.rsplit("-", 1)[-1]
    for line in path.open(errors="replace"):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        stamp = record.get("timestamp", "")
        payload = record.get("payload", {})
        if record.get("type") == "session_meta":
            meta = payload
            session_id = meta.get("session_id", session_id)
            if Path(meta.get("cwd", "")).resolve() != ROOT:
                return None
        if not stamp or (since and stamp < since) or (until and stamp > until):
            continue
        times.append(stamp)
        when = stamp[5:16].replace("T", " ")
        if record.get("type") == "response_item" and payload.get("type") == "message":
            role = payload.get("role")
            content = payload.get("content", [])
            if role == "user":
                parts = [part.get("text", "") for part in content
                         if isinstance(part, dict) and part.get("type") == "input_text"]
                message = "\n".join(parts).strip()
                if message and not message.startswith(("<environment_context>", "# AGENTS.md", "<skill>")):
                    events.append(f"- {when} USER {short(message, 700)}")
            elif role == "assistant":
                phase = payload.get("phase", "")
                if phase == "final_answer":
                    message = "\n".join(part.get("text", "") for part in content
                                       if isinstance(part, dict) and part.get("type") == "output_text").strip()
                    if message:
                        events.append(f"- {when} FINAL {short(message, 1000)}")
        elif record.get("type") == "event_msg" and payload.get("type") == "item_completed":
            item = payload.get("item", {})
            if item.get("type") == "UserMessage":
                skills = [part.get("name") for part in item.get("content", [])
                          if isinstance(part, dict) and part.get("type") == "skill"]
                for name in skills:
                    events.append(f"- {when} SKILL ${name}")
            if item.get("type") == "CommandExecution" and (
                    item.get("status") == "failed" or item.get("exit_code", 0) not in (0, None)):
                command = " ".join(item.get("command", []))
                error = next((part.strip() for part in item.get("aggregated_output", "").splitlines()
                              if part.strip() and ("error" in part.lower() or "no such" in part.lower())), "")
                events.append(f"- {when} ERROR {short(command, 180)}: {short(error, 260)}")
    if not times and not events:
        return None
    return "\n".join([f"## Codex session {session_id}", "",
                      f"{min(times)[:16]} to {max(times)[:16]}", ""] + events)


def codex_session_id(path):
    for line in path.open(errors="replace"):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("type") == "session_meta":
            return record.get("payload", {}).get("session_id", "")
    return ""


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since", default="", help="ISO time, e.g. 2026-10-09T10:00")
    parser.add_argument("--until", default="")
    parser.add_argument("--session", default="", help="one session id")
    args = parser.parse_args()
    paths = sorted((p for d in CLAUDE_LOGS for p in d.glob("*.jsonl")), key=lambda p: p.stat().st_mtime)
    if args.session:
        paths = [p for p in paths if p.stem == args.session]
    found = [d for d in (digest(p, args.since, args.until) for p in paths) if d]
    by_session = {}
    for path in sorted((p for d in CODEX_LOGS for p in d.glob("**/*.jsonl")), key=lambda p: p.stat().st_size, reverse=True):
        session_id = codex_session_id(path)
        if session_id and session_id not in by_session:
            by_session[session_id] = path
    codex_paths = list(by_session.values())
    if args.session:
        codex_paths = [p for p in codex_paths if codex_session_id(p) == args.session]
    codex_digests = [codex_digest(p, args.since, args.until) for p in codex_paths]
    found.extend(d for d in codex_digests if d)
    codex_ids = {codex_session_id(p) for p in codex_paths}
    worker_paths = sorted(WORK_LOGS.glob("*/*/work/*.log"))
    if args.session:
        worker_paths = [p for p in worker_paths if p.stem == args.session or
                        f"session id: {args.session}" in p.read_text(errors="replace")]
    else:
        worker_paths = [p for p in worker_paths if not any(
            f"session id: {session_id}" in p.read_text(errors="replace") for session_id in codex_ids)]
    found.extend(d for d in (digest_worker(p, args.since, args.until)
                             for p in worker_paths) if d)
    print(f"# Session digest ({len(found)} sessions/workers; Claude: {', '.join(map(str, CLAUDE_LOGS))}; Codex: {', '.join(map(str, CODEX_LOGS))}; worker logs: {WORK_LOGS})\n")
    print("\n\n".join(found) if found else "No sessions in that window.")


if __name__ == "__main__":
    main()
