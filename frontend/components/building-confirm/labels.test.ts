import { describe, expect, it } from 'vitest';
import { floorFromUnit } from './labels';

describe('floorFromUnit', () => {
  it.each([
    ['4층 401호', '4층'],
    ['지하1층', '지하 1층'],
    ['B1층', '지하 1층'],
    ['지1층', '지하 1층'],
    ['1.5층', '해당 층'],
    ['401호', '해당 층'],
    ['', '해당 층'],
  ])('%s -> %s', (input, expected) => {
    expect(floorFromUnit(input)).toBe(expected);
  });
});
