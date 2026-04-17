export const automationSeries = Array.from({ length: 30 }).map((_, i) => ({
  date: `2025-01-${(i + 1).toString().padStart(2, '0')}`,
  rate: 60 + Math.random() * 30,
  intake: Math.random() * 10,
  fusion: Math.random() * 10,
  compliance: Math.random() * 10
}));
