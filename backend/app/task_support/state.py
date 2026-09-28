"""Shared task-state reducers."""

def merge_subtasks(left: list | None, right: list | None) -> list:
    """Merge subtask lists by id; right fields win."""
    left = list(left or [])
    right = list(right or [])
    if not right:
        return left
    if not left:
        return [dict(t) for t in right]
    index = {str(t.get("id")): dict(t) for t in left if t.get("id")}
    order = [str(t.get("id")) for t in left if t.get("id")]
    for t in right:
        tid = str(t.get("id") or "")
        if not tid:
            continue
        if tid in index:
            index[tid] = {**index[tid], **dict(t)}
        else:
            index[tid] = dict(t)
            order.append(tid)
    return [index[i] for i in order if i in index]
