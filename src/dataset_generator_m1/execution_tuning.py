"""Hardware-informed trial selection and evidence-bound local execution choices."""
from collections import defaultdict
import json
import math
import os
from pathlib import Path
import platform
from statistics import median

import psutil
import yaml

from .assets import build_asset_catalog
from .execution import plan_execution, usable_cpu_count
from .identities import digest, generation_contract, software_identity
from .models import ExecutionConfig
from .performance_version import IMPLEMENTATION

GIB = 2**30
MIB = 2**20


def hardware_snapshot():
    """Capacity inputs, never hostname, username, CPU model or a device identifier."""
    logical = os.cpu_count() or 1
    usable = usable_cpu_count()
    memory = psutil.virtual_memory()
    return {'logical_cpus': logical, 'usable_cpus': max(1, min(logical, usable)),
            'total_memory_bytes': memory.total, 'available_memory_bytes': memory.available,
            'system': platform.system(), 'machine': platform.machine()}


def tuning_context(resolved, *, hardware=None, implementation=IMPLEMENTATION):
    hardware = hardware or hardware_snapshot()
    contract = generation_contract(resolved, build_asset_catalog(resolved))
    # A tuning result can serve another run size/seed, but not different content
    # distributions, dimensions, sources, candidate budgets or QA/telemetry costs.
    for key in ('num_images', 'seed'):
        contract['profile']['run'].pop(key, None)
    contract['report'] = resolved.profile.report.model_dump(mode='json')
    contract['telemetry'] = resolved.profile.telemetry.model_dump(mode='json')
    return {'schema_version': 1, 'workload_sha256': digest(contract),
            'performance_implementation': implementation, 'software': software_identity(),
            'environment_class': {key: hardware[key] for key in ('system', 'machine', 'logical_cpus', 'usable_cpus')}
            | {'ram_class_gib': 2**round(math.log2(max(1, hardware['total_memory_bytes']/GIB)))}}


def execution_candidates(resolved, *, hardware=None, workers=None, threads=(1, 2),
                         cpu_budget=None, ram_budget_mb=None, max_workers=32):
    """Return a conservative starting policy and a bounded experimental matrix.

    Explicit worker lists may explore above the advisory RAM forecast; they are
    labelled, never silently treated as safe or launched by this function.
    """
    hardware = hardware or hardware_snapshot()
    cpu = cpu_budget if cpu_budget is not None else resolved.profile.execution.cpu_budget or max(1, hardware['usable_cpus']-1)
    if isinstance(cpu, bool) or not isinstance(cpu, int) or not 1 <= cpu <= hardware['usable_cpus'] or not 1 <= max_workers <= 32:
        raise ValueError('CPU budget must fit usable CPUs; max_workers must be between 1 and 32')
    ram = ram_budget_mb if ram_budget_mb is not None else resolved.profile.execution.ram_budget_mb or max(256, int(hardware['available_memory_bytes']*.6/MIB))
    if isinstance(ram, bool) or not isinstance(ram, int) or ram < 256:
        raise ValueError('RAM planning budget must be an integer of at least 256 MiB')
    base = ExecutionConfig(workers='auto', native_threads=1, cpu_budget=cpu, ram_budget_mb=ram)
    current = resolved.model_copy(update={'profile': resolved.profile.model_copy(update={'execution': base})})
    starting = plan_execution(current, available_ram=hardware['available_memory_bytes'], logical_cpus=hardware['usable_cpus'])
    requested = workers if workers is not None else sorted({1, 2, 3, 4, 6, 8, 12, 16, 24, 32, starting.workers})
    if not threads or any(isinstance(t, bool) or not isinstance(t, int) or t < 1 for t in threads):
        raise ValueError('Native thread trials must be positive integers')
    if any(isinstance(w, bool) or not isinstance(w, int) or not 1 <= w <= 32 for w in requested):
        raise ValueError('Worker trials must be integers between 1 and 32')
    variants, forecasts, excluded = {}, {}, []
    for count in sorted(set(requested)):
        for native in sorted(set(threads)):
            name = f'w{count}-t{native}'
            if count > max_workers or count*native > cpu:
                excluded.append({'variant': name, 'reason': 'CPU budget or worker cap'})
                continue
            policy = base.model_copy(update={'workers': count, 'native_threads': native, 'max_in_flight': count})
            candidate = current.model_copy(update={'profile': current.profile.model_copy(update={'execution': policy})})
            plan = plan_execution(candidate, available_ram=hardware['available_memory_bytes'], logical_cpus=hardware['usable_cpus'])
            if workers is None and plan.estimated_peak_bytes > ram*MIB:
                excluded.append({'variant': name, 'reason': 'Advisory RAM forecast exceeds budget'})
                continue
            variants[name] = policy.model_dump(exclude_none=True)
            forecasts[name] = {'estimated_peak_bytes': plan.estimated_peak_bytes, 'warnings': list(plan.warnings)}
    if not variants:
        raise ValueError('No trial fits the declared limits; inspect the one-worker plan or choose explicit trials')
    return {'schema_version': 1, 'status': 'complete', 'kind': 'execution-candidates',
            'hardware': hardware, 'tuning_context': tuning_context(resolved, hardware=hardware),
            'starting_overrides': {'execution': base.model_dump(exclude_none=True)},
            'starting_plan': starting.as_dict(), 'matrix': {'schema_version': 1, 'variants': variants},
            'forecasts': forecasts, 'excluded': excluded,
            'scope': 'Unmeasured capacity guidance; benchmark candidates under host-memory and swap guards.'}


def _positive(value, label, *, integer=False, zero=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
            or value < 0 or (not zero and value == 0) or (integer and not isinstance(value, int))):
        raise ValueError(f'Invalid {label}')
    return value


def recommend_execution(resolved, study, *, hardware=None, tolerance_percent=5):
    """Choose the smallest safe near-best measured policy, without auto-applying it."""
    hardware = hardware or hardware_snapshot()
    if isinstance(tolerance_percent, bool) or not isinstance(tolerance_percent, (int, float)) or not math.isfinite(tolerance_percent) or not 0 <= tolerance_percent <= 20:
        raise ValueError('Near-best tolerance must be between 0 and 20 percent')
    if study.get('status') != 'complete' or study.get('kind') != 'execution-control-study':
        raise ValueError('A complete guarded execution study is required; aborted studies cannot recommend settings')
    samples = _positive(study.get('samples'), 'sample count', integer=True)
    repeats = _positive(study.get('repeats'), 'repetition count', integer=True)
    if samples < 20 or repeats < 3:
        raise ValueError('Recommendations require at least 20 measured samples and three repetitions per policy')
    if study.get('tuning_context') != tuning_context(resolved, hardware=hardware):
        raise ValueError('Tuning context differs or is missing; rerun for this workload, software and hardware class')
    if not study.get('exact_encoded_images_equal') or not study.get('geometry_annotation_masks_equal'):
        raise ValueError('Exact paired image and annotation evidence is required')
    groups = defaultdict(list)
    signatures, pixels, identities, commits = set(), set(), set(), set()
    for row in study.get('records', []):
        _positive(row.get('repeat'), 'repeat index', integer=True, zero=True)
        if row.get('status') != 'complete' or row.get('inspection') != 'valid' or row.get('accepted') != samples:
            raise ValueError('Every measured pool must be complete and inspected')
        attempts = _positive(row.get('attempts'), 'attempt count', integer=True)
        active = _positive(row.get('active_seconds'), 'active duration')
        rate = _positive(row.get('throughput'), 'accepted throughput')
        if attempts < samples or not math.isclose(rate, samples/active, rel_tol=1e-6):
            raise ValueError('Throughput/attempt counters are inconsistent')
        if row.get('source', {}).get('dirty') is not False:
            raise ValueError('Tuning requires clean immutable measured sources')
        if row.get('tuning_context') != study['tuning_context'] or row.get('software') != study['tuning_context']['software']:
            raise ValueError('A measured row has incompatible tuning context or software')
        commits.add(row['source']['commit'])
        signatures.add(row.get('content_signature')); pixels.add(row.get('pixel_signature'))
        identity = row.get('generation_identity', {}).get('sha256')
        if not isinstance(identity, str) or len(identity) != 64 or any(c not in '0123456789abcdef' for c in identity):
            raise ValueError('Missing generation identity')
        identities.add(identity)
        groups[row['variant']].append(row)
    if not groups or len(commits) != 1 or len(signatures) != 1 or len(pixels) != 1 or len(identities) != 1:
        raise ValueError('Study must compare one immutable implementation and matching content')
    for values in (signatures, pixels):
        if any(not isinstance(v, str) or len(v) != 64 or any(c not in '0123456789abcdef' for c in v) for v in values):
            raise ValueError('Missing paired content hashes')
    candidates, excluded = [], []
    for name, rows in groups.items():
        if len(rows) != repeats or {r['repeat'] for r in rows} != set(range(repeats)):
            raise ValueError('Missing or duplicate policy repetitions')
        policies = {digest(r['execution']['requested']) for r in rows}
        if len(policies) != 1:
            raise ValueError('A variant changes policy between repetitions')
        plan = rows[0]['execution']
        native = _positive(plan.get('native_threads'), 'bounded OpenCV thread count', integer=True)
        count = _positive(plan.get('workers'), 'worker count', integer=True)
        if any(r['execution']['workers'] != count or r['execution']['native_threads'] != native
               or r['execution']['max_in_flight'] != plan['max_in_flight'] for r in rows):
            raise ValueError('Effective policy changes between repetitions')
        required_available, peak_rss = 0, 0
        for row in rows:
            guards = row.get('guard_limits', {})
            floor = _positive(guards.get('min_available_gib'), 'available-memory guard')*GIB
            swap_limit = _positive(guards.get('max_swap_out_mib'), 'swap-out guard')*MIB
            _positive(guards.get('cell_timeout_seconds'), 'timeout guard')
            rss_limit = _positive(guards.get('rss_limit_gib'), 'RSS guard')*GIB
            initial = _positive(row.get('initial_available_memory_bytes'), 'initial available RAM')
            minimum = _positive(row.get('minimum_available_memory_bytes'), 'minimum available RAM')
            swap = _positive(row.get('swap_out_delta_bytes'), 'swap-out growth', zero=True)
            observed = _positive(row.get('command_resource_observed', {}).get('peak_rss_bytes'), 'observed RSS')
            observed = max(observed, _positive(row.get('resource_peaks', {}).get('rss_bytes', 0), 'generation RSS', zero=True))
            if minimum > initial:
                raise ValueError('Minimum available memory exceeds the initial observation')
            if minimum < floor or swap > swap_limit or observed > rss_limit:
                raise ValueError('Completed study violates its recorded guards')
            required_available = max(required_available, max(0, initial-minimum)*1.1 + floor)
            peak_rss = max(peak_rss, observed)
        rates = [r['throughput'] for r in rows]
        item = {'variant': name, 'workers': count, 'native_threads': native,
                'throughput': {'median': median(rates), 'min': min(rates), 'max': max(rates)},
                'peak_observed_rss_bytes': peak_rss, 'required_available_memory_bytes': math.ceil(required_available)}
        current_budget = resolved.profile.execution.cpu_budget or hardware['usable_cpus']
        if count*native > min(current_budget, hardware['usable_cpus']) or required_available > hardware['available_memory_bytes']:
            excluded.append({**item, 'reason': 'Current CPU budget or available-memory headroom is insufficient'})
            continue
        candidates.append(item)
    if not candidates:
        raise ValueError('No measured policy fits current headroom; free RAM or benchmark smaller candidates')
    best = max(candidates, key=lambda c: c['throughput']['median'])
    threshold = best['throughput']['median']*(1-tolerance_percent/100)
    near = [c for c in candidates if c['throughput']['median'] >= threshold]
    chosen = min(near, key=lambda c: (c['workers'], c['workers']*c['native_threads'], c['peak_observed_rss_bytes'], -c['throughput']['median']))
    measured = groups[chosen['variant']][0]['execution']
    settings = {key: measured[key] for key in ('workers', 'native_threads', 'max_in_flight')}
    settings['decoded_cache_mb'] = measured['requested']['decoded_cache_mb']
    # Preserve the composer's resource budgets. Trial safety ceilings are not
    # silently installed as normal-generation budgets.
    for key in ('cpu_budget', 'ram_budget_mb'):
        if getattr(resolved.profile.execution, key) is not None:
            settings[key] = getattr(resolved.profile.execution, key)
    policy = ExecutionConfig.model_validate(settings)
    current = resolved.model_copy(update={'profile': resolved.profile.model_copy(update={'execution': policy})})
    advisory = plan_execution(current, available_ram=hardware['available_memory_bytes'], logical_cpus=hardware['usable_cpus'])
    return {'schema_version': 1, 'status': 'complete', 'kind': 'execution-recommendation',
            'tuning_context': study['tuning_context'], 'study_sha256': digest(study),
            'selected': chosen, 'fastest': best, 'candidates': candidates, 'excluded': excluded,
            'method': {'minimum_samples': 20, 'minimum_repetitions': 3, 'near_best_tolerance_percent': tolerance_percent,
                       'preference': 'fewest workers, then requested CPU concurrency, then measured RSS',
                       'headroom_rule': 'largest observed host-memory drop ×1.10 + recorded available-memory floor'},
            'overrides': {'execution': settings}, 'current_advisory_plan': advisory.as_dict(),
            'scope': 'Environment-local recommendation, not a hardware-class speed guarantee or hard memory bound.'}


def save_tuning_result(result, output_dir):
    root = Path(output_dir)
    if root.exists():
        raise ValueError('Tuning destination must not exist')
    root.mkdir(parents=True)
    (root/'result.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    if result['kind'] == 'execution-candidates':
        documents = {'matrix.yaml': result['matrix'], 'starting-overrides.yaml': result['starting_overrides']}
    else:
        documents = {'recommended-overrides.yaml': result['overrides']}
    for name, payload in documents.items():
        (root/name).write_text(yaml.safe_dump(payload, sort_keys=False), encoding='utf-8')
    return result
