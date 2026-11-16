"""Exact independent polygon storage; Python 3.11 standard library."""
from dataclasses import dataclass
from fractions import Fraction
import json
from types import MappingProxyType

Point = tuple[Fraction, Fraction]
Ring = tuple[Point, ...]


def _sequence(value):
    if not isinstance(value, (list, tuple)):
        raise ValueError("expected list or tuple")
    return value


def _point(value):
    _sequence(value)
    if len(value) != 2 or not all(isinstance(x, Fraction) for x in value):
        raise ValueError("coordinates must be Fraction pairs")
    return tuple(value)


def _cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on(p, a, b):
    return (_cross(a, b, p) == 0
            and min(a[0], b[0]) <= p[0] <= max(a[0], b[0])
            and min(a[1], b[1]) <= p[1] <= max(a[1], b[1]))


def _edges(ring):
    return zip(ring, ring[1:] + ring[:1])


def _segment_kind(a, b, c, d):
    ab_c, ab_d = _cross(a, b, c), _cross(a, b, d)
    cd_a, cd_b = _cross(c, d, a), _cross(c, d, b)
    if ab_c == ab_d == cd_a == cd_b == 0:
        common = {p for p in (a, b, c, d) if _on(p, a, b) and _on(p, c, d)}
        return "overlap" if len(common) > 1 else "point" if common else "none"
    if ab_c * ab_d < 0 and cd_a * cd_b < 0:
        return "cross"
    if (_on(c, a, b) or _on(d, a, b)
            or _on(a, c, d) or _on(b, c, d)):
        return "point"
    return "none"


def _twice_area(ring):
    return sum((a[0] * b[1] - b[0] * a[1] for a, b in _edges(ring)), Fraction(0))


def _location(ring, p):
    inside = False
    for a, b in _edges(ring):
        if _on(p, a, b):
            return "boundary"
        if (a[1] > p[1]) != (b[1] > p[1]):
            x = a[0] + (p[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if p[0] < x:
                inside = not inside
    return "interior" if inside else "exterior"


def _ring(value):
    ring = tuple(_point(p) for p in _sequence(value))
    if len(ring) < 3 or any(a == b for a, b in _edges(ring)):
        raise ValueError("ring needs at least three distinct consecutive vertices")
    if _twice_area(ring) == 0:
        raise ValueError("zero-area ring")
    edges = list(_edges(ring))
    for i, (a, b) in enumerate(edges):
        for j in range(i + 1, len(edges)):
            c, d = edges[j]
            kind = _segment_kind(a, b, c, d)
            adjacent = j == i + 1 or (i == 0 and j == len(edges) - 1)
            if (adjacent and kind != "point") or (not adjacent and kind != "none"):
                raise ValueError("ring is not simple")
    return ring


def _rings_meet(a, b):
    return any(_segment_kind(p, q, r, s) != "none"
               for p, q in _edges(a) for r, s in _edges(b))


@dataclass(frozen=True)
class Region:
    outer: Ring
    holes: tuple[Ring, ...] = ()

    def __post_init__(self):
        outer = _ring(self.outer)
        holes = tuple(_ring(h) for h in _sequence(self.holes))
        for h in holes:
            if _rings_meet(outer, h) or _location(outer, h[0]) != "interior":
                raise ValueError("hole must be strictly inside outer ring")
        for i, a in enumerate(holes):
            for b in holes[i + 1:]:
                if (_rings_meet(a, b) or _location(a, b[0]) != "exterior"
                        or _location(b, a[0]) != "exterior"):
                    raise ValueError("holes must have disjoint closures")
        object.__setattr__(self, "outer", outer)
        object.__setattr__(self, "holes", holes)

    @property
    def area(self):
        return (abs(_twice_area(self.outer))
                - sum((abs(_twice_area(h)) for h in self.holes), Fraction(0))) / 2

    def locate(self, point):
        point = _point(point)
        result = _location(self.outer, point)
        if result != "interior":
            return result
        for hole in self.holes:
            result = _location(hole, point)
            if result == "boundary":
                return result
            if result == "interior":
                return "exterior"
        return "interior"


# --- Conservation transfer -------------------------------------------------
#
# Overlap area is measured exactly by vertical slab integration. The plane is
# split at every ring vertex and every proper edge/edge crossing, so inside a
# slab the set of crossings of a vertical line with a region's rings is fixed
# and the covered y-length is linear. Evaluating that length once at the slab
# midpoint and multiplying by the exact slab width is therefore exact.
# Holes are odd-even alternations of the same vertical line, so their interiors
# contribute nothing; point and edge contacts never open a positive interval.

def _region_edges(region):
    edges = list(_edges(region.outer))
    for hole in region.holes:
        edges.extend(_edges(hole))
    return edges


def _edge_crossing_x(a, b, c, d):
    """x coordinate of a proper (non-collinear) edge/edge crossing, or None."""
    r = (b[0] - a[0], b[1] - a[1])
    s = (d[0] - c[0], d[1] - c[1])
    rxs = r[0] * s[1] - r[1] * s[0]
    if rxs == 0:
        return None
    qp = (c[0] - a[0], c[1] - a[1])
    t = (qp[0] * s[1] - qp[1] * s[0]) / rxs
    u = (qp[0] * r[1] - qp[1] * r[0]) / rxs
    if not (Fraction(0) < t < 1 and Fraction(0) < u < 1):
        return None
    return a[0] + t * r[0]


def _vertical_intervals(edges, x):
    """Covered y-intervals of one region on a vertical line through x."""
    crossings = []
    for a, b in edges:
        if (a[0] < x < b[0]) or (b[0] < x < a[0]):
            y = a[1] + (x - a[0]) * (b[1] - a[1]) / (b[0] - a[0])
            crossings.append(y)
    crossings.sort()
    return [(crossings[i], crossings[i + 1])
            for i in range(0, len(crossings), 2)]


def _interval_overlap_length(first, second):
    total = Fraction(0)
    i = j = 0
    while i < len(first) and j < len(second):
        lo = max(first[i][0], second[j][0])
        hi = min(first[i][1], second[j][1])
        if hi > lo:
            total += hi - lo
        if first[i][1] < second[j][1]:
            i += 1
        else:
            j += 1
    return total


def _overlap_area(region_a, region_b):
    edges_a = _region_edges(region_a)
    edges_b = _region_edges(region_b)
    xs = set()
    for edges in (edges_a, edges_b):
        for a, b in edges:
            xs.add(a[0])
            xs.add(b[0])
    for a, b in edges_a:
        for c, d in edges_b:
            x = _edge_crossing_x(a, b, c, d)
            if x is not None:
                xs.add(x)
    xs = sorted(xs)
    area = Fraction(0)
    for left, right in zip(xs, xs[1:]):
        width = right - left
        if width == 0:
            continue
        middle = (left + right) / 2
        length = _interval_overlap_length(
            _vertical_intervals(edges_a, middle),
            _vertical_intervals(edges_b, middle))
        area += width * length
    return area


def _disjoint_interiors(region_a, region_b):
    return _overlap_area(region_a, region_b) == 0


def _edge_count(region):
    return len(region.outer) + sum(len(hole) for hole in region.holes)


def _id_list(value):
    if not isinstance(value, list) or not value:
        raise ValueError("selection must be a nonempty list of IDs")
    result = tuple(_identifier(item) for item in value)
    if len(set(result)) != len(result):
        raise ValueError("selection contains duplicate IDs")
    return result


class TransferPlan:
    """Immutable fixed-weight plan; independent of later archive changes."""

    __slots__ = ("_source_ids", "_target_ids", "_source_areas",
                 "_overlaps", "_uncovered")

    def __init__(self, source_ids, target_ids, source_areas, overlaps,
                 uncovered):
        object.__setattr__(self, "_source_ids", tuple(source_ids))
        object.__setattr__(self, "_target_ids", tuple(target_ids))
        object.__setattr__(self, "_source_areas",
                           MappingProxyType(dict(source_areas)))
        object.__setattr__(self, "_overlaps", MappingProxyType(dict(overlaps)))
        object.__setattr__(self, "_uncovered",
                           MappingProxyType(dict(uncovered)))

    @property
    def source_ids(self):
        return self._source_ids

    @property
    def target_ids(self):
        return self._target_ids

    @property
    def source_areas(self):
        return self._source_areas

    @property
    def overlaps(self):
        return self._overlaps

    @property
    def uncovered(self):
        return self._uncovered

    def __setattr__(self, name, value):
        raise AttributeError("TransferPlan is immutable")

    def allocate(self, amounts):
        if not isinstance(amounts, dict):
            raise ValueError("amounts must be a dict of source ID to Fraction")
        if set(amounts) != set(self._source_ids):
            raise ValueError("amounts keys must be exactly the source IDs")
        for value in amounts.values():
            if type(value) is not Fraction or value < 0:
                raise ValueError("each amount must be a nonnegative Fraction")
        areas = self._source_areas
        pairs = {}
        for (source_id, target_id), overlap in self._overlaps.items():
            pairs[(source_id, target_id)] = (
                amounts[source_id] * overlap / areas[source_id])
        remaining = {
            source_id: (amounts[source_id] * self._uncovered[source_id]
                        / areas[source_id])
            for source_id in self._source_ids
        }
        totals = {target_id: Fraction(0) for target_id in self._target_ids}
        for (source_id, target_id), value in pairs.items():
            totals[target_id] += value
        return {"pairs": pairs, "remaining": remaining, "totals": totals}


def _identifier(value):
    if not isinstance(value, str) or not value:
        raise ValueError("region ID must be a nonempty string")
    return value


def _keys(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError("unexpected JSON object fields")


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("nonfinite JSON number: " + value)


def _decode_ring(value):
    if not isinstance(value, list):
        raise ValueError("wire ring must be an array")
    points = []
    for pair in value:
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError("wire point must be a two-element array")
        coords = []
        for text in pair:
            if not isinstance(text, str):
                raise ValueError("wire coordinate must be a canonical rational string")
            try:
                number = Fraction(text)
            except (ValueError, ZeroDivisionError) as exc:
                raise ValueError("invalid rational") from exc
            if str(number) != text:
                raise ValueError("noncanonical rational")
            coords.append(number)
        points.append(tuple(coords))
    return tuple(points)


def _encode_ring(ring):
    return [[str(x), str(y)] for x, y in ring]


class Archive:
    """Independent region IDs; put validates before replacing any stored value."""

    def __init__(self):
        self._regions = {}

    @property
    def ids(self):
        return tuple(sorted(self._regions))

    def put(self, region_id, outer, holes=()):
        region_id = _identifier(region_id)
        candidate = Region(outer, holes)
        self._regions[region_id] = candidate

    def read(self, region_id):
        return self._regions[_identifier(region_id)]

    def transfer_plan(self, source_ids, target_ids):
        sources = _id_list(source_ids)
        targets = _id_list(target_ids)
        source_regions = {region_id: self.read(region_id)
                          for region_id in sources}
        target_regions = {region_id: self.read(region_id)
                          for region_id in targets}
        edge_budget = (sum(_edge_count(r) for r in source_regions.values())
                       + sum(_edge_count(r) for r in target_regions.values()))
        if edge_budget > 120:
            raise ValueError("selected geometry exceeds the 120-edge limit")
        for group in (source_regions, target_regions):
            members = list(group.values())
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    if not _disjoint_interiors(members[i], members[j]):
                        raise ValueError(
                            "regions in one group must have disjoint interiors")
        source_areas = {region_id: source_regions[region_id].area
                        for region_id in sorted(sources)}
        overlaps = {}
        covered = {region_id: Fraction(0) for region_id in sources}
        for source_id in sorted(sources):
            source_region = source_regions[source_id]
            for target_id in sorted(targets):
                overlap = _overlap_area(source_region,
                                        target_regions[target_id])
                if overlap > 0:
                    overlaps[(source_id, target_id)] = overlap
                    covered[source_id] += overlap
        uncovered = {region_id: source_areas[region_id] - covered[region_id]
                     for region_id in sorted(sources)}
        return TransferPlan(tuple(sorted(sources)), tuple(sorted(targets)),
                            source_areas, overlaps, uncovered)

    def export(self, region_ids=None):
        if region_ids is None:
            selected = self.ids
        else:
            selected = tuple(_identifier(x) for x in _sequence(region_ids))
            if len(set(selected)) != len(selected):
                raise ValueError("duplicate selected region ID")
            selected = tuple(sorted(selected))
        records = []
        for region_id in selected:
            region = self.read(region_id)
            records.append({"id": region_id, "outer": _encode_ring(region.outer),
                            "holes": [_encode_ring(h) for h in region.holes]})
        return {"version": 1, "regions": records}

    def dumps(self, region_ids=None):
        return json.dumps(self.export(region_ids), ensure_ascii=True, sort_keys=True,
                          separators=(",", ":")) + "\n"

    @classmethod
    def loads(cls, text):
        if not isinstance(text, str):
            raise ValueError("archive input must be text")
        try:
            data = json.loads(text, object_pairs_hook=_object, parse_constant=_reject_constant)
        except (ValueError, RecursionError) as exc:
            raise ValueError("invalid archive JSON") from exc
        _keys(data, ("version", "regions"))
        if type(data["version"]) is not int or data["version"] != 1:
            raise ValueError("unsupported archive version")
        if not isinstance(data["regions"], list):
            raise ValueError("regions must be an array")
        archive = cls()
        for record in data["regions"]:
            _keys(record, ("id", "outer", "holes"))
            region_id = _identifier(record["id"])
            if region_id in archive._regions:
                raise ValueError("duplicate region ID")
            if not isinstance(record["holes"], list):
                raise ValueError("holes must be an array")
            archive.put(region_id, _decode_ring(record["outer"]),
                        tuple(_decode_ring(h) for h in record["holes"]))
        return archive
