/** Shared, derived mission state for every page, plus a way for a page to steer the 3D scene. */
import { createContext, useContext, useEffect } from 'react';
import type { Derived, SceneMode, StageView } from './derive';

export interface SceneOverride { mode: SceneMode; stages: StageView[]; key: string }
interface MissionCtx { d: Derived; now: number; setScene: (o: SceneOverride | null) => void }

export const Mission = createContext<MissionCtx | null>(null);
export function useMission(): MissionCtx {
  const c = useContext(Mission);
  if (!c) throw new Error('useMission outside the shell');
  return c;
}

/** While mounted, the reactor shows this incident instead of the global state. */
export function useSceneFocus(o: SceneOverride | null) {
  const { setScene } = useMission();
  const sig = o ? `${o.key}:${o.mode}:${o.stages.map((s) => s.state).join(',')}` : '';
  useEffect(() => { setScene(o); }, [sig]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => setScene(null), [setScene]);
}
