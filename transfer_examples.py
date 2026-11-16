"""Public examples and independent small oracles for the new transfer API."""
import sys
from fractions import Fraction as F
from random import Random
from polyarchive import Archive


def box(x0, y0, x1, y1):
    return [(F(x0), F(y0)), (F(x1), F(y0)),
            (F(x1), F(y1)), (F(x0), F(y1))]


def ring(points):
    return [(F(x), F(y)) for x, y in points]


def fixture():
    a = Archive()
    a.put("old", box(0, 0, 4, 4), [box(1, 1, 3, 3)])
    a.put("half", box(0, 0, 2, 4))
    a.put("hole", box(2, 1, 3, 3))
    a.put("touch", box(4, 0, 5, 4))
    return a


def must_raise(kind, call):
    try:
        call()
    except kind:
        return
    raise AssertionError("expected " + kind.__name__)


def check_ledger(plan, amounts, expected_pairs):
    got = plan.allocate(amounts)
    assert set(got) == {"pairs", "remaining", "totals"}
    assert got["pairs"] == expected_pairs
    assert set(got["remaining"]) == set(plan.source_ids)
    assert set(got["totals"]) == set(plan.target_ids)
    assert set(got["pairs"]) == set(plan.overlaps)
    for mapping in got.values():
        assert list(mapping) == sorted(mapping)
        assert all(isinstance(x, F) and x >= 0 for x in mapping.values())
    for s in plan.source_ids:
        assigned = sum((v for (src, _), v in got["pairs"].items()
                        if src == s), F(0))
        assert assigned + got["remaining"][s] == amounts[s]
    for t in plan.target_ids:
        assert got["totals"][t] == sum(
            (v for (_, dst), v in got["pairs"].items() if dst == t), F(0))
    return got


def rectangle_overlap(a, b):
    # Independent oracle for axis-aligned rectangles only.
    return (max(F(0), min(a[2], b[2]) - max(a[0], b[0]))
            * max(F(0), min(a[3], b[3]) - max(a[1], b[1])))


def verify():
    a = fixture()
    before = a.dumps()
    sources, targets = ["old"], ["touch", "hole", "half"]
    p = a.transfer_plan(sources, targets)
    assert p.source_ids == ("old",)
    assert p.target_ids == ("half", "hole", "touch")
    assert dict(p.source_areas) == {"old": F(12)}
    assert dict(p.overlaps) == {("old", "half"): F(6)}
    assert dict(p.uncovered) == {"old": F(6)}
    for mapping in (p.source_areas, p.overlaps, p.uncovered):
        assert list(mapping) == sorted(mapping)
        assert all(isinstance(v, F) for v in mapping.values())
    got = check_ledger(p, {"old": F(120)}, {("old", "half"): F(60)})
    assert got["remaining"] == {"old": F(60)}
    assert got["totals"] == {"half": F(60), "hole": F(0), "touch": F(0)}
    assert a.dumps() == before
    got["totals"]["half"] = F(999)
    assert p.allocate({"old": F(120)})["totals"]["half"] == 60
    zero = check_ledger(p, {"old": F(0)}, {("old", "half"): F(0)})
    assert zero["remaining"] == {"old": F(0)}
    sources.clear()
    targets.clear()
    for bad in ({}, {"old": F(-1)}, {"old": 1}, {"old": True},
                {"old": 1.0}, {"old": F(1), "extra": F(0)}, []):
        must_raise(ValueError, lambda bad=bad: p.allocate(bad))
    assert p.allocate({"old": F(120)})["remaining"] == {"old": F(60)}

    # Both sides have the same hole; the effective area remains 12.
    same = a.transfer_plan(["old"], ["old"])
    assert dict(same.overlaps) == {("old", "old"): F(12)}
    assert dict(same.uncovered) == {"old": F(0)}
    check_ledger(same, {"old": F(7)}, {("old", "old"): F(7)})
    # A separate region occupying a hole is legal in the same source group.
    nested = a.transfer_plan(["old", "hole"], ["half"])
    assert dict(nested.overlaps) == {("old", "half"): F(6)}

    a.put("bad", box(0, 0, 1, 1))
    for src, dst in ((["old", "bad"], ["half"]),
                     (["old"], ["bad", "half"]),
                     ([], ["half"]), (["old", "old"], ["half"]),
                     (("old",), ["half"]), (["old"], [""])):
        saved = a.dumps()
        must_raise(ValueError, lambda: a.transfer_plan(src, dst))
        assert a.dumps() == saved
    must_raise(KeyError, lambda: a.transfer_plan(["missing"], ["half"]))

    # Ordinary public immutability attempts must not alter the plan.
    for attr in ("source_areas", "overlaps", "uncovered"):
        mapping = getattr(p, attr)
        old = dict(mapping)
        key = next(iter(mapping))
        try:
            mapping[key] = F(999)
        except Exception:
            pass
        assert dict(getattr(p, attr)) == old
    try:
        p.source_ids = ("changed",)
    except Exception:
        pass
    assert p.source_ids == ("old",)

    a.put("old", box(0, 0, 1, 1))
    a.put("half", box(20, 20, 21, 21))
    saved = a.dumps()
    assert p.allocate({"old": F(120)})["totals"]["half"] == 60
    assert a.dumps() == saved

    sloped = Archive()
    sloped.put("s", ring([(0, 0), (2, 0), (2, 2)]))
    sloped.put("t", ring([(0, 0), (2, 0), (0, 2)]))
    q = sloped.transfer_plan(["s"], ["t"])
    assert dict(q.overlaps) == {("s", "t"): F(1)}
    assert dict(q.uncovered) == {"s": F(1)}
    check_ledger(q, {"s": F(2)}, {("s", "t"): F(1)})

    concave = [(0, 0), (3, 0), (3, 1), (1, 1), (1, 3), (0, 3)]
    for points in (concave, concave[::-1]):
        sloped.put("s", ring(points))
        sloped.put("t", box(-1, -1, 4, 4))
        q = sloped.transfer_plan(["s"], ["t"])
        assert dict(q.overlaps) == {("s", "t"): F(5)}
        check_ledger(q, {"s": F(5)}, {("s", "t"): F(5)})

    rng = Random(17031)
    geometry = {
        "s0": ((F(0), F(0), F(4), F(4)), (F(1), F(1), F(3), F(3))),
        "s1": ((F(4), F(0), F(8), F(4)), (F(5), F(1), F(7), F(3))),
    }
    for _ in range(24):
        ar = Archive()
        for s, (outer, hole) in geometry.items():
            ar.put(s, box(*outer), [box(*hole)])
        cuts = sorted(F(x, 2) for x in rng.sample(range(-2, 19), 6))
        rectangles = {}
        for i in range(3):
            t = "t" + str(i)
            rect = (cuts[2*i], F(-1), cuts[2*i+1], F(5))
            rectangles[t] = rect
            ar.put(t, box(*rect))
        plan = ar.transfer_plan(["s1", "s0"], ["t2", "t0", "t1"])
        expected = {}
        for s, (outer, hole) in geometry.items():
            for t, rect in rectangles.items():
                area = rectangle_overlap(outer, rect) - rectangle_overlap(hole, rect)
                if area > 0:
                    expected[s, t] = area
        assert dict(plan.source_areas) == {"s0": F(12), "s1": F(12)}
        assert dict(plan.overlaps) == expected
        for s in geometry:
            assert plan.uncovered[s] == 12 - sum(
                (v for (src, _), v in expected.items() if src == s), F(0))
        amounts = {"s0": F(7, 3), "s1": F(11, 5)}
        pairs = {key: amounts[key[0]] * area / 12 for key, area in expected.items()}
        check_ledger(plan, amounts, pairs)
    print("TRANSFER_CONTRACT_OK: exact weights, residuals and ledgers agree")


def demo():
    a = fixture()
    p = a.transfer_plan(["old"], ["touch", "hole", "half"])
    print("source areas:", dict(p.source_areas))
    print("positive overlaps:", dict(p.overlaps))
    print("uncovered areas:", dict(p.uncovered))
    print("amount 120:", p.allocate({"old": F(120)}))
    a.put("old", box(0, 0, 1, 1))
    print("same fixed plan after archive replacement:", p.allocate({"old": F(120)}))


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("verify", "demo"):
        raise SystemExit("usage: python3.11 -B transfer_examples.py verify|demo")
    (verify if sys.argv[1] == "verify" else demo)()
