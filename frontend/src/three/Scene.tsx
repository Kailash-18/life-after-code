import { PerformanceMonitor, Stars } from '@react-three/drei';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Bloom, ChromaticAberration, EffectComposer, Vignette } from '@react-three/postprocessing';
import { BlendFunction } from 'postprocessing';
import { Component, useMemo, useRef, useState, type ReactNode } from 'react';
import * as THREE from 'three';
import { bus } from '../state/bus';
import type { SceneMode, StageState, StageView } from '../state/derive';
import { MODE_COLOR } from '../state/derive';
import { coreFragment, coreVertex } from './shaders';

interface Params { color: string; color2: string; agitation: number; speed: number; chaos: number; fracture: number; aberration: number; scan: number }

const P: Record<SceneMode, Params> = {
  connecting: { color: MODE_COLOR.connecting, color2: '#1b1f5c', agitation: 0.066, speed: 0.09, chaos: 0.0225, fracture: 0.0, aberration: 0.00015, scan: 0 },
  offline: { color: MODE_COLOR.offline, color2: '#14161a', agitation: 0.022, speed: 0.024, chaos: 0.0, fracture: 0.0, aberration: 0.0001, scan: 0 },
  healthy: { color: MODE_COLOR.healthy, color2: '#1440ff', agitation: 0.088, speed: 0.132, chaos: 0.0, fracture: 0.0, aberration: 0.00015, scan: 0 },
  canary: { color: MODE_COLOR.canary, color2: '#ff5a1f', agitation: 0.165, speed: 0.204, chaos: 0.036, fracture: 0.0, aberration: 0.00022, scan: 0 },
  degraded: { color: MODE_COLOR.degraded, color2: '#ff2e63', agitation: 0.3025, speed: 0.36, chaos: 0.1575, fracture: 0.1, aberration: 0.0005, scan: 0 },
  breach: { color: MODE_COLOR.breach, color2: '#ff0040', agitation: 0.55, speed: 0.75, chaos: 0.45, fracture: 0.5, aberration: 0.0012, scan: 0 },
  contained: { color: MODE_COLOR.contained, color2: '#ff2e63', agitation: 0.231, speed: 0.24, chaos: 0.1125, fracture: 0.21, aberration: 0.0004, scan: 0 },
  investigating: { color: MODE_COLOR.investigating, color2: '#3a1cff', agitation: 0.187, speed: 0.27, chaos: 0.045, fracture: 0.11, aberration: 0.0003, scan: 1 },
  verifying: { color: MODE_COLOR.verifying, color2: '#7b3cff', agitation: 0.132, speed: 0.36, chaos: 0.018, fracture: 0.04, aberration: 0.00022, scan: 0.4 },
  redeploying: { color: MODE_COLOR.redeploying, color2: '#00a3ff', agitation: 0.11, speed: 0.3, chaos: 0.009, fracture: 0.01, aberration: 0.0002, scan: 0 },
  recovered: { color: MODE_COLOR.recovered, color2: '#00ffd0', agitation: 0.055, speed: 0.18, chaos: 0.0, fracture: 0.0, aberration: 0.00017, scan: 0 },
  failed: { color: MODE_COLOR.failed, color2: '#5a0018', agitation: 0.385, speed: 0.18, chaos: 0.27, fracture: 0.375, aberration: 0.001, scan: 0 },
};

const STAGE_COLOR: Record<StageState, string> = {
  waiting: '#222a33', active: '#ffc23d', sourced: '#e8f6ff', unsourced: '#7d8a90', advisory: '#a77bff',
  failed: '#ff2e63', blocked: '#3a1420', confirmed: '#2bff88',
};

/** Smoothly chases the target params of the current mode. */
function useLive(mode: SceneMode) {
  const live = useRef({ ...P[mode], c: new THREE.Color(P[mode].color), c2: new THREE.Color(P[mode].color2) });
  const target = P[mode];
  const tc = useMemo(() => new THREE.Color(target.color), [target.color]);
  const tc2 = useMemo(() => new THREE.Color(target.color2), [target.color2]);
  useFrame((_, dt) => {
    const k = 1 - Math.exp(-dt * 2.2);
    const l = live.current;
    l.agitation += (target.agitation - l.agitation) * k;
    l.speed += (target.speed - l.speed) * k;
    l.chaos += (target.chaos - l.chaos) * k;
    l.fracture += (target.fracture - l.fracture) * (1 - Math.exp(-dt * (target.fracture > l.fracture ? 7 : 1.2)));
    l.aberration += (target.aberration - l.aberration) * k;
    l.scan += (target.scan - l.scan) * k;
    l.c.lerp(tc, k); l.c2.lerp(tc2, k);
    bus.kick *= Math.exp(-dt * 3.2);
  });
  return live;
}

type Live = ReturnType<typeof useLive>;

function Core({ live }: { live: Live }) {
  const mat = useRef<THREE.ShaderMaterial>(null);
  const grp = useRef<THREE.Group>(null);
  const uniforms = useMemo(() => ({
    uTime: { value: 0 }, uAgitation: { value: 0.2 }, uKick: { value: 0 },
    uColor: { value: new THREE.Color() }, uColor2: { value: new THREE.Color() },
  }), []);
  useFrame((s, dt) => {
    const l = live.current;
    uniforms.uTime.value += dt * (0.6 + l.speed);
    uniforms.uAgitation.value = l.agitation;
    uniforms.uKick.value = bus.kick;
    uniforms.uColor.value.copy(l.c);
    uniforms.uColor2.value.copy(l.c2);
    if (grp.current) {
      grp.current.rotation.y += dt * (0.12 + l.speed * 0.4);
      grp.current.rotation.x = Math.sin(s.clock.elapsedTime * 0.3) * 0.15;
      const sc = 1 + bus.kick * 0.03 + Math.sin(s.clock.elapsedTime * (1.2 + l.agitation * 6)) * 0.015 * (1 + l.agitation * 3);
      grp.current.scale.setScalar(sc);
    }
  });
  return (
    <group ref={grp}>
      <mesh>
        <icosahedronGeometry args={[1.25, 96]} />
        <shaderMaterial ref={mat} uniforms={uniforms} vertexShader={coreVertex} fragmentShader={coreFragment} />
      </mesh>
      <Shell live={live} />
    </group>
  );
}

function Shell({ live }: { live: Live }) {
  const a = useRef<THREE.LineSegments>(null);
  const b = useRef<THREE.LineSegments>(null);
  const geoA = useMemo(() => new THREE.EdgesGeometry(new THREE.IcosahedronGeometry(1.75, 1)), []);
  const geoB = useMemo(() => new THREE.EdgesGeometry(new THREE.OctahedronGeometry(2.05, 0)), []);
  useFrame((_, dt) => {
    const l = live.current;
    if (a.current) {
      a.current.rotation.y -= dt * (0.2 + l.speed * 0.6);
      a.current.rotation.z += dt * 0.07;
      (a.current.material as THREE.LineBasicMaterial).color.copy(l.c);
      const s = 1 + l.fracture * 0.35 + bus.kick * 0.12;
      a.current.scale.setScalar(s);
    }
    if (b.current) {
      b.current.rotation.x += dt * (0.1 + l.speed * 0.3);
      b.current.rotation.y += dt * 0.05;
      (b.current.material as THREE.LineBasicMaterial).color.copy(l.c2).lerp(l.c, 0.5);
      b.current.scale.setScalar(1 + l.fracture * 0.6);
    }
  });
  return (
    <>
      <lineSegments ref={a} geometry={geoA}><lineBasicMaterial transparent opacity={0.55} toneMapped={false} /></lineSegments>
      <lineSegments ref={b} geometry={geoB}><lineBasicMaterial transparent opacity={0.22} toneMapped={false} /></lineSegments>
    </>
  );
}

const ringVertex = /* glsl */ `
uniform float uTime; uniform float uChaos; uniform float uKick; uniform float uSize;
attribute float aSeed; attribute float aRadius;
varying float vAlpha;
void main(){
  float ang = position.x + uTime * (0.6 + aSeed * 0.5) / aRadius;
  float wob = sin(uTime * 3.0 + aSeed * 40.0) * uChaos;
  float r = aRadius + position.y + wob * 0.9 + uKick * 0.5 * aSeed;
  vec3 p = vec3(cos(ang) * r, position.z + wob * 0.6 * sin(aSeed * 90.0), sin(ang) * r);
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  gl_PointSize = uSize * (0.6 + aSeed) * (12.0 / -mv.z);
  vAlpha = 0.35 + 0.65 * aSeed;
  gl_Position = projectionMatrix * mv;
}`;
const ringFragment = /* glsl */ `
uniform vec3 uColor; varying float vAlpha;
void main(){
  float d = length(gl_PointCoord - 0.5);
  float a = smoothstep(0.5, 0.0, d) * vAlpha;
  gl_FragColor = vec4(uColor * 1.6, a);
}`;

function Rings({ live, count }: { live: Live; count: number }) {
  const rings = useMemo(() => [
    { r: 2.35, tilt: [1.2, 0, 0.2], spread: 0.08, n: count },
    { r: 3.05, tilt: [1.45, 0.4, -0.3], spread: 0.14, n: Math.round(count * 1.2) },
    { r: 4.4, tilt: [1.0, -0.6, 0.5], spread: 0.35, n: Math.round(count * 0.9) },
  ].map((cfg) => {
    const g = new THREE.BufferGeometry();
    const pos = new Float32Array(cfg.n * 3), seed = new Float32Array(cfg.n), rad = new Float32Array(cfg.n);
    for (let i = 0; i < cfg.n; i++) {
      pos[i * 3] = Math.random() * Math.PI * 2;
      pos[i * 3 + 1] = (Math.random() - 0.5) * cfg.spread * 2;
      pos[i * 3 + 2] = (Math.random() - 0.5) * cfg.spread;
      seed[i] = Math.random(); rad[i] = cfg.r;
    }
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    g.setAttribute('aSeed', new THREE.BufferAttribute(seed, 1));
    g.setAttribute('aRadius', new THREE.BufferAttribute(rad, 1));
    const u = { uTime: { value: 0 }, uChaos: { value: 0 }, uKick: { value: 0 }, uSize: { value: 2.4 }, uColor: { value: new THREE.Color() } };
    return { cfg, g, u };
  }), [count]);
  const grp = useRef<THREE.Group>(null);
  useFrame((_, dt) => {
    const l = live.current;
    rings.forEach(({ u }, i) => {
      u.uTime.value += dt * (0.5 + l.speed * 2.2) * (i % 2 ? -1 : 1);
      u.uChaos.value = l.chaos;
      u.uKick.value = bus.kick;
      u.uColor.value.copy(i === 1 ? l.c2.clone().lerp(l.c, 0.6) : l.c);
    });
    if (grp.current) grp.current.rotation.y += dt * 0.04;
  });
  return (
    <group ref={grp}>
      {rings.map(({ cfg, g, u }, i) => (
        <points key={i} geometry={g} rotation={cfg.tilt as [number, number, number]}>
          <shaderMaterial uniforms={u} vertexShader={ringVertex} fragmentShader={ringFragment} transparent depthWrite={false} blending={THREE.AdditiveBlending} />
        </points>
      ))}
    </group>
  );
}

function Shards({ live, count = 140 }: { live: Live; count?: number }) {
  const mesh = useRef<THREE.InstancedMesh>(null);
  const data = useMemo(() => Array.from({ length: count }, () => {
    const dir = new THREE.Vector3().randomDirection();
    return { dir, dist: 1.6 + Math.random() * 3.6, spin: new THREE.Vector3(Math.random(), Math.random(), Math.random()).multiplyScalar(3), size: 0.04 + Math.random() * 0.11, phase: Math.random() * 10 };
  }), [count]);
  const m = useMemo(() => new THREE.Object3D(), []);
  const mat = useRef<THREE.MeshBasicMaterial>(null);
  useFrame((s) => {
    const l = live.current;
    const t = s.clock.elapsedTime;
    const f = l.fracture;
    if (!mesh.current) return;
    data.forEach((d, i) => {
      const r = 1.15 + f * d.dist + Math.sin(t * 2 + d.phase) * 0.05 * f;
      m.position.copy(d.dir).multiplyScalar(r);
      m.rotation.set(d.spin.x * t, d.spin.y * t, d.spin.z * t);
      m.scale.setScalar(f > 0.01 ? d.size * Math.min(1, f * 3) : 0.0001);
      m.updateMatrix();
      mesh.current!.setMatrixAt(i, m.matrix);
    });
    mesh.current.instanceMatrix.needsUpdate = true;
    mat.current?.color.copy(l.c).multiplyScalar(1.4);
  });
  return (
    <instancedMesh ref={mesh} args={[undefined, undefined, count]}>
      <tetrahedronGeometry args={[1, 0]} />
      <meshBasicMaterial ref={mat} toneMapped={false} />
    </instancedMesh>
  );
}

function Gates({ stages }: { stages: StageView[] }) {
  const grp = useRef<THREE.Group>(null);
  const mats = useRef<(THREE.MeshBasicMaterial | null)[]>([]);
  const cols = useMemo(() => stages.map((s) => new THREE.Color(STAGE_COLOR[s.state])), [stages]);
  useFrame((s, dt) => {
    if (grp.current) grp.current.rotation.y += dt * 0.08;
    const t = s.clock.elapsedTime;
    stages.forEach((st, i) => {
      const mm = mats.current[i];
      if (!mm) return;
      mm.color.lerp(cols[i], 1 - Math.exp(-dt * 4));
      const pulse = st.state === 'active' ? 0.6 + 0.4 * Math.sin(t * 6) : st.state === 'advisory' ? 0.75 + 0.25 * Math.sin(t * 2 + i) : 1;
      mm.opacity = st.state === 'waiting' ? 0.35 : st.state === 'blocked' ? 0.5 : pulse;
    });
  });
  return (
    <group ref={grp} rotation={[0.42, 0, 0.08]}>
      {stages.map((st, i) => {
        const a = (i / stages.length) * Math.PI * 2;
        return (
          <mesh key={st.stage} position={[Math.cos(a) * 3.05, 0, Math.sin(a) * 3.05]} rotation={[0, -a, 0]}>
            <torusGeometry args={[0.2, st.state === 'confirmed' ? 0.05 : 0.032, 12, 48]} />
            <meshBasicMaterial ref={(el) => { mats.current[i] = el; }} transparent toneMapped={false} />
          </mesh>
        );
      })}
    </group>
  );
}

function Satellite({ pct, danger }: { pct: number; danger: boolean }) {
  const ref = useRef<THREE.Mesh>(null);
  const target = pct > 0 ? 0.12 + (pct / 100) * 0.55 : 0.0001;
  useFrame((s, dt) => {
    if (!ref.current) return;
    const t = s.clock.elapsedTime * 0.5;
    ref.current.position.set(Math.cos(t) * 2.6, Math.sin(t * 1.3) * 0.5, Math.sin(t) * 2.6);
    const cur = ref.current.scale.x;
    ref.current.scale.setScalar(cur + (target - cur) * (1 - Math.exp(-dt * 3)));
    (ref.current.material as THREE.MeshBasicMaterial).color.set(danger ? '#ff2e63' : '#ffc23d');
  });
  return (
    <mesh ref={ref} scale={0.0001}>
      <icosahedronGeometry args={[1, 3]} />
      <meshBasicMaterial toneMapped={false} wireframe />
    </mesh>
  );
}

function Scanner({ live }: { live: Live }) {
  const ref = useRef<THREE.Mesh>(null);
  useFrame((s) => {
    if (!ref.current) return;
    const l = live.current;
    const y = Math.sin(s.clock.elapsedTime * 1.6) * 1.35;
    const r = Math.sqrt(Math.max(0.05, 1.9 * 1.9 - y * y));
    ref.current.position.y = y;
    ref.current.scale.set(r, r, 1);
    (ref.current.material as THREE.MeshBasicMaterial).opacity = l.scan * 0.85;
    ref.current.visible = l.scan > 0.02;
  });
  return (
    <mesh ref={ref} rotation={[Math.PI / 2, 0, 0]}>
      <ringGeometry args={[0.96, 1, 96]} />
      <meshBasicMaterial color="#c9a8ff" transparent side={THREE.DoubleSide} toneMapped={false} />
    </mesh>
  );
}

function Shockwaves({ live }: { live: Live }) {
  const refs = useRef<(THREE.Mesh | null)[]>([]);
  useFrame(() => {
    const now = performance.now();
    for (let i = 0; i < 6; i++) {
      const m = refs.current[i];
      const w = bus.waves[i];
      if (!m) continue;
      if (!w) { m.visible = false; continue; }
      const age = (now - w.t) / 1100;
      if (age > 1) { m.visible = false; continue; }
      m.visible = true;
      const s = 1.2 + age * (5 + w.s * 3);
      m.scale.set(s, s, s);
      const mat = m.material as THREE.MeshBasicMaterial;
      mat.opacity = (1 - age) * (1 - age) * Math.min(1, w.s);
      mat.color.copy(live.current.c);
    }
  });
  return (
    <>
      {Array.from({ length: 6 }, (_, i) => (
        <mesh key={i} ref={(el) => { refs.current[i] = el; }} visible={false} rotation={[Math.PI / 2.4, 0, 0]}>
          <ringGeometry args={[0.98, 1, 128]} />
          <meshBasicMaterial transparent side={THREE.DoubleSide} toneMapped={false} />
        </mesh>
      ))}
    </>
  );
}

/** Gentle camera drift with the page, plus a little pointer parallax. */
const PATH: { at: number; pos: [number, number, number]; look: [number, number, number] }[] = [
  { at: 0.0, pos: [0, 0.2, 7.4], look: [0, 0, 0] },
  { at: 0.5, pos: [-0.5, 0.8, 8.2], look: [0, 0, 0] },
  { at: 1.0, pos: [0, 0.3, 9.4], look: [0, 0, 0] },
];
const ease = (x: number) => x * x * (3 - 2 * x);

function Rig({ offsetX, narrow }: { live?: Live; offsetX: number; narrow: boolean }) {
  const { camera } = useThree();
  const look = useRef(new THREE.Vector3());
  const pos = useRef(new THREE.Vector3(0, 0.2, 9));
  useFrame((s, dt) => {
    const p = Math.min(1, Math.max(0, bus.scroll));
    let i = 0;
    while (i < PATH.length - 2 && p > PATH[i + 1].at) i++;
    const a = PATH[i], b = PATH[i + 1];
    const f = ease(Math.min(1, Math.max(0, (p - a.at) / (b.at - a.at))));
    const tp = new THREE.Vector3(...a.pos).lerp(new THREE.Vector3(...b.pos), f);
    const tl = new THREE.Vector3(...a.look).lerp(new THREE.Vector3(...b.look), f);
    if (narrow) { tp.multiplyScalar(1.7); tp.y -= 2.4; tl.y -= 2.4; }
    tp.x += bus.pointer.x * 0.12 - offsetX;
    tp.y += bus.pointer.y * 0.08;
    const k = 1 - Math.exp(-dt * 1.6);
    pos.current.lerp(tp, k);
    look.current.lerp(tl.add(new THREE.Vector3(-offsetX, 0, 0)), k);
    camera.position.copy(pos.current);
    camera.lookAt(look.current);
    void s;
  });
  return null;
}

function Fx({ live, enabled }: { live: Live; enabled: boolean }) {
  const off = useMemo(() => new THREE.Vector2(0.0006, 0.0006), []);
  useFrame(() => {
    const a = live.current.aberration + bus.kick * 0.0008;
    off.set(a, a * 0.6);
  });
  if (!enabled) return null;
  return (
    <EffectComposer multisampling={0}>
      <Bloom mipmapBlur intensity={0.85} luminanceThreshold={0.08} luminanceSmoothing={0.25} radius={0.75} />
      <ChromaticAberration offset={off} blendFunction={BlendFunction.NORMAL} radialModulation={false} modulationOffset={0} />
      <Vignette darkness={0.75} offset={0.25} />
    </EffectComposer>
  );
}

function World({ mode, stages, candidatePct, offsetX, narrow, quality }: SceneProps & { quality: number }) {
  const live = useLive(mode);
  return (
    <>
      <color attach="background" args={['#030406']} />
      <fog attach="fog" args={['#030406', 9, 26]} />
      <Stars radius={60} depth={40} count={quality > 0.6 ? 5000 : 2000} factor={3.2} saturation={0} fade speed={0.6} />
      <Core live={live} />
      <Rings live={live} count={quality > 0.6 ? 1600 : 700} />
      <Shards live={live} count={quality > 0.6 ? 160 : 70} />
      <Gates stages={stages} />
      <Satellite pct={candidatePct} danger={mode === 'breach' || mode === 'degraded'} />
      <Scanner live={live} />
      <Shockwaves live={live} />
      <Rig live={live} offsetX={offsetX} narrow={narrow} />
      <Fx live={live} enabled={quality > 0.45} />
    </>
  );
}

export interface SceneProps { mode: SceneMode; stages: StageView[]; candidatePct: number; offsetX: number; narrow: boolean }

class Boundary extends Component<{ children: ReactNode; fallback: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? this.props.fallback : this.props.children; }
}

function webglAvailable() {
  try {
    const c = document.createElement('canvas');
    return !!(c.getContext('webgl2') || c.getContext('webgl'));
  } catch { return false; }
}

export function Scene(props: SceneProps) {
  const [quality, setQuality] = useState(1);
  const [ok] = useState(webglAvailable);
  const fallback = <div className="scene-fallback" style={{ ['--glow' as string]: MODE_COLOR[props.mode] }} aria-hidden="true" />;
  if (!ok) return fallback;
  return (
    <Boundary fallback={fallback}>
      <Canvas
        className="scene"
        dpr={[1, quality > 0.6 ? 1.75 : 1]}
        camera={{ fov: 42, near: 0.1, far: 120, position: [0, 0.2, 9] }}
        gl={{ antialias: false, powerPreference: 'high-performance', alpha: false }}
        aria-hidden="true"
      >
        <PerformanceMonitor onDecline={() => setQuality((q) => Math.max(0.3, q - 0.35))} onIncline={() => setQuality((q) => Math.min(1, q + 0.2))} />
        <World {...props} quality={quality} />
      </Canvas>
    </Boundary>
  );
}
