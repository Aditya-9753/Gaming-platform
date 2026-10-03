/**
 * Lobby catalog shown on Home / Casino. Live games link to their page; the
 * rest are placeholders marked "Coming soon". Names and art are our own.
 */
export interface LobbyGame {
  id: string
  title: string
  /** Small label on top of the tile */
  tag: string
  /** Tailwind gradient classes for the tile background */
  gradient: string
  /** Emoji used as the tile's illustration */
  art: string
  to?: string
  live?: boolean
}

export const LIVE_GAMES: LobbyGame[] = [
  { id: 'aviator', title: 'Aviator', tag: 'CRASH', gradient: 'from-red-600 to-rose-800', art: '✈️', to: '/games/aviator', live: true },
  { id: 'teen_patti', title: 'Teen Patti', tag: 'LIVE CARDS', gradient: 'from-emerald-600 to-green-900', art: '🃏', to: '/games/teen-patti', live: true },
  { id: 'color', title: 'Color Prediction', tag: 'WINGO', gradient: 'from-violet-600 to-fuchsia-800', art: '🎨', to: '/games/color', live: true },
  { id: 'mines', title: 'Mines', tag: 'INSTANT', gradient: 'from-sky-500 to-blue-800', art: '💣', to: '/games/mines', live: true },
]

export interface LobbySection {
  id: string
  title: string
  games: LobbyGame[]
}

export const COMING_SOON_SECTIONS: LobbySection[] = [
  {
    id: 'crash',
    title: 'Crash & Instant',
    games: [
      { id: 'rocket', title: 'Rocket Rush', tag: 'CRASH', gradient: 'from-indigo-600 to-purple-900', art: '🚀' },
      { id: 'chicken', title: 'Chicken Cross', tag: 'INSTANT', gradient: 'from-blue-700 to-slate-900', art: '🐔' },
      { id: 'coinflip', title: 'Coin Flip', tag: 'INSTANT', gradient: 'from-amber-400 to-orange-600', art: '🪙' },
      { id: 'plinko', title: 'Plinko', tag: 'INSTANT', gradient: 'from-pink-500 to-rose-700', art: '🔴' },
      { id: 'dice', title: 'Dice', tag: 'INSTANT', gradient: 'from-teal-500 to-cyan-800', art: '🎲' },
      { id: 'limbo', title: 'Limbo', tag: 'CRASH', gradient: 'from-lime-500 to-green-800', art: '📈' },
    ],
  },
  {
    id: 'cards',
    title: 'Live Casino',
    games: [
      { id: 'andar_bahar', title: 'Andar Bahar', tag: 'CARDS', gradient: 'from-red-700 to-amber-700', art: '🂡' },
      { id: 'dragon_tiger', title: 'Dragon Tiger', tag: 'CARDS', gradient: 'from-orange-600 to-red-900', art: '🐉' },
      { id: 'roulette', title: 'Roulette', tag: 'TABLE', gradient: 'from-green-700 to-emerald-950', art: '🎡' },
      { id: 'blackjack', title: 'Blackjack', tag: 'TABLE', gradient: 'from-slate-600 to-zinc-900', art: '♠️' },
      { id: 'baccarat', title: 'Baccarat', tag: 'TABLE', gradient: 'from-yellow-600 to-amber-900', art: '♦️' },
      { id: 'poker', title: 'Poker', tag: 'CARDS', gradient: 'from-cyan-700 to-blue-950', art: '♣️' },
    ],
  },
  {
    id: 'slots',
    title: 'Slots',
    games: [
      { id: 'gems', title: 'Golden Gems', tag: 'SLOTS', gradient: 'from-orange-500 to-amber-700', art: '💎' },
      { id: 'rabbit', title: 'Lucky Rabbit', tag: 'SLOTS', gradient: 'from-fuchsia-500 to-purple-800', art: '🐰' },
      { id: 'sevens', title: '777 Classic', tag: 'SLOTS', gradient: 'from-yellow-500 to-orange-700', art: '7️⃣' },
      { id: 'fruits', title: 'Fruit Slots', tag: 'SLOTS', gradient: 'from-rose-500 to-pink-800', art: '🍒' },
      { id: 'keno', title: 'Keno', tag: 'LOTTERY', gradient: 'from-blue-500 to-indigo-800', art: '🔢' },
      { id: 'wheel', title: 'Lucky Wheel', tag: 'WHEEL', gradient: 'from-emerald-500 to-teal-800', art: '🎯' },
    ],
  },
  {
    id: 'sports',
    title: 'Sports',
    games: [
      { id: 'cricket', title: 'Cricket', tag: 'SPORTS', gradient: 'from-sky-600 to-blue-900', art: '🏏' },
      { id: 'football', title: 'Football', tag: 'SPORTS', gradient: 'from-green-600 to-emerald-900', art: '⚽' },
      { id: 'kabaddi', title: 'Kabaddi', tag: 'SPORTS', gradient: 'from-orange-600 to-red-800', art: '🤼' },
      { id: 'tennis', title: 'Tennis', tag: 'SPORTS', gradient: 'from-lime-500 to-green-700', art: '🎾' },
    ],
  },
]
