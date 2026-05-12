export type PathPoint = [number, number, number];

const _TRAITS: Record<string, Record<string, number>> = {
  precise: {
    tremor_amp: 0.55,
    click_offset_sigma: 0.65,
    fitts_noise: 0.75,
    hover_delay: 0.85,
    scroll_speed: 0.90,
    keystroke_sigma: 0.80,
  },
  normal: {
    tremor_amp: 1.00,
    click_offset_sigma: 1.00,
    fitts_noise: 1.00,
    hover_delay: 1.00,
    scroll_speed: 1.00,
    keystroke_sigma: 1.00,
  },
  sloppy: {
    tremor_amp: 1.55,
    click_offset_sigma: 1.35,
    fitts_noise: 1.30,
    hover_delay: 1.20,
    scroll_speed: 1.15,
    keystroke_sigma: 1.25,
  },
};

let currentPersonality: { trait: string, mult: Record<string, number> } | undefined = undefined;

export function setPersonality(trait?: string, seed?: number): { trait: string, mult: Record<string, number> } {
  if (!trait) {
    const r = Math.random();
    if (r < 0.25) trait = "precise";
    else if (r < 0.75) trait = "normal";
    else trait = "sloppy";
  }
  if (!_TRAITS[trait]) trait = "normal";
  currentPersonality = { trait, mult: (_TRAITS[trait] || _TRAITS["normal"]) as Record<string, number> };
  return currentPersonality as any;
}

export function getPersonality() {
  if (!currentPersonality) {
    return { trait: "normal", mult: _TRAITS["normal"] };
  }
  return currentPersonality as any;
}

function _mult(key: string): number {
  if (!currentPersonality) return 1.0;
  return currentPersonality.mult[key] ?? 1.0;
}

function randomGauss(mu: number = 0, sigma: number = 1): number {
  let u = 0, v = 0;
  while (u === 0) u = Math.random();
  while (v === 0) v = Math.random();
  const num = Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v);
  return num * sigma + mu;
}

function randomExpovariate(lambda: number): number {
  return -Math.log(1.0 - Math.random()) / lambda;
}

function randomBetavariate(alpha: number, beta: number): number {
    const a = randomGauss(alpha, 1);
    const b = randomGauss(beta, 1);
    return Math.abs(a) / (Math.abs(a) + Math.abs(b));
}

function randomLognormvariate(mu: number, sigma: number): number {
    return Math.exp(randomGauss(mu, sigma));
}

export function fittsTime(distance: number, width: number = 50.0): number {
  if (distance < 1) return 0.05;
  const a = 0.05;
  const b = 0.145;
  let mt = a + b * Math.log2(distance / width + 1);
  mt *= randomGauss(1.0, 0.15 * _mult("fitts_noise"));
  return Math.max(0.05, mt);
}

const _SQRT_2PI = Math.sqrt(2.0 * Math.PI);

function _lognormalPdf(t: number, t0: number, mu: number, sigma: number): number {
  const dt = t - t0;
  if (dt <= 1e-10) return 0.0;
  const logDt = Math.log(dt);
  return Math.exp(-Math.pow(logDt - mu, 2) / (2.0 * sigma * sigma)) / (sigma * _SQRT_2PI * dt);
}

function _generateSubmovements(arcLength: number, duration: number, distance: number) {
  let n = 2;
  if (distance < 100) n = Math.random() < 0.55 ? 1 : 2;
  else if (distance < 300) n = Math.random() < 0.6 ? 2 : 3;
  else if (distance < 500) n = Math.random() < 0.35 ? 2 : (Math.random() < 0.75 ? 3 : 4);
  else n = Math.random() < 0.35 ? 3 : (Math.random() < 0.75 ? 4 : 5);

  const subs: [number, number, number, number][] = [];
  let t0 = 0.003 + Math.random() * 0.009;
  let remainingD = arcLength;

  for (let i = 0; i < n; i++) {
    const sigma = Math.max(0.18, Math.min(0.55, randomGauss(0.30, 0.08)));
    let d = 0;
    let peakTime = 0;
    if (i === 0) {
      const dFrac = Math.min(0.98, Math.max(0.70, randomBetavariate(8, 2)));
      d = arcLength * dFrac;
      remainingD -= d;
      const peakFrac = Math.max(0.25, Math.min(0.50, randomGauss(0.37, 0.04)));
      peakTime = Math.max(0.008, (duration - t0) * peakFrac);
    } else {
      const spacing = Math.max(0.015, randomExpovariate(1.0 / 0.08));
      t0 += spacing;
      if (t0 >= duration * 0.95) t0 = duration * (0.6 + Math.random() * 0.25);
      if (i < n - 1) {
        const frac = 0.3 + Math.random() * 0.4;
        d = Math.max(0.5, remainingD * frac);
        remainingD -= d;
      } else {
        d = Math.max(0.5, remainingD);
        remainingD = 0;
      }
      const remainingTime = Math.max(0.02, duration * 1.05 - t0);
      const peakFrac = Math.max(0.20, Math.min(0.55, randomGauss(0.35, 0.06)));
      peakTime = Math.max(0.005, remainingTime * peakFrac);
    }
    const mu = Math.log(peakTime) + sigma * sigma;
    subs.push([t0, mu, sigma, d]);
  }
  return subs;
}

function _velocityAt(t: number, submovements: [number, number, number, number][]): number {
  let v = 0.0;
  for (const [t0, mu, sigma, d] of submovements) {
    v += d * _lognormalPdf(t, t0, mu, sigma);
  }
  return v;
}

function _bezierCubic(t: number, p0: number[], p1: number[], p2: number[], p3: number[]) {
  const u = 1 - t;
  return [
    u * u * u * p0[0]! + 3 * u * u * t * p1[0]! + 3 * u * t * t * p2[0]! + t * t * t * p3[0]!,
    u * u * u * p0[1]! + 3 * u * u * t * p1[1]! + 3 * u * t * t * p2[1]! + t * t * t * p3[1]!
  ];
}

function _controlPoints(sx: number, sy: number, ex: number, ey: number): [number[], number[]] {
  const dx = ex - sx, dy = ey - sy;
  const dist = Math.sqrt(dx * dx + dy * dy) || 1.0;
  const px = -dy / dist, py = dx / dist;
  const side = Math.random() < 0.5 ? -1 : 1;
  const spread = dist * (0.15 + Math.random() * 0.25);
  const off1 = side * (spread * 0.3 + Math.random() * spread * 0.5);
  const c1 = [sx + dx * 0.25 + px * off1, sy + dy * 0.25 + py * off1];
  const off2 = side * (spread * 0.2 + Math.random() * spread * 0.4);
  const c2 = [sx + dx * 0.75 + px * off2, sy + dy * 0.75 + py * off2];
  return [c1, c2];
}

function _buildCurve(sx: number, sy: number, ex: number, ey: number, nSamples = 500) {
  const [c1, c2] = _controlPoints(sx, sy, ex, ey) as [number[], number[]];
  const p0 = [sx, sy], p3 = [ex, ey];
  const points: number[][] = [];
  const arcLengths: number[] = [0.0];
  let prevX = sx, prevY = sy;
  for (let i = 0; i <= nSamples; i++) {
    const frac = i / nSamples;
    const [x, y] = _bezierCubic(frac, p0, c1, c2, p3);
    points.push([x, y]);
    if (i > 0) {
      const d = Math.sqrt(Math.pow((x as number) - prevX, 2) + Math.pow((y as number) - prevY, 2));
      arcLengths.push(arcLengths[arcLengths.length - 1] + d);
    }
    prevX = x; prevY = y;
  }
  return { points, arcLengths };
}

function _lookupPosition(curvePoints: number[][], arcLengths: number[], targetS: number) {
  const total = arcLengths[arcLengths.length - 1];
  targetS = Math.max(0.0, Math.min(total, targetS));
  let lo = 0, hi = arcLengths.length - 1;
  while (lo < hi - 1) {
    const mid = Math.floor((lo + hi) / 2);
    if (arcLengths[mid]! <= targetS) lo = mid;
    else hi = mid;
  }
  if (arcLengths[hi] === arcLengths[lo]) return curvePoints[lo];
  const frac = (targetS - arcLengths[lo]!) / (arcLengths[hi]! - arcLengths[lo]!);
  const x = curvePoints[lo]![0]! + frac * (curvePoints[hi]![0]! - curvePoints[lo]![0]!);
  const y = curvePoints[lo]![1]! + frac * (curvePoints[hi]![1]! - curvePoints[lo]![1]!);
  return [x, y];
}

function _tremor(t: number, freq: number, amplitude: number) {
  const tx = amplitude * Math.sin(2 * Math.PI * freq * t) + amplitude * 0.3 * Math.sin(2 * Math.PI * (freq * 1.37) * t + 1.2);
  const ty = amplitude * Math.sin(2 * Math.PI * (freq * 0.93) * t + 0.7) + amplitude * 0.25 * Math.sin(2 * Math.PI * (freq * 1.51) * t + 2.1);
  return [tx, ty];
}

function _splitIntoSubmovements(sx: number, sy: number, ex: number, ey: number) {
  const dist = Math.sqrt(Math.pow(ex - sx, 2) + Math.pow(ey - sy, 2));
  if (dist < 300) return [[ex, ey]];
  let n = dist < 600 ? 2 : (Math.random() < 0.5 ? 2 : 3);
  const dx = ex - sx, dy = ey - sy;
  const px = -dy / dist, py = dx / dist;
  const waypoints = [];
  for (let i = 1; i < n; i++) {
    let frac = i / n + randomGauss(0, 0.05);
    frac = Math.max(0.2, Math.min(0.8, frac));
    const wander = randomGauss(0, dist * 0.03);
    const wx = sx + dx * frac + px * wander;
    const wy = sy + dy * frac + py * wander;
    waypoints.push([wx, wy]);
  }
  waypoints.push([ex, ey]);
  return waypoints;
}

function _overshootTarget(sx: number, sy: number, ex: number, ey: number) {
  const dx = ex - sx, dy = ey - sy;
  const dist = Math.sqrt(dx * dx + dy * dy) || 1.0;
  const ux = dx / dist, uy = dy / dist;
  const px = -uy, py = ux;
  const forward = 5 + Math.random() * 15;
  const lateral = randomGauss(0, 4);
  return [ex + ux * forward + px * lateral, ey + uy * forward + py * lateral];
}

function _generateSegment(sx: number, sy: number, ex: number, ey: number, targetWidth: number = 50.0): PathPoint[] {
  const dist = Math.sqrt(Math.pow(ex - sx, 2) + Math.pow(ey - sy, 2));
  if (dist < 1) return [[ex, ey, 0.01]];
  const { points: curvePts, arcLengths: arcLens } = _buildCurve(sx, sy, ex, ey);
  const totalArc = arcLens[arcLens.length - 1];
  const duration = fittsTime(dist, targetWidth);
  const subs = _generateSubmovements(totalArc, duration, dist);
  const sampleRate = 55 + Math.random() * 20;
  const nPoints = Math.max(8, Math.floor(duration * sampleRate));
  const intDt = 0.002;
  const intSteps = Math.max(1, Math.floor(duration * 1.12 / intDt));
  let cumS = 0.0;
  const sAtT = [[0.0, 0.0]];
  let prevV = _velocityAt(0.0, subs);
  for (let step = 1; step <= intSteps; step++) {
    const t = step * intDt;
    const v = _velocityAt(t, subs);
    cumS += 0.5 * (prevV + v) * intDt;
    sAtT.push([t, cumS]);
    prevV = v;
  }
  const actualTotal = sAtT[sAtT.length - 1]![1];
  const scale = (actualTotal as number) > 1e-6 ? (totalArc as number) / (actualTotal as number) : 1.0;
  const outputDt = duration / nPoints;
  const tremorFreq = 8 + Math.random() * 4;
  const tremorAmp = (0.3 + Math.random() * 0.9) * _mult("tremor_amp");
  const points: PathPoint[] = [];
  let sIdx = 0;
  for (let i = 0; i <= nPoints; i++) {
    const tTarget = i * outputDt;
    while (sIdx < sAtT.length - 1 && sAtT[sIdx + 1]![0]! <= tTarget) sIdx++;
    let sNow = 0;
    if (sIdx < sAtT.length - 1) {
      const [tLo, sLo] = sAtT[sIdx] as [number, number];
      const [tHi, sHi] = sAtT[sIdx + 1] as [number, number];
      const dtSpan = tHi - tLo;
      const frac = dtSpan > 1e-10 ? (tTarget - tLo) / dtSpan : 0.0;
      sNow = (sLo + frac * (sHi - sLo)) * scale;
    } else {
      sNow = totalArc;
    }
    let [x, y] = _lookupPosition(curvePts, arcLens, sNow);
    const progress = totalArc > 0 ? Math.min(1.0, sNow / totalArc) : 1.0;
    const tScale = Math.max(0.1, 1.0 - progress * 0.7);
    const [tx, ty] = _tremor(tTarget, tremorFreq, tremorAmp * tScale);
    x += tx; y += ty;
    const delay = i === 0 ? 0.003 + Math.random() * 0.005 : Math.max(0.004, outputDt + randomGauss(0, outputDt * 0.08));
    points.push([x, y, delay]);
  }
  if (points.length > 0) {
    const last = points[points.length - 1];
    points[points.length - 1] = [ex, ey, last![2]];
  }
  return points;
}

export function generatePath(sx: number, sy: number, ex: number, ey: number, targetWidth: number = 50.0): PathPoint[] {
  const dist = Math.sqrt(Math.pow(ex - sx, 2) + Math.pow(ey - sy, 2));
  if (dist < 2) return [[ex, ey, 0.01]];
  const doOvershoot = dist > 350 && Math.random() < Math.min(0.5, dist / 1200);
  if (doOvershoot) {
    const [ox, oy] = _overshootTarget(sx, sy, ex, ey);
    const path = _generateSegment(sx, sy, ox, oy, targetWidth);
    if (path.length > 0) {
      const last = path[path.length - 1];
      path[path.length - 1] = [last![0]!, last![1]!, 0.08 + Math.random() * 0.07];
    }
    const correction = _generateSegment(ox, oy, ex, ey, targetWidth * 2);
    return path.concat(correction);
  }
  const waypoints = _splitIntoSubmovements(sx, sy, ex, ey);
  let path: PathPoint[] = [];
  let cx = sx, cy = sy;
  for (let i = 0; i < waypoints.length; i++) {
    const [wx, wy] = waypoints[i];
    const segment = _generateSegment(cx, cy, wx, wy, targetWidth);
    if (i < waypoints.length - 1 && segment.length > 0) {
      const last = segment[segment.length - 1];
      segment[segment.length - 1] = [last![0]!, last![1]!, 0.08 + Math.random() * 0.12];
    }
    path = path.concat(segment);
    if (segment.length > 0) {
      cx = segment[segment.length - 1]![0]!;
      cy = segment[segment.length - 1]![1]!;
    }
  }
  return path;
}

export function hoverDelay(): number {
  const base = randomLognormvariate(Math.log(0.18), 0.4);
  return Math.max(0.06, base * _mult("hover_delay"));
}

export function scrollSequence(totalDelta: number): [number, number][] {
  if (Math.abs(totalDelta) < 10) return [];
  const sign = totalDelta > 0 ? 1 : -1;
  let remaining = Math.abs(totalDelta);
  const events: [number, number][] = [];
  const pauseScale = 1.0 / _mult("scroll_speed");
  while (remaining > 5) {
    const burstLen = 3 + Math.floor(Math.random() * 6);
    const burstBase = 60 + Math.random() * 80;
    for (let j = 0; j < burstLen; j++) {
      if (remaining <= 5) break;
      const progress = j / Math.max(1, burstLen - 1);
      const intensity = Math.sin(progress * Math.PI) * 0.6 + 0.4;
      const delta = Math.min(remaining, burstBase * intensity * (0.7 + Math.random() * 0.6));
      remaining -= delta;
      events.push([delta * sign, 0.015 + Math.random() * 0.045]);
    }
    if (remaining > 5) {
      const decayEvents = 2 + Math.floor(Math.random() * 3);
      let decayDelta = events.length > 0 ? events[events.length - 1]![0] : burstBase * sign * 0.5;
      for (let k = 0; k < decayEvents; k++) {
        decayDelta *= (0.4 + Math.random() * 0.3);
        if (Math.abs(decayDelta) < 5) break;
        remaining -= Math.abs(decayDelta);
        events.push([decayDelta, 0.03 + Math.random() * 0.05]);
      }
    }
    if (remaining > 5) {
      events.push([0, (0.2 + Math.random() * 1.8) * pauseScale]);
    }
  }
  if (events.length > 5 && Math.random() < 0.05) {
    const insertAt = Math.floor(events.length / 2) + Math.floor(Math.random() * (events.length - Math.floor(events.length / 2)));
    const revDelta = -sign * (20 + Math.random() * 40);
    events.splice(insertAt, 0, [revDelta, 0.04 + Math.random() * 0.06]);
  }
  return events;
}

const _FAST_DIGRAPHS = new Set([
  "th", "he", "in", "er", "an", "re", "on", "at", "en", "nd",
  "ti", "es", "or", "te", "of", "ed", "is", "it", "al", "ar",
  "st", "to", "nt", "ng", "se", "ha", "as", "ou", "io", "le",
  "ve", "co", "me", "de", "hi", "ri", "ro", "ic", "ne", "ea",
  "ra", "ce", "li", "ch", "ll", "be", "ma", "si", "om", "ur",
  "ão", "qu", "os", "as", "em", "do", "da", "mo", "ss", "rr",
]);

const _SLOW_DIGRAPHS = new Set(["qz", "zx", "xj", "jq", "vq", "kw", "fq", "pq", "jx", "wq"]);

export function keystrokeDelay(char: string, prevChar: string = ""): number {
  let baseMu = Math.log(0.15);
  let baseSigma = 0.38 * _mult("keystroke_sigma");
  if (prevChar) {
    const digraph = (prevChar + char).toLowerCase();
    if (_FAST_DIGRAPHS.has(digraph)) {
      baseMu = Math.log(0.10);
    } else if (_SLOW_DIGRAPHS.has(digraph)) {
      baseMu = Math.log(0.22);
      baseSigma = 0.45;
    } else if (prevChar === " " && char.match(/[a-z]/i)) {
      baseMu = Math.log(0.18);
    } else if (char === " ") {
      baseMu = Math.log(0.17);
    } else if (!prevChar.match(/[a-z]/i) && char.match(/[a-z]/i)) {
      baseMu = Math.log(0.20);
    }
  }
  const delay = randomLognormvariate(baseMu, baseSigma);
  return Math.max(0.04, Math.min(0.8, delay));
}

export function typingSequence(text: string): [string, number][] {
  if (!text) return [];
  const out: [string, number][] = [];
  let prev = "";
  for (const ch of text) {
    let d = keystrokeDelay(ch, prev);
    if (".,!?;:".includes(prev) && ch === " " && Math.random() < 0.3) {
      d += 0.15 + Math.random() * 0.35;
    }
    out.push([ch, d]);
    prev = ch;
  }
  return out;
}
