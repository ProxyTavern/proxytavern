#!/usr/bin/env python3
"""Reply to a GitHub PR review thread/comment with fallback to PR-level comment.

Requires GitHub CLI (`gh`) to be installed and authenticated.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


EXIT_OK = 0
EXIT_TARGET_NOT_FOUND = 2
EXIT_INLINE_FAILED_FALLBACK_OK = 3
EXIT_BOTH_POSTS_FAILED = 4
EXIT_RUNTIME_ERROR = 5


@dataclass
class MatchResult:
    mode: str
    target_input: str
    thread_node_id: Optional[str]
    thread_resolved: Optional[bool]
    comment_node_id: Optional[str]
    comment_database_id: Optional[int]
    comment_url: Optional[str]


def run_gh(args: List[str], stdin_text: Optional[str] = None) -> Tuple[int, str, str]:
    proc = subprocess.run(
        ["gh", *args],
        input=stdin_text,
        text=True,
        capture_output=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


def gh_json(args: List[str]) -> Any:
    rc, out, err = run_gh(args)
    if rc != 0:
        raise RuntimeError(f"gh command failed ({rc}): {' '.join(shlex.quote(x) for x in args)}\n{err.strip()}")
    try:
        return json.loads(out)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON from gh command: {e}\nOutput:\n{out[:500]}") from e


def resolve_repo_slug(explicit_repo: Optional[str]) -> str:
    if explicit_repo:
        return explicit_repo
    rc, out, err = run_gh(["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"])
    if rc != 0:
        raise RuntimeError(
            "Could not infer repository from current directory. Pass --repo owner/name.\n"
            f"gh repo view error: {err.strip()}"
        )
    slug = out.strip()
    if not slug or "/" not in slug:
        raise RuntimeError(f"Unexpected repository slug: {slug!r}")
    return slug


def fetch_review_threads(owner: str, repo: str, pr_number: int) -> List[Dict[str, Any]]:
    query = """
query($owner: String!, $name: String!, $pr: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $pr) {
      id
      number
      reviewThreads(first: 100) {
        nodes {
          id
          isResolved
          comments(first: 100) {
            nodes {
              id
              databaseId
              url
              body
              createdAt
              replyTo {
                id
                databaseId
              }
              author {
                login
              }
            }
          }
        }
      }
    }
  }
}
""".strip()
    data = gh_json([
        "api",
        "graphql",
        "-f",
        f"query={query}",
        "-F",
        f"owner={owner}",
        "-F",
        f"name={repo}",
        "-F",
        f"pr={pr_number}",
    ])
    pr = data.get("data", {}).get("repository", {}).get("pullRequest")
    if not pr:
        raise RuntimeError(f"PR #{pr_number} not found in {owner}/{repo}")
    return pr.get("reviewThreads", {}).get("nodes", []) or []


def normalize_target(raw: str) -> str:
    raw = raw.strip()
    m = re.search(r"discussion_r(\d+)", raw)
    if m:
        return m.group(1)
    if raw.isdigit():
        return raw
    return raw


def match_target(threads: List[Dict[str, Any]], target: str) -> Optional[MatchResult]:
    target_n = normalize_target(target)

    # 1) Exact thread node id match
    for t in threads:
        if t.get("id") == target_n:
            comments = t.get("comments", {}).get("nodes", []) or []
            last = comments[-1] if comments else {}
            return MatchResult(
                mode="thread_id",
                target_input=target,
                thread_node_id=t.get("id"),
                thread_resolved=t.get("isResolved"),
                comment_node_id=last.get("id"),
                comment_database_id=last.get("databaseId"),
                comment_url=last.get("url"),
            )

    # 2) comment database id or comment node id match
    for t in threads:
        for c in (t.get("comments", {}).get("nodes", []) or []):
            if str(c.get("databaseId")) == target_n:
                return MatchResult(
                    mode="comment_database_id",
                    target_input=target,
                    thread_node_id=t.get("id"),
                    thread_resolved=t.get("isResolved"),
                    comment_node_id=c.get("id"),
                    comment_database_id=c.get("databaseId"),
                    comment_url=c.get("url"),
                )
            if c.get("id") == target_n:
                return MatchResult(
                    mode="comment_node_id",
                    target_input=target,
                    thread_node_id=t.get("id"),
                    thread_resolved=t.get("isResolved"),
                    comment_node_id=c.get("id"),
                    comment_database_id=c.get("databaseId"),
                    comment_url=c.get("url"),
                )

    return None


def post_inline_reply(owner: str, repo: str, parent_comment_id: int, body: str) -> Dict[str, Any]:
    return gh_json([
        "api",
        "-X",
        "POST",
        f"repos/{owner}/{repo}/pulls/comments/{parent_comment_id}/replies",
        "-f",
        f"body={body}",
    ])


def post_pr_fallback(owner: str, repo: str, pr_number: int, body: str) -> Dict[str, Any]:
    return gh_json([
        "api",
        "-X",
        "POST",
        f"repos/{owner}/{repo}/issues/{pr_number}/comments",
        "-f",
        f"body={body}",
    ])


def build_fallback_body(user_body: str, target: str, reason: str, matched: Optional[MatchResult]) -> str:
    context = [
        "⚠️ Inline review reply failed; posting as PR-level fallback.",
        f"Target: `{target}`",
        f"Reason: {reason}",
    ]
    if matched:
        context.append(f"Matched thread: `{matched.thread_node_id}`")
        context.append(f"Matched comment databaseId: `{matched.comment_database_id}`")
        if matched.comment_url:
            context.append(f"Matched comment URL: {matched.comment_url}")
    context.append("")
    context.append(user_body)
    return "\n".join(context)


def to_summary(
    *,
    repo: str,
    pr: int,
    target: str,
    matched: Optional[MatchResult],
    inline_ok: bool,
    inline_error: Optional[str],
    fallback_ok: bool,
    fallback_error: Optional[str],
    inline_url: Optional[str],
    fallback_url: Optional[str],
    dry_run: bool,
    listed: bool,
) -> Dict[str, Any]:
    return {
        "repo": repo,
        "pr": pr,
        "target": target,
        "dry_run": dry_run,
        "list_mode": listed,
        "matched": None
        if not matched
        else {
            "mode": matched.mode,
            "thread_node_id": matched.thread_node_id,
            "thread_resolved": matched.thread_resolved,
            "comment_node_id": matched.comment_node_id,
            "comment_database_id": matched.comment_database_id,
            "comment_url": matched.comment_url,
        },
        "inline_reply": {
            "ok": inline_ok,
            "url": inline_url,
            "error": inline_error,
        },
        "fallback_pr_comment": {
            "ok": fallback_ok,
            "url": fallback_url,
            "error": fallback_error,
        },
    }


def print_text_summary(summary: Dict[str, Any]) -> None:
    print(f"repo: {summary['repo']}")
    print(f"pr: {summary['pr']}")
    print(f"target: {summary['target']}")
    print(f"dry_run: {summary['dry_run']}")
    if summary.get("list_mode"):
        print("mode: list")
    matched = summary.get("matched")
    print(f"matched: {'yes' if matched else 'no'}")
    if matched:
        print(f"  match_mode: {matched['mode']}")
        print(f"  thread_id: {matched['thread_node_id']}")
        print(f"  comment_db_id: {matched['comment_database_id']}")
        print(f"  comment_url: {matched['comment_url']}")
    ir = summary.get("inline_reply", {})
    print(f"inline_reply_ok: {ir.get('ok')}")
    if ir.get("url"):
        print(f"inline_reply_url: {ir['url']}")
    if ir.get("error"):
        print(f"inline_reply_error: {ir['error']}")
    fb = summary.get("fallback_pr_comment", {})
    print(f"fallback_ok: {fb.get('ok')}")
    if fb.get("url"):
        print(f"fallback_url: {fb['url']}")
    if fb.get("error"):
        print(f"fallback_error: {fb['error']}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pr", type=int, required=True, help="Pull request number")
    p.add_argument("--target", required=True, help="Target review comment ID/thread ID/or discussion URL")
    p.add_argument("--body", help="Reply body text")
    p.add_argument("--body-file", help="Read reply body from file")
    p.add_argument("--repo", help="owner/name (defaults to current gh repo)")
    p.add_argument("--dry-run", action="store_true", help="Resolve and report without posting")
    p.add_argument("--list", action="store_true", help="List discovered threads/comments for the PR")
    p.add_argument("--format", choices=["json", "text"], default="json")
    args = p.parse_args()

    if not args.list and not args.dry_run and not (args.body or args.body_file):
        p.error("--body or --body-file is required unless --dry-run/--list")

    body = ""
    if args.body_file:
        with open(args.body_file, "r", encoding="utf-8") as f:
            body = f.read()
    elif args.body:
        body = args.body

    try:
        slug = resolve_repo_slug(args.repo)
        owner, repo = slug.split("/", 1)
        threads = fetch_review_threads(owner, repo, args.pr)

        if args.list:
            listing = []
            for t in threads:
                for c in (t.get("comments", {}).get("nodes", []) or []):
                    listing.append(
                        {
                            "thread_node_id": t.get("id"),
                            "thread_resolved": t.get("isResolved"),
                            "comment_node_id": c.get("id"),
                            "comment_database_id": c.get("databaseId"),
                            "comment_url": c.get("url"),
                            "author": (c.get("author") or {}).get("login"),
                            "createdAt": c.get("createdAt"),
                            "replyTo_databaseId": (c.get("replyTo") or {}).get("databaseId"),
                        }
                    )
            out = {"repo": slug, "pr": args.pr, "count": len(listing), "comments": listing}
            if args.format == "json":
                print(json.dumps(out, indent=2))
            else:
                print(f"repo={slug} pr={args.pr} comments={len(listing)}")
                for row in listing:
                    print(
                        f"thread={row['thread_node_id']} comment_db={row['comment_database_id']} "
                        f"comment_node={row['comment_node_id']} url={row['comment_url']}"
                    )
            return EXIT_OK

        matched = match_target(threads, args.target)
        if not matched:
            summary = to_summary(
                repo=slug,
                pr=args.pr,
                target=args.target,
                matched=None,
                inline_ok=False,
                inline_error="Target not found in first 100 review threads/comments",
                fallback_ok=False,
                fallback_error=None,
                inline_url=None,
                fallback_url=None,
                dry_run=args.dry_run,
                listed=False,
            )
            if args.format == "json":
                print(json.dumps(summary, indent=2))
            else:
                print_text_summary(summary)
            return EXIT_TARGET_NOT_FOUND

        if args.dry_run:
            summary = to_summary(
                repo=slug,
                pr=args.pr,
                target=args.target,
                matched=matched,
                inline_ok=False,
                inline_error=None,
                fallback_ok=False,
                fallback_error=None,
                inline_url=None,
                fallback_url=None,
                dry_run=True,
                listed=False,
            )
            if args.format == "json":
                print(json.dumps(summary, indent=2))
            else:
                print_text_summary(summary)
            return EXIT_OK

        if not matched.comment_database_id:
            inline_error = "Matched thread/comment has no databaseId for REST replies"
            fallback_body = build_fallback_body(body, args.target, inline_error, matched)
            try:
                fb = post_pr_fallback(owner, repo, args.pr, fallback_body)
                summary = to_summary(
                    repo=slug,
                    pr=args.pr,
                    target=args.target,
                    matched=matched,
                    inline_ok=False,
                    inline_error=inline_error,
                    fallback_ok=True,
                    fallback_error=None,
                    inline_url=None,
                    fallback_url=fb.get("html_url"),
                    dry_run=False,
                    listed=False,
                )
                if args.format == "json":
                    print(json.dumps(summary, indent=2))
                else:
                    print_text_summary(summary)
                return EXIT_INLINE_FAILED_FALLBACK_OK
            except Exception as e:
                summary = to_summary(
                    repo=slug,
                    pr=args.pr,
                    target=args.target,
                    matched=matched,
                    inline_ok=False,
                    inline_error=inline_error,
                    fallback_ok=False,
                    fallback_error=str(e),
                    inline_url=None,
                    fallback_url=None,
                    dry_run=False,
                    listed=False,
                )
                if args.format == "json":
                    print(json.dumps(summary, indent=2))
                else:
                    print_text_summary(summary)
                return EXIT_BOTH_POSTS_FAILED

        # Try inline first.
        try:
            ir = post_inline_reply(owner, repo, matched.comment_database_id, body)
            summary = to_summary(
                repo=slug,
                pr=args.pr,
                target=args.target,
                matched=matched,
                inline_ok=True,
                inline_error=None,
                fallback_ok=False,
                fallback_error=None,
                inline_url=ir.get("html_url") or ir.get("url"),
                fallback_url=None,
                dry_run=False,
                listed=False,
            )
            if args.format == "json":
                print(json.dumps(summary, indent=2))
            else:
                print_text_summary(summary)
            return EXIT_OK
        except Exception as e:
            inline_error = str(e)
            fallback_body = build_fallback_body(body, args.target, inline_error, matched)
            try:
                fb = post_pr_fallback(owner, repo, args.pr, fallback_body)
                summary = to_summary(
                    repo=slug,
                    pr=args.pr,
                    target=args.target,
                    matched=matched,
                    inline_ok=False,
                    inline_error=inline_error,
                    fallback_ok=True,
                    fallback_error=None,
                    inline_url=None,
                    fallback_url=fb.get("html_url"),
                    dry_run=False,
                    listed=False,
                )
                if args.format == "json":
                    print(json.dumps(summary, indent=2))
                else:
                    print_text_summary(summary)
                return EXIT_INLINE_FAILED_FALLBACK_OK
            except Exception as e2:
                summary = to_summary(
                    repo=slug,
                    pr=args.pr,
                    target=args.target,
                    matched=matched,
                    inline_ok=False,
                    inline_error=inline_error,
                    fallback_ok=False,
                    fallback_error=str(e2),
                    inline_url=None,
                    fallback_url=None,
                    dry_run=False,
                    listed=False,
                )
                if args.format == "json":
                    print(json.dumps(summary, indent=2))
                else:
                    print_text_summary(summary)
                return EXIT_BOTH_POSTS_FAILED

    except Exception as e:
        err = {"error": str(e), "exit": EXIT_RUNTIME_ERROR}
        print(json.dumps(err, indent=2))
        return EXIT_RUNTIME_ERROR


if __name__ == "__main__":
    sys.exit(main())
