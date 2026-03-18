# Immich `flush:true` Upload Benchmark

This directory contains tooling to measure the per-file write latency and throughput
impact of `flush: true` (fsync after write) introduced in commit `b108f0430`.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `IMMICH_FLUSH_WRITES` | `true` | Set to `false` to disable fsync on upload writes |
| `IMMICH_UPLOAD_BENCHMARK` | _(unset)_ | Set to a file path to enable JSONL benchmark logging |

When `IMMICH_UPLOAD_BENCHMARK` is unset, **no instrumentation overhead is added** to uploads.

## Step-by-step: A/B benchmark

### 1. Run with flush enabled (baseline)

```bash
export IMMICH_FLUSH_WRITES=true
export IMMICH_UPLOAD_BENCHMARK=/tmp/bench.jsonl

# Start (or restart) the Immich server, then upload your test dataset.
# Each uploaded file appends one JSON line to /tmp/bench.jsonl.
```

### 2. Run with flush disabled

```bash
export IMMICH_FLUSH_WRITES=false
# Keep IMMICH_UPLOAD_BENCHMARK pointing to the same file — records include
# flush_enabled:false so the two runs can be combined and compared.

# Restart the server, then upload the same dataset again.
```

### 3. Analyze results

```bash
pip install matplotlib numpy

python misc/benchmark/analyze.py \
  --upload-log /tmp/bench.jsonl \
  --output-dir ./charts/
```

This prints a stats table (mean, median, p90, p95, p99 for both duration and throughput)
and writes four PNG charts to `./charts/`.

## Running a concurrent fio workload

Simulate background disk pressure during uploads to understand real-world impact:

```bash
# Random-write workload (simulates PostgreSQL/database I/O)
fio --name=db-sim \
    --rw=randwrite \
    --bs=4k \
    --size=1g \
    --numjobs=4 \
    --iodepth=32 \
    --runtime=300 \
    --time_based \
    --output-format=json \
    --output=fio_db.json \
    --filename=/tmp/fio-db-test &

# Sequential-read workload (simulates media streaming, e.g. Plex)
fio --name=stream-sim \
    --rw=read \
    --bs=128k \
    --size=4g \
    --numjobs=2 \
    --runtime=300 \
    --time_based \
    --output-format=json \
    --output=fio_stream.json \
    --filename=/tmp/fio-stream-test &

# Then run your Immich uploads while fio is running in the background.
# After uploads complete, kill fio:
kill %1 %2
```

### Overlay fio results in the analysis

```bash
python misc/benchmark/analyze.py \
  --upload-log /tmp/bench.jsonl \
  --fio-result fio_db.json \
  --output-dir ./charts/
```

## Recommended test datasets

| Dataset | Why |
|---|---|
| ~100 small JPEGs (< 1 MB each) | Highlights per-fsync syscall overhead as a fraction of total time |
| ~20 large RAW files (20–50 MB each) | Shows whether flush cost is amortized by larger writes |
| ~5 video files (100–500 MB each) | Stresses sequential throughput; fsync cost should be negligible |
| Mixed (all of the above combined) | Most representative of real library imports |

## Output charts

| File | Description |
|---|---|
| `cdf_duration.png` | Cumulative distribution of per-file write duration |
| `histogram_throughput.png` | Distribution of per-file throughput |
| `scatter_throughput_vs_size.png` | Throughput as a function of file size |
| `timeline_throughput.png` | Throughput over the upload sequence |
| `fio_overlay.png` | fio bandwidth/IOPS + Immich timeline (only with `--fio-result`) |

## What to look for

- **Duration p99 difference**: large gap between flush=on and flush=off at p99 suggests
  fsync is causing occasional stalls (common on spinning disk or heavily loaded storage).
- **Throughput degradation on small files**: if flush=on throughput for files < 1 MB is
  significantly lower, fsync latency is dominating write time.
- **Negligible difference on large files**: expected — fsync cost amortizes over large I/O.
- **fio overlay**: if throughput drops when fio is running but recovers without fio, the
  storage is I/O-constrained and fsync contention is a real concern in production.
