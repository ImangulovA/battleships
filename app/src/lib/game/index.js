// ===========================================================================
// GAME CONFIG — Daily Battleships (Bimaru).
//
// The platform (routing, timer, storage, stats, backend, archive, share) talks
// to your game ONLY through this object and the component's callback contract.
// See ../../../../docs/GAME_CONTRACT.md for the full contract.
// ===========================================================================
import GameComponent from './GameComponent.svelte';
import { dayIndexes as dataDayIndexes, loadDay as dataLoadDay } from './data/days.js';
import { fmtTime } from '../platform/timer.js';

const TIER_EMOJI = {
  beginner: '🟢',
  easy: '🟢',
  medium: '🟡',
  hard: '🟠',
  expert: '🔴',
  master: '🔴'
};

export const GAME = {
  // Storage namespace + backend game key. MUST be unique & stable.
  id: 'battleships',

  title: 'Daily Battleships',
  tagline: 'Find the hidden fleet from the row and column clues. One puzzle a day.',

  // Day 0 = 3 July 2026 (monthIndex 6). Day N = this + N calendar days.
  anchorDate: [2026, 6, 3],

  component: GameComponent,

  dayIndexes: dataDayIndexes,
  loadDay: dataLoadDay,

  // Unscored beyond time + completion: the puzzle has one solution, so the only
  // ladder is how fast you find it. The platform already tracks active time.
  scoreOf() {
    return null;
  },

  // Spoiler-free share line.
  shareLine(result, dayIdx, url) {
    const t = result?.ms != null ? fmtTime(result.ms) : '';
    const tier = result?.tier ? TIER_EMOJI[result.tier] || '' : '';
    const size = result?.size ? ` ${result.size}` : '';
    const badge = result?.won ? '🚢✅' : '🚢';
    return [
      `${GAME.title} #${dayIdx}`,
      `${badge} ${tier}${size}${t ? ' · ' + t : ''}`.trim(),
      url
    ].join('\n');
  }
};
