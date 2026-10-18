/**
 * A tiny mutable bus shared by the DOM and the WebGL scene, read every frame
 * without React re-renders: scroll progress, pointer, and impulse events.
 */
export const bus = {
  /** 0..1 progress through the page */
  scroll: 0,
  /** -1..1, normalised pointer position */
  pointer: { x: 0, y: 0 },
  /** impulse strength, decays in the scene */
  kick: 0,
  /** set when a shockwave should be spawned: [time, strength] */
  waves: [] as { t: number; s: number }[],
  reducedMotion: typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches,
  pulse(strength = 1) {
    this.kick = Math.min(2.2, this.kick + strength);
    this.waves.push({ t: performance.now(), s: strength });
    if (this.waves.length > 6) this.waves.shift();
  },
};
