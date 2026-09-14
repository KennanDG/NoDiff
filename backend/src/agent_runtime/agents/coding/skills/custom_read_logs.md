# Skill: Log Reader and Debug Summarizer

Purpose: Safely locate, filter, and summarize log files inside the repository to help diagnose errors, correlate events, and report likely causes without modifying log data.

Use when:
- The user asks to read, inspect, search, or explain a log file.
- A build, test, or runtime failure needs to be traced through logs.
- You need to correlate timestamps or request IDs across one or more logs.
- The user wants a concise error summary, frequency count, or first/last occurrence from logs.
- The log location is unknown and must be discovered within the repository.

Allowed tools:
- read_logs
- list_files
- read_file
- file_size
- resolve_in_repo
- search_repo
- robust_search
- is_allowed_command
- run_command

Steps:
1. Resolve the requested log path with resolve_in_repo; if it is ambiguous, use list_files to locate candidate files ending in .log or inside log directories.
2. Check each candidate with file_size before reading; note empty files and avoid loading oversized logs without filters.
3. Call read_logs with the narrowest useful filters first, such as severity level, time range, and a pattern or keyword.
4. If more filtering is needed, use search_repo or robust_search for matching lines, then read only relevant regions with read_file using offsets or line limits when available.
5. Group results by error signature, timestamp, request ID, or component to identify repeated failures and the first and last occurrences.
6. Correlate across multiple log files by shared timestamps, correlation IDs, or host/service names.
7. Verify any additional shell command with is_allowed_command before running it; allow only read-only commands such as grep, tail, head, wc, or cat.
8. Run the verified read-only command with run_command and capture only the minimal output needed.
9. Summarize findings as: what failed, when it started, how often it occurred, the strongest evidence lines, and the most likely causes.
10. Clearly separate confirmed evidence from hypotheses, and state which log files and line ranges were inspected.

Rules:
- Treat all log files as read-only: never edit, truncate, rotate, delete, or append to them.
- Never dump an entire large log file without filters; always narrow by level, time, pattern, or line limit first.
- Redact secrets, tokens, cookies, credentials, and personal data before quoting log content.
- Stay inside the repository root; do not follow symlinks or read paths outside the allowed workspace.
- Run shell access only through is_allowed_command, and only for read-only inspection commands.
- Do not use run_command for state-changing, network-facing, or destructive operations.
- If the requested log does not exist, say so directly instead of guessing or fabricating content.
- Use write_file only when the user explicitly requests a saved report, and never write inside log directories.
- Prefer exact quoted log lines with file and line references over paraphrased evidence.
- Cap summaries to the most relevant evidence and avoid pasting large blocks of raw logs.
