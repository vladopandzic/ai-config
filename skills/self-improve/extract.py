"""Collects the user's own messages from Claude Code sessions across all projects into one text file."""

import argparse
import glob
import json
import os
import re
from datetime import datetime, timedelta, timezone

DEFAULT_DAYS = 30
MAX_MESSAGE_LENGTH = 700
MAX_PROJECT_NAME_LENGTH = 40
SYSTEM_REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
PASTED_CONTENT = re.compile(r"<pasted_content[^>]*>.*?</pasted_content[^>]*>", re.S)
NOT_TYPED_BY_USER = (
    "<command", "<local-command", "<task-notification", "<side-sessions", "<ci-monitor",
    "Base directory for this skill", "## Arguments", "Caveat:", "This session is being continued",
    "[Request interrupted",
)
CORRECTION_HINT = re.compile(
    r"(^\s*(ne|nee+|ma ne|pa ne|no|nope|stop)\b|nemoj|ne volim|ne razumi|zašto|zasto|čemu|cemu|zapam|radije|krivo|"
    r"pogrešn|ne treba|ne želim|ne zelim|previše|previse|komplic|opet|stalno|koliko puta|rekao sam|rekla sam|"
    r"već sam|vec sam|nisi |ubuduće|ubuduce|uvijek|nikad|smeta|!!|"
    r"remember|actually|don't|do not|never|always|again|wrong|instead|i said|i told you|stop)",
    re.I,
)
VOICE_HINT = re.compile(
    r"(ne\s+(razum|zarum|arzum|kužim|kuzim|shvaćam|shvacam)|nejasn|previše teksta|previse teksta|"
    r"(previše|previse|zvuči|zvuci)\s+(kao\s+)?AI|kompliciran|za glupane|summary|sažetak|ukratko|preduga|"
    r"ne mogu (to )?sve|too long|unclear|don't understand|do not understand)",
    re.I,
)
MAX_REPLY_LENGTH = 1500


def parse_arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--out", required=True)
    parser.add_argument("--projects-dir", default=os.path.join(os.path.expanduser("~"), ".claude", "projects"))
    parser.add_argument("--all", action="store_true", help="keep every message, not only ones that look like corrections")
    parser.add_argument("--voice", action="store_true", help="keep complaints about how Claude writes, each with the reply it reacted to")
    return parser.parse_args()


def project_name(session_path):
    folder = os.path.basename(os.path.dirname(session_path))
    name = re.sub(r"^[A-Za-z]--(PROJEKTI-|Users-[^-]+-)?", "", folder)
    return "scratch" if "scratch" in name else name[:MAX_PROJECT_NAME_LENGTH]


def typed_texts(entry):
    content = entry.get("message", {}).get("content")
    if isinstance(content, str):
        return [content]
    return [part.get("text", "") for part in content or [] if isinstance(part, dict) and part.get("type") == "text"]


def clean(text):
    return PASTED_CONTENT.sub("[PASTE]", SYSTEM_REMINDER.sub("", text or "")).strip()


def rejection_feedback(entry):
    result = entry.get("toolUseResult")
    if not isinstance(result, str) or "user said:" not in result:
        return ""
    return result.split("user said:", 1)[1].strip()


def reply_excerpt(reply):
    if len(reply) <= MAX_REPLY_LENGTH:
        return reply
    return f"{reply[:MAX_REPLY_LENGTH]} […cut, whole reply {len(reply)} chars]"


def main():
    arguments = parse_arguments()
    cutoff = datetime.now(timezone.utc) - timedelta(days=arguments.days)
    rejections, messages, voice_complaints, seen = [], [], [], set()
    session_count = 0

    for session_path in glob.glob(os.path.join(arguments.projects_dir, "*", "*.jsonl")):
        modified = datetime.fromtimestamp(os.path.getmtime(session_path), timezone.utc)
        if modified < cutoff:
            continue
        session_count += 1
        project = project_name(session_path)
        last_reply = ""

        for line in open(session_path, encoding="utf-8", errors="replace"):
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get("isSidechain"):
                continue
            if entry.get("type") == "assistant":
                reply = "\n".join(text for text in typed_texts(entry) if text.strip())
                last_reply = reply or last_reply
                continue
            is_user_entry = entry.get("type") == "user" and not entry.get("isMeta")
            if not is_user_entry:
                continue
            timestamp = entry.get("timestamp", "")
            if timestamp and datetime.fromisoformat(timestamp.replace("Z", "+00:00")) < cutoff:
                continue
            tag = f"[{timestamp[:10]} {project}]"

            feedback = rejection_feedback(entry)
            if feedback:
                rejections.append(f"{tag} {feedback[:MAX_MESSAGE_LENGTH]}")

            for text in map(clean, typed_texts(entry)):
                is_candidate = text and not text.startswith(NOT_TYPED_BY_USER) and len(text) <= MAX_MESSAGE_LENGTH and text not in seen
                if not is_candidate:
                    continue
                seen.add(text)
                if arguments.voice:
                    if VOICE_HINT.search(text) and last_reply:
                        voice_complaints.append(f"{tag} USER: {' '.join(text.split())}\nCLAUDE BEFORE:\n{reply_excerpt(last_reply)}")
                elif arguments.all or CORRECTION_HINT.search(text):
                    messages.append(f"{tag} {' '.join(text.split())}")

    with open(arguments.out, "w", encoding="utf-8") as output:
        output.write(f"Sessions: {session_count}, last {arguments.days} days\n\n")
        if arguments.voice:
            output.write(f"VOICE COMPLAINTS ({len(voice_complaints)})\n\n" + "\n\n---\n\n".join(sorted(voice_complaints)) + "\n")
        else:
            output.write(f"TOOL REJECTIONS ({len(rejections)})\n" + "\n".join(sorted(rejections)) + "\n\n")
            output.write(f"MESSAGES ({len(messages)})\n" + "\n".join(sorted(messages)) + "\n")

    print(f"sessions={session_count} rejections={len(rejections)} messages={len(messages)} voice={len(voice_complaints)} -> {arguments.out}")


if __name__ == "__main__":
    main()
