def is_double_jeopardy(new_issue: dict, seen_targets: list[dict], radius: int = 5) -> bool:
    """3D Double Jeopardy: file + snippet containment + line radius."""
    new_f = new_issue.get("file")
    if not new_f or new_f == "unknown":
        return False

    for seen in seen_targets:
        if new_f != seen.get("file"):
            continue

        # Snippet containment match
        new_snip = new_issue.get("snippet", "").strip()
        seen_snip = seen.get("snippet", "").strip()
        if new_snip and seen_snip and len(new_snip) > 5 and (new_snip in seen_snip or seen_snip in new_snip):
            return True

        # Line radius match
        n_line = new_issue.get("approx_line")
        s_line = seen.get("approx_line")
        if isinstance(n_line, int) and isinstance(s_line, int) and n_line > 0 and s_line > 0:
            if abs(n_line - s_line) <= radius:
                return True

    return False
