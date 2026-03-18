#!/usr/bin/env python3
"""
Immich upload benchmark analyzer.

Usage:
    python analyze.py --upload-log results.jsonl [--fio-result fio.json] [--output-dir ./charts/]
"""

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec


def load_upload_log(path: str) -> list[dict]:
    records = []
    with open(path) as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"Warning: skipping malformed line {lineno}: {e}", file=sys.stderr)
    return records


def percentile_stats(values: list[float]) -> dict:
    a = np.array(values)
    return {
        'count': len(a),
        'mean': float(np.mean(a)),
        'median': float(np.median(a)),
        'p90': float(np.percentile(a, 90)),
        'p95': float(np.percentile(a, 95)),
        'p99': float(np.percentile(a, 99)),
        'min': float(np.min(a)),
        'max': float(np.max(a)),
    }


def print_stats_table(groups: dict[bool, list[dict]]) -> None:
    col_width = 12
    metrics = ['count', 'mean', 'median', 'p90', 'p95', 'p99', 'min', 'max']
    fields = [('duration_ms', 'Duration (ms)'), ('throughput_mbps', 'Throughput (MB/s)')]

    for field, label in fields:
        print(f'\n=== {label} ===')
        header = f"{'Metric':<12}" + ''.join(
            f"{'flush=on' if k else 'flush=off':>{col_width}}"
            for k in sorted(groups.keys(), reverse=True)
        )
        print(header)
        print('-' * len(header))

        stats_by_group = {}
        for flush_on, records in groups.items():
            vals = [r[field] for r in records if field in r]
            if vals:
                stats_by_group[flush_on] = percentile_stats(vals)

        for m in metrics:
            row = f'{m:<12}'
            for k in sorted(groups.keys(), reverse=True):
                s = stats_by_group.get(k)
                if s is None:
                    row += f"{'N/A':>{col_width}}"
                elif m == 'count':
                    row += f"{int(s[m]):>{col_width}}"
                else:
                    row += f"{s[m]:>{col_width}.2f}"
            print(row)


def plot_duration_cdf(groups: dict[bool, list[dict]], output_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    colors = {True: '#1f77b4', False: '#ff7f0e'}
    labels = {True: 'flush=on', False: 'flush=off'}

    for flush_on in sorted(groups.keys(), reverse=True):
        records = groups[flush_on]
        vals = sorted(r['duration_ms'] for r in records if 'duration_ms' in r)
        if not vals:
            continue
        cdf = np.arange(1, len(vals) + 1) / len(vals)
        ax.plot(vals, cdf, label=labels[flush_on], color=colors[flush_on], linewidth=2)

    ax.set_xlabel('Duration (ms)')
    ax.set_ylabel('CDF')
    ax.set_title('Upload Duration CDF')
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    out = output_dir / 'cdf_duration.png'
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f'Saved: {out}')


def plot_throughput_histogram(groups: dict[bool, list[dict]], output_dir: Path) -> None:
    fig, axes = plt.subplots(1, len(groups), figsize=(6 * len(groups), 5), sharey=False)
    if len(groups) == 1:
        axes = [axes]
    colors = {True: '#1f77b4', False: '#ff7f0e'}
    labels = {True: 'flush=on', False: 'flush=off'}

    for ax, flush_on in zip(axes, sorted(groups.keys(), reverse=True)):
        records = groups[flush_on]
        vals = [r['throughput_mbps'] for r in records if 'throughput_mbps' in r]
        if not vals:
            continue
        ax.hist(vals, bins=30, color=colors[flush_on], edgecolor='white', alpha=0.85)
        ax.set_xlabel('Throughput (MB/s)')
        ax.set_ylabel('Count')
        ax.set_title(f'Throughput Histogram — {labels[flush_on]}')
        ax.grid(True, alpha=0.3)

    fig.tight_layout()
    out = output_dir / 'histogram_throughput.png'
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f'Saved: {out}')


def plot_scatter(groups: dict[bool, list[dict]], output_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    colors = {True: '#1f77b4', False: '#ff7f0e'}
    labels = {True: 'flush=on', False: 'flush=off'}

    for flush_on in sorted(groups.keys(), reverse=True):
        records = groups[flush_on]
        sizes = [r['size_bytes'] / 1_048_576 for r in records if 'size_bytes' in r and 'throughput_mbps' in r]
        throughputs = [r['throughput_mbps'] for r in records if 'size_bytes' in r and 'throughput_mbps' in r]
        if not sizes:
            continue
        ax.scatter(sizes, throughputs, label=labels[flush_on], color=colors[flush_on], alpha=0.6, s=20)

    ax.set_xlabel('File size (MB)')
    ax.set_ylabel('Throughput (MB/s)')
    ax.set_title('Throughput vs File Size')
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    out = output_dir / 'scatter_throughput_vs_size.png'
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f'Saved: {out}')


def plot_timeline(groups: dict[bool, list[dict]], output_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    colors = {True: '#1f77b4', False: '#ff7f0e'}
    labels = {True: 'flush=on', False: 'flush=off'}

    for flush_on in sorted(groups.keys(), reverse=True):
        records = groups[flush_on]
        throughputs = [r['throughput_mbps'] for r in records if 'throughput_mbps' in r]
        if not throughputs:
            continue
        ax.plot(range(len(throughputs)), throughputs, label=labels[flush_on],
                color=colors[flush_on], linewidth=1, alpha=0.8)

    ax.set_xlabel('Upload sequence index')
    ax.set_ylabel('Throughput (MB/s)')
    ax.set_title('Throughput Timeline')
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    out = output_dir / 'timeline_throughput.png'
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f'Saved: {out}')


def load_fio_result(path: str) -> dict | None:
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: could not parse fio result: {e}", file=sys.stderr)
        return None


def print_fio_summary(fio: dict) -> None:
    print('\n=== fio Summary ===')
    jobs = fio.get('jobs', [])
    for job in jobs:
        name = job.get('jobname', 'unknown')
        read = job.get('read', {})
        write = job.get('write', {})

        def bw(section):
            bw_bytes = section.get('bw_bytes', 0)
            return bw_bytes / 1_048_576

        def iops(section):
            return section.get('iops', 0)

        def lat_ns(section):
            return section.get('lat_ns', {})

        print(f'\nJob: {name}')
        if read.get('bw_bytes', 0) > 0:
            lat = lat_ns(read)
            print(f"  Read:  BW={bw(read):.1f} MB/s  IOPS={iops(read):.0f}  "
                  f"lat_mean={lat.get('mean', 0)/1e6:.2f}ms  "
                  f"lat_p99={lat.get('percentile', {}).get('99.000000', 0)/1e6:.2f}ms")
        if write.get('bw_bytes', 0) > 0:
            lat = lat_ns(write)
            print(f"  Write: BW={bw(write):.1f} MB/s  IOPS={iops(write):.0f}  "
                  f"lat_mean={lat.get('mean', 0)/1e6:.2f}ms  "
                  f"lat_p99={lat.get('percentile', {}).get('99.000000', 0)/1e6:.2f}ms")


def plot_fio_panel(fio: dict, groups: dict[bool, list[dict]], output_dir: Path) -> None:
    jobs = fio.get('jobs', [])
    if not jobs:
        return

    fig = plt.figure(figsize=(12, 8))
    gs = gridspec.GridSpec(2, 2, figure=fig)

    # fio bandwidth bar chart (top-left)
    ax_bw = fig.add_subplot(gs[0, 0])
    job_names = [j.get('jobname', f'job{i}') for i, j in enumerate(jobs)]
    read_bw = [j.get('read', {}).get('bw_bytes', 0) / 1_048_576 for j in jobs]
    write_bw = [j.get('write', {}).get('bw_bytes', 0) / 1_048_576 for j in jobs]
    x = np.arange(len(job_names))
    width = 0.35
    ax_bw.bar(x - width / 2, read_bw, width, label='Read', color='#2ca02c')
    ax_bw.bar(x + width / 2, write_bw, width, label='Write', color='#d62728')
    ax_bw.set_xticks(x)
    ax_bw.set_xticklabels(job_names, rotation=15, ha='right')
    ax_bw.set_ylabel('Bandwidth (MB/s)')
    ax_bw.set_title('fio Bandwidth')
    ax_bw.legend()
    ax_bw.grid(True, alpha=0.3, axis='y')

    # fio IOPS bar chart (top-right)
    ax_iops = fig.add_subplot(gs[0, 1])
    read_iops = [j.get('read', {}).get('iops', 0) for j in jobs]
    write_iops = [j.get('write', {}).get('iops', 0) for j in jobs]
    ax_iops.bar(x - width / 2, read_iops, width, label='Read', color='#2ca02c')
    ax_iops.bar(x + width / 2, write_iops, width, label='Write', color='#d62728')
    ax_iops.set_xticks(x)
    ax_iops.set_xticklabels(job_names, rotation=15, ha='right')
    ax_iops.set_ylabel('IOPS')
    ax_iops.set_title('fio IOPS')
    ax_iops.legend()
    ax_iops.grid(True, alpha=0.3, axis='y')

    # Immich throughput timeline (bottom, spanning both columns)
    ax_tl = fig.add_subplot(gs[1, :])
    colors = {True: '#1f77b4', False: '#ff7f0e'}
    labels = {True: 'flush=on', False: 'flush=off'}
    for flush_on in sorted(groups.keys(), reverse=True):
        records = groups[flush_on]
        vals = [r['throughput_mbps'] for r in records if 'throughput_mbps' in r]
        if vals:
            ax_tl.plot(range(len(vals)), vals, label=f'Immich {labels[flush_on]}',
                       color=colors[flush_on], linewidth=1, alpha=0.8)
    ax_tl.set_xlabel('Upload sequence index')
    ax_tl.set_ylabel('Throughput (MB/s)')
    ax_tl.set_title('Immich Upload Throughput (with fio load)')
    ax_tl.legend()
    ax_tl.grid(True, alpha=0.3)

    fig.suptitle('Immich flush benchmark — fio overlay', fontsize=13)
    fig.tight_layout()
    out = output_dir / 'fio_overlay.png'
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f'Saved: {out}')


def main() -> None:
    parser = argparse.ArgumentParser(description='Analyze Immich upload benchmark results.')
    parser.add_argument('--upload-log', required=True, help='Path to JSONL upload benchmark log')
    parser.add_argument('--fio-result', help='Path to fio JSON output (optional)')
    parser.add_argument('--output-dir', default='./charts', help='Directory for PNG charts (default: ./charts)')
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f'Loading upload log: {args.upload_log}')
    records = load_upload_log(args.upload_log)
    if not records:
        print('No records found in upload log.', file=sys.stderr)
        sys.exit(1)
    print(f'Loaded {len(records)} records.')

    # Group by flush_enabled
    groups: dict[bool, list[dict]] = {}
    for r in records:
        key = bool(r.get('flush_enabled', True))
        groups.setdefault(key, []).append(r)

    print(f'Groups: ' + ', '.join(
        f"flush={'on' if k else 'off'} ({len(v)} records)"
        for k, v in sorted(groups.items(), reverse=True)
    ))

    print_stats_table(groups)

    print('\nGenerating charts...')
    plot_duration_cdf(groups, output_dir)
    plot_throughput_histogram(groups, output_dir)
    plot_scatter(groups, output_dir)
    plot_timeline(groups, output_dir)

    if args.fio_result:
        print(f'\nLoading fio result: {args.fio_result}')
        fio = load_fio_result(args.fio_result)
        if fio:
            print_fio_summary(fio)
            plot_fio_panel(fio, groups, output_dir)

    print(f'\nDone. Charts written to: {output_dir}/')


if __name__ == '__main__':
    main()
