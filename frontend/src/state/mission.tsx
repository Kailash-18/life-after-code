/** Derived mission state shared by every page. */
import { createContext, useContext } from 'react';
import type { Derived } from './derive';

interface MissionCtx { d: Derived; now: number }

export const Mission = createContext<MissionCtx | null>(null);
export function useMission(): MissionCtx {
  const c = useContext(Mission);
  if (!c) throw new Error('useMission outside the shell');
  return c;
}
