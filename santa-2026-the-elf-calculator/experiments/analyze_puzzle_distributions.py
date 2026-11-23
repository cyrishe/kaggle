#!/usr/bin/env python3
"""Summarize puzzle target growth and starting-value distributions."""
import argparse
import collections
import csv
import json
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def quantile(values, fraction):
    ordered = sorted(values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def distribution(values):
    values = list(values)
    if not values:
        return {}
    return {'min': min(values), 'p25': quantile(values, .25),
            'median': statistics.median(values), 'p75': quantile(values, .75),
            'p90': quantile(values, .90), 'p95': quantile(values, .95),
            'max': max(values), 'mean': statistics.mean(values)}


def analyze(source, prefix):
    with source.open(newline='', encoding='utf-8') as stream:
        puzzles = list(csv.DictReader(stream))
    records = []
    adjacent_records = []
    all_starts, all_targets, all_growth = [], [], []
    unique_start_count = collections.Counter()
    digit_count = collections.Counter()
    puzzle_start_digits = collections.Counter()
    start_presence = collections.Counter()
    adjacent_exceed = collections.Counter()
    for puzzle in puzzles:
        starts = json.loads(puzzle['starting_values'])
        targets = sorted(json.loads(puzzle['targets']))
        if not starts or not targets or min(starts) <= 0 or min(targets) <= 0:
            raise ValueError(f"Invalid positive input in {puzzle['id']}")
        growth = [(b - a) / a for a, b in zip(targets, targets[1:])]
        for index, (a, b, rate) in enumerate(zip(targets, targets[1:], growth), 1):
            adjacent_records.append({'id': puzzle['id'], 'pair_index': index,
                                     'lower_target': a, 'upper_target': b,
                                     'difference': b - a, 'growth_ratio': rate,
                                     'growth_percent': rate * 100})
        all_starts.extend(starts)
        all_targets.extend(targets)
        all_growth.extend(growth)
        unique_start_count.update(starts)
        digit_count.update(len(str(x)) for x in starts)
        puzzle_start_digits.update({len(str(x)) for x in starts})
        start_presence.update(set(starts))
        for threshold in (0.01, 0.1, 1, 9, 99):
            adjacent_exceed[str(threshold)] += sum(x >= threshold for x in growth)
        first_target, last_target = targets[0], targets[-1]
        rec = {
            'id': puzzle['id'], 'family': puzzle.get('family', ''),
            'design_tier': puzzle.get('design_tier', ''),
            'start_count': len(starts), 'starting_values': json.dumps(starts, separators=(',', ':')),
            'start_min': min(starts), 'start_max': max(starts),
            'start_median': statistics.median(starts),
            'target_count': len(targets), 'target_min': first_target, 'target_max': last_target,
            'target_max_min_ratio': last_target / first_target,
            'target_span_orders_of_magnitude': math.log10(last_target / first_target),
            'target_min_over_start_max': first_target / max(starts),
            'adjacent_pairs': len(growth),
            'adjacent_growth_min': min(growth) if growth else '',
            'adjacent_growth_median': statistics.median(growth) if growth else '',
            'adjacent_growth_mean': statistics.mean(growth) if growth else '',
            'adjacent_growth_max': max(growth) if growth else '',
            'adjacent_growth_p90': quantile(growth, .90) if growth else '',
            'adjacent_growth_ge_100pct_count': sum(x >= 1 for x in growth),
        }
        records.append(rec)
    output = ROOT / 'experiments' / f'{prefix}_puzzle_distributions.csv'
    with output.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)
    adjacent_file = ROOT / 'experiments' / f'{prefix}_adjacent_growth.csv'
    with adjacent_file.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=['id', 'pair_index', 'lower_target',
                                'upper_target', 'difference', 'growth_ratio', 'growth_percent'])
        writer.writeheader()
        writer.writerows(adjacent_records)
    rows_with_pairs = [r for r in records if r['adjacent_pairs']]
    summary = {
        'dataset': prefix, 'puzzles': len(records), 'start_values_count': len(all_starts),
        'target_values_count': len(all_targets), 'adjacent_pairs_count': len(all_growth),
        'puzzle_start_count_distribution': dict(sorted(collections.Counter(r['start_count'] for r in records).items())),
        'puzzle_target_count_distribution': dict(sorted(collections.Counter(r['target_count'] for r in records).items())),
        'start_digit_counts_by_value': dict(sorted(digit_count.items())),
        'start_digit_puzzle_presence': dict(sorted(puzzle_start_digits.items())),
        'start_most_common_values': unique_start_count.most_common(20),
        'start_values_distribution': distribution(all_starts),
        'start_unique_count': len(unique_start_count),
        'start_value_1_to_34_count': sum(1 <= x <= 34 for x in all_starts),
        'puzzles_all_starts_at_most_34': sum(r['start_max'] <= 34 for r in records),
        'puzzles_with_one': start_presence[1],
        'target_values_distribution': distribution(all_targets),
        'target_max_min_ratio_distribution': distribution(r['target_max_min_ratio'] for r in records),
        'target_span_orders_distribution': distribution(r['target_span_orders_of_magnitude'] for r in records),
        'target_min_over_start_max_distribution': distribution(r['target_min_over_start_max'] for r in records),
        'puzzles_min_target_greater_than_max_start': sum(r['target_min'] > r['start_max'] for r in records),
        'pooled_adjacent_growth_distribution': distribution(all_growth),
        'per_puzzle_adjacent_growth_median_distribution': distribution(r['adjacent_growth_median'] for r in rows_with_pairs),
        'per_puzzle_adjacent_growth_mean_distribution': distribution(r['adjacent_growth_mean'] for r in rows_with_pairs),
        'puzzles_with_adjacent_pairs': len(rows_with_pairs),
        'puzzles_with_max_min_ratio_ge_10': sum(r['target_max_min_ratio'] >= 10 for r in records),
        'puzzles_with_max_min_ratio_ge_1000': sum(r['target_max_min_ratio'] >= 1000 for r in records),
        'pooled_adjacent_growth_at_least_counts': dict(adjacent_exceed),
        'puzzles_all_adjacent_growth_below_100pct': sum(r['adjacent_growth_max'] < 1 for r in rows_with_pairs),
        'per_puzzle_file': str(output.relative_to(ROOT)),
        'adjacent_file': str(adjacent_file.relative_to(ROOT)),
    }
    (ROOT / 'experiments' / f'{prefix}_distribution_summary.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', choices=['scored', 'practice', 'both'], default='both')
    args = parser.parse_args()
    names = ['scored', 'practice'] if args.dataset == 'both' else [args.dataset]
    for name in names:
        path = ROOT / 'data' / ('puzzles.csv' if name == 'scored' else 'practice_puzzles.csv')
        print(json.dumps(analyze(path, name), ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
