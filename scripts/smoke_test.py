#!/usr/bin/env python3
"""End-to-end smoke test against a running backend.

Usage: python3 scripts/smoke_test.py [--api-url URL] [--arxiv-id ID]"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request

ANSWERABLE = "How are positional encodings computed in the Transformer?"
UNRELATED = "What is a good recipe for sourdough bread?"

results: list[tuple[str, str, str]] = []  # (status, step, detail)


def call(
    base: str, method: str, path: str, body: dict | None = None
) -> tuple[int, dict | list]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        base + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"null")


def record(status: str, step: str, detail: str = "") -> None:
    results.append((status, step, detail))
    print(f"  [{status:^7}] {step}" + (f": {detail}" if detail else ""))


def check(condition: bool, step: str, detail: str = "") -> bool:
    record("PASSED" if condition else "FAILED", step, detail)
    return condition


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--api-url", default="http://localhost:8001")
    parser.add_argument("--arxiv-id", default="1706.03762")
    args = parser.parse_args()
    base = args.api_url.rstrip("/")

    print(f"Smoke test against {base}")
    try:
        status, body = call(base, "GET", "/health")
    except OSError as error:
        print(f"Cannot reach the backend: {error}")
        return 2
    if not check(status == 200 and body == {"status": "ok"}, "backend health"):
        return 1

    status, body = call(base, "POST", "/papers/import", {"arxiv_id": args.arxiv_id})
    if not check(
        status in (200, 201), "import paper", f"HTTP {status}: {body.get('detail', '')}"
    ):
        return 1
    paper = body["paper"]
    paper_id = paper["id"]
    record(
        "PASSED",
        "paper stored",
        f"id={paper_id} “{paper['title']}” created={body['created']}",
    )

    if paper["ingestion_status"] != "indexed":
        status, body = call(base, "POST", f"/papers/{paper_id}/process")
        if not check(
            status == 200, "process paper (PDF -> passages)", f"HTTP {status}"
        ):
            return 1
        record(
            "INFO",
            "extracted",
            f"{body['extracted_characters']} chars, {body['passage_count']} passages",
        )
        status, body = call(base, "POST", f"/papers/{paper_id}/index")
        if not check(
            status == 200, "index paper (embeddings)", f"HTTP {status}: {body}"
        ):
            return 1
        record(
            "INFO",
            "indexed",
            f"{body['indexed_passages']} passages, {body['embedding_dimension']} dims",
        )
    else:
        record("SKIPPED", "process + index", "paper is already indexed")

    status, passages = call(base, "GET", f"/papers/{paper_id}/passages")
    stored = {p["id"]: p["text"] for p in passages}
    check(
        status == 200 and len(stored) > 0,
        "passages are stored",
        f"{len(stored)} passages",
    )

    status, body = call(base, "POST", "/search", {"query": ANSWERABLE, "limit": 3})
    hits = body.get("results", [])
    check(
        status == 200 and len(hits) == 3 and hits[0]["score"] >= hits[-1]["score"],
        "semantic search returns ranked passages",
        f"top score {hits[0]['score']}" if hits else f"HTTP {status}",
    )

    status, body = call(
        base, "POST", "/ask", {"question": ANSWERABLE, "paper_ids": [paper_id]}
    )
    if status == 503:
        record(
            "SKIPPED",
            "answerable question",
            body.get("detail", "no language model available"),
        )
    elif check(
        status == 200 and not body["abstained"] and body["citations"],
        "answerable question gets a cited answer",
        f"HTTP {status}",
    ):
        record("INFO", "answer", body["answer"].replace("\n", " ")[:160])
        numbers = {int(n) for n in re.findall(r"\[(\d+)\]", body["answer"])}
        cited = {c["number"] for c in body["citations"]}
        check(
            numbers <= cited and bool(numbers),
            "every [n] in the answer has a citation",
            f"markers {sorted(numbers)}",
        )
        real = all(
            stored.get(c["passage_id"]) == c["passage_text"] for c in body["citations"]
        )
        check(
            real,
            "every citation is the exact text of a stored passage",
            f"{len(body['citations'])} citation(s)",
        )

    status, body = call(base, "POST", "/ask", {"question": UNRELATED})
    check(
        status == 200 and body["abstained"] and not body["citations"],
        "unrelated question abstains",
        f"reason={body.get('abstention_reason')} best_score={body.get('best_score')}",
    )

    failed = [r for r in results if r[0] == "FAILED"]
    skipped = [r for r in results if r[0] == "SKIPPED"]
    passed = [r for r in results if r[0] == "PASSED"]
    print(f"\n{len(passed)} passed, {len(failed)} failed, {len(skipped)} skipped")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
