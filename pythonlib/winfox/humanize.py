"""Human-like mouse movement and typing helpers for Winfox."""

import contextvars
import math
import random
from typing import List, Optional, Tuple

PathPoint = Tuple[float, float, float]

_personality: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar(
    "humanize_personality", default=None
)

_TRAITS = {
    "precise": {
        "tremor_amp": 0.55,
        "click_offset_sigma": 0.65,
        "fitts_noise": 0.75,
        "hover_delay": 0.85,
        "scroll_speed": 0.90,
        "keystroke_sigma": 0.80,
    },
    "normal": {
        "tremor_amp": 1.00,
        "click_offset_sigma": 1.00,
        "fitts_noise": 1.00,
        "hover_delay": 1.00,
        "scroll_speed": 1.00,
        "keystroke_sigma": 1.00,
    },
    "sloppy": {
        "tremor_amp": 1.55,
        "click_offset_sigma": 1.35,
        "fitts_noise": 1.30,
        "hover_delay": 1.20,
        "scroll_speed": 1.15,
        "keystroke_sigma": 1.25,
    },
}


def set_personality(trait: Optional[str] = None, seed: Optional[int] = None) -> dict:
    if trait is None:
        rng = random.Random(seed) if seed is not None else random
        r = rng.random()
        if r < 0.25:
            trait = "precise"
        elif r < 0.75:
            trait = "normal"
        else:
            trait = "sloppy"
    if trait not in _TRAITS:
        trait = "normal"
    state = {"trait": trait, "mult": _TRAITS[trait]}
    _personality.set(state)
    return state


def get_personality() -> dict:
    state = _personality.get()
    if state is None:
        return {"trait": "normal", "mult": _TRAITS["normal"]}
    return state


def _mult(key: str) -> float:
    state = _personality.get()
    if state is None:
        return 1.0
    return state["mult"].get(key, 1.0)


def fitts_time(distance: float, width: float = 50.0) -> float:
    if distance < 1:
        return 0.05
    a = 0.05
    b = 0.145
    mt = a + b * math.log2(distance / width + 1)
    mt *= random.gauss(1.0, 0.15 * _mult("fitts_noise"))
    return max(0.05, mt)


def _lognormal_pdf(t: float, t0: float, mu: float, sigma: float) -> float:
    dt = t - t0
    if dt <= 1e-10:
        return 0.0
    log_dt = math.log(dt)
    return math.exp(-(log_dt - mu) ** 2 / (2.0 * sigma * sigma)) / (
        sigma * _SQRT_2PI * dt
    )


_SQRT_2PI = math.sqrt(2.0 * math.pi)


def _generate_submovements(arc_length: float, duration: float, distance: float) -> list:
    if distance < 100:
        n = random.choices([1, 2], weights=[0.55, 0.45])[0]
    elif distance < 300:
        n = random.choices([2, 3], weights=[0.6, 0.4])[0]
    elif distance < 500:
        n = random.choices([2, 3, 4], weights=[0.35, 0.40, 0.25])[0]
    else:
        n = random.choices([3, 4, 5], weights=[0.35, 0.40, 0.25])[0]

    subs = []
    t0 = random.uniform(0.003, 0.012)
    remaining_d = arc_length

    for i in range(n):
        sigma = max(0.18, min(0.55, random.gauss(0.30, 0.08)))
        if i == 0:
            d_frac = min(0.98, max(0.70, random.betavariate(8, 2)))
            d = arc_length * d_frac
            remaining_d -= d
            peak_frac = max(0.25, min(0.50, random.gauss(0.37, 0.04)))
            peak_time = max(0.008, (duration - t0) * peak_frac)
        else:
            spacing = max(0.015, random.expovariate(1.0 / 0.08))
            t0 += spacing
            if t0 >= duration * 0.95:
                t0 = duration * random.uniform(0.6, 0.85)
            if i < n - 1:
                frac = random.uniform(0.3, 0.7)
                d = max(0.5, remaining_d * frac)
                remaining_d -= d
            else:
                d = max(0.5, remaining_d)
                remaining_d = 0
            remaining_time = max(0.02, duration * 1.05 - t0)
            peak_frac = max(0.20, min(0.55, random.gauss(0.35, 0.06)))
            peak_time = max(0.005, remaining_time * peak_frac)
        mu = math.log(peak_time) + sigma * sigma
        subs.append((t0, mu, sigma, d))
    return subs


def _velocity_at(t: float, submovements: list) -> float:
    v = 0.0
    for t0, mu, sigma, d in submovements:
        v += d * _lognormal_pdf(t, t0, mu, sigma)
    return v


def _bezier_cubic(t: float, p0, p1, p2, p3):
    u = 1 - t
    return (
        u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0],
        u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1],
    )


def _control_points(sx, sy, ex, ey):
    dx, dy = ex - sx, ey - sy
    dist = math.sqrt(dx * dx + dy * dy) or 1.0
    px, py = -dy / dist, dx / dist
    side = random.choice([-1, 1])
    spread = dist * random.uniform(0.15, 0.40)
    off1 = side * random.uniform(spread * 0.3, spread * 0.8)
    c1 = (sx + dx * 0.25 + px * off1, sy + dy * 0.25 + py * off1)
    off2 = side * random.uniform(spread * 0.2, spread * 0.6)
    c2 = (sx + dx * 0.75 + px * off2, sy + dy * 0.75 + py * off2)
    return c1, c2


def _build_curve(sx, sy, ex, ey, n_samples=500):
    c1, c2 = _control_points(sx, sy, ex, ey)
    p0, p3 = (sx, sy), (ex, ey)
    points = []
    arc_lengths = [0.0]
    prev_x, prev_y = sx, sy
    for i in range(n_samples + 1):
        frac = i / n_samples
        x, y = _bezier_cubic(frac, p0, c1, c2, p3)
        points.append((x, y))
        if i > 0:
            d = math.sqrt((x - prev_x) ** 2 + (y - prev_y) ** 2)
            arc_lengths.append(arc_lengths[-1] + d)
        prev_x, prev_y = x, y
    return points, arc_lengths


def _lookup_position(curve_points, arc_lengths, target_s):
    total = arc_lengths[-1]
    target_s = max(0.0, min(total, target_s))
    lo, hi = 0, len(arc_lengths) - 1
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if arc_lengths[mid] <= target_s:
            lo = mid
        else:
            hi = mid
    if arc_lengths[hi] == arc_lengths[lo]:
        return curve_points[lo]
    frac = (target_s - arc_lengths[lo]) / (arc_lengths[hi] - arc_lengths[lo])
    x = curve_points[lo][0] + frac * (curve_points[hi][0] - curve_points[lo][0])
    y = curve_points[lo][1] + frac * (curve_points[hi][1] - curve_points[lo][1])
    return (x, y)


def _tremor(t: float, freq: float, amplitude: float) -> Tuple[float, float]:
    tx = amplitude * math.sin(2 * math.pi * freq * t) + amplitude * 0.3 * math.sin(
        2 * math.pi * (freq * 1.37) * t + 1.2
    )
    ty = amplitude * math.sin(2 * math.pi * (freq * 0.93) * t + 0.7) + amplitude * 0.25 * math.sin(
        2 * math.pi * (freq * 1.51) * t + 2.1
    )
    return tx, ty


def _split_into_submovements(sx, sy, ex, ey) -> List[Tuple[float, float]]:
    dist = math.sqrt((ex - sx) ** 2 + (ey - sy) ** 2)
    if dist < 300:
        return [(ex, ey)]
    elif dist < 600:
        n = 2
    else:
        n = random.choice([2, 3])
    dx, dy = ex - sx, ey - sy
    px, py = -dy / dist, dx / dist
    waypoints = []
    for i in range(1, n):
        frac = i / n + random.gauss(0, 0.05)
        frac = max(0.2, min(0.8, frac))
        wander = random.gauss(0, dist * 0.03)
        wx = sx + dx * frac + px * wander
        wy = sy + dy * frac + py * wander
        waypoints.append((wx, wy))
    waypoints.append((ex, ey))
    return waypoints


def _overshoot_target(sx, sy, ex, ey) -> Tuple[float, float]:
    dx, dy = ex - sx, ey - sy
    dist = math.sqrt(dx * dx + dy * dy) or 1.0
    ux, uy = dx / dist, dy / dist
    px, py = -uy, ux
    forward = random.uniform(5, 20)
    lateral = random.gauss(0, 4)
    return (ex + ux * forward + px * lateral, ey + uy * forward + py * lateral)


def _generate_segment(sx: float, sy: float, ex: float, ey: float, target_width: float = 50.0) -> List[PathPoint]:
    dist = math.sqrt((ex - sx) ** 2 + (ey - sy) ** 2)
    if dist < 1:
        return [(ex, ey, 0.01)]
    curve_pts, arc_lens = _build_curve(sx, sy, ex, ey)
    total_arc = arc_lens[-1]
    duration = fitts_time(dist, target_width)
    subs = _generate_submovements(total_arc, duration, dist)
    sample_rate = random.uniform(55, 75)
    n_points = max(8, int(duration * sample_rate))
    int_dt = 0.002
    int_steps = max(1, int(duration * 1.12 / int_dt))
    cum_s = 0.0
    s_at_t = [(0.0, 0.0)]
    prev_v = _velocity_at(0.0, subs)
    for step in range(1, int_steps + 1):
        t = step * int_dt
        v = _velocity_at(t, subs)
        cum_s += 0.5 * (prev_v + v) * int_dt
        s_at_t.append((t, cum_s))
        prev_v = v
    actual_total = s_at_t[-1][1]
    scale = total_arc / actual_total if actual_total > 1e-6 else 1.0
    output_dt = duration / n_points
    tremor_freq = random.uniform(8, 12)
    tremor_amp = random.uniform(0.3, 1.2) * _mult("tremor_amp")
    points = []
    s_idx = 0
    for i in range(n_points + 1):
        t_target = i * output_dt
        while s_idx < len(s_at_t) - 1 and s_at_t[s_idx + 1][0] <= t_target:
            s_idx += 1
        if s_idx < len(s_at_t) - 1:
            t_lo, s_lo = s_at_t[s_idx]
            t_hi, s_hi = s_at_t[s_idx + 1]
            dt_span = t_hi - t_lo
            frac = (t_target - t_lo) / dt_span if dt_span > 1e-10 else 0.0
            s_now = (s_lo + frac * (s_hi - s_lo)) * scale
        else:
            s_now = total_arc
        x, y = _lookup_position(curve_pts, arc_lens, s_now)
        progress = min(1.0, s_now / total_arc) if total_arc > 0 else 1.0
        t_scale = max(0.1, 1.0 - progress * 0.7)
        tx, ty = _tremor(t_target, tremor_freq, tremor_amp * t_scale)
        x += tx
        y += ty
        if i == 0:
            delay = random.uniform(0.003, 0.008)
        else:
            delay = max(0.004, output_dt + random.gauss(0, output_dt * 0.08))
        points.append((x, y, delay))
    if points:
        _, _, last_d = points[-1]
        points[-1] = (ex, ey, last_d)
    return points


def generate_path(sx: float, sy: float, ex: float, ey: float, target_width: float = 50.0) -> List[PathPoint]:
    dist = math.sqrt((ex - sx) ** 2 + (ey - sy) ** 2)
    if dist < 2:
        return [(ex, ey, 0.01)]
    do_overshoot = dist > 350 and random.random() < min(0.5, dist / 1200)
    if do_overshoot:
        ox, oy = _overshoot_target(sx, sy, ex, ey)
        path = _generate_segment(sx, sy, ox, oy, target_width)
        if path:
            lx, ly, _ = path[-1]
            path[-1] = (lx, ly, random.uniform(0.08, 0.15))
        correction = _generate_segment(ox, oy, ex, ey, target_width * 2)
        path.extend(correction)
        return path
    waypoints = _split_into_submovements(sx, sy, ex, ey)
    path = []
    cx, cy = sx, sy
    for i, (wx, wy) in enumerate(waypoints):
        segment = _generate_segment(cx, cy, wx, wy, target_width)
        if i < len(waypoints) - 1 and segment:
            lx, ly, _ = segment[-1]
            segment[-1] = (lx, ly, random.uniform(0.08, 0.20))
        path.extend(segment)
        if segment:
            cx, cy = segment[-1][0], segment[-1][1]
    return path


def hover_delay() -> float:
    base = random.lognormvariate(math.log(0.18), 0.4)
    return max(0.06, base * _mult("hover_delay"))


def scroll_sequence(total_delta: float) -> List[Tuple[float, float]]:
    if abs(total_delta) < 10:
        return []
    sign = 1 if total_delta > 0 else -1
    remaining = abs(total_delta)
    events: List[Tuple[float, float]] = []
    pause_scale = 1.0 / _mult("scroll_speed")
    while remaining > 5:
        burst_len = random.randint(3, 8)
        burst_base = random.uniform(60, 140)
        for j in range(burst_len):
            if remaining <= 5:
                break
            progress = j / max(1, burst_len - 1)
            intensity = math.sin(progress * math.pi) * 0.6 + 0.4
            delta = min(remaining, burst_base * intensity * random.uniform(0.7, 1.3))
            remaining -= delta
            events.append((delta * sign, random.uniform(0.015, 0.06)))
        if remaining > 5:
            decay_events = random.randint(2, 4)
            decay_delta = events[-1][0] if events else burst_base * sign * 0.5
            for _ in range(decay_events):
                decay_delta *= random.uniform(0.4, 0.7)
                if abs(decay_delta) < 5:
                    break
                remaining -= abs(decay_delta)
                events.append((decay_delta, random.uniform(0.03, 0.08)))
        if remaining > 5:
            events.append((0, random.uniform(0.2, 2.0) * pause_scale))
    if len(events) > 5 and random.random() < 0.05:
        insert_at = random.randint(len(events) // 2, len(events) - 1)
        rev_delta = -sign * random.uniform(20, 60)
        events.insert(insert_at, (rev_delta, random.uniform(0.04, 0.1)))
    return events


_FAST_DIGRAPHS = frozenset([
    "th", "he", "in", "er", "an", "re", "on", "at", "en", "nd",
    "ti", "es", "or", "te", "of", "ed", "is", "it", "al", "ar",
    "st", "to", "nt", "ng", "se", "ha", "as", "ou", "io", "le",
    "ve", "co", "me", "de", "hi", "ri", "ro", "ic", "ne", "ea",
    "ra", "ce", "li", "ch", "ll", "be", "ma", "si", "om", "ur",
    "ão", "qu", "os", "as", "em", "do", "da", "mo", "ss", "rr",
])

_SLOW_DIGRAPHS = frozenset(["qz", "zx", "xj", "jq", "vq", "kw", "fq", "pq", "jx", "wq"])


def keystroke_delay(char: str, prev_char: str = "") -> float:
    base_mu = math.log(0.15)
    base_sigma = 0.38 * _mult("keystroke_sigma")
    if prev_char:
        digraph = (prev_char + char).lower()
        if digraph in _FAST_DIGRAPHS:
            base_mu = math.log(0.10)
        elif digraph in _SLOW_DIGRAPHS:
            base_mu = math.log(0.22)
            base_sigma = 0.45
        elif prev_char == " " and char.isalpha():
            base_mu = math.log(0.18)
        elif char == " ":
            base_mu = math.log(0.17)
        elif not prev_char.isalpha() and char.isalpha():
            base_mu = math.log(0.20)
    delay = random.lognormvariate(base_mu, base_sigma)
    return max(0.04, min(0.8, delay))


def typing_sequence(text: str) -> List[Tuple[str, float]]:
    if not text:
        return []
    out = []
    prev = ""
    for ch in text:
        d = keystroke_delay(ch, prev)
        if prev in ".,!?;:" and ch == " " and random.random() < 0.3:
            d += random.uniform(0.15, 0.5)
        out.append((ch, d))
        prev = ch
    return out
