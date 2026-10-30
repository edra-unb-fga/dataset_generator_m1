"""Split and verify a bounded bundle transfer without modifying the original."""
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

MAX_CHUNK_BYTES=32*1024*1024


def split_bundle(bundle, destination, chunk_bytes=MAX_CHUNK_BYTES):
    if not 0 < chunk_bytes <= MAX_CHUNK_BYTES:
        raise ValueError('Chunk size must be between 1 and 32 MiB')
    destination=Path(destination);destination.mkdir(exist_ok=False)
    chunks=[];whole=hashlib.sha256()
    with Path(bundle).open('rb') as source:
        while data:=source.read(chunk_bytes):
            name=f'context-input-{len(chunks):04d}.part'
            (destination/name).write_bytes(data);whole.update(data)
            chunks.append({'name':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    if not chunks:raise ValueError('Input bundle is empty')
    return {'chunks':chunks,'sha256':whole.hexdigest()}


def assemble_bundle(source, destination, transfer):
    source=Path(source);destination=Path(destination);partial=destination.with_suffix('.partial')
    if destination.exists() or partial.exists():raise FileExistsError(destination)
    if not transfer['chunks']:raise ValueError('No chunks')
    whole=hashlib.sha256()
    try:
        with partial.open('xb') as out:
            for i,chunk in enumerate(transfer['chunks']):
                name=f'context-input-{i:04d}.part'
                if chunk['name']!=name or not 0 < chunk['bytes'] <= MAX_CHUNK_BYTES:
                    raise ValueError('Invalid chunk descriptor')
                data=(source/name).read_bytes()
                if len(data)!=chunk['bytes'] or hashlib.sha256(data).hexdigest()!=chunk['sha256']:
                    raise ValueError(f'Chunk checksum or size mismatch: {name}')
                whole.update(data);out.write(data)
        if whole.hexdigest()!=transfer['sha256']:raise ValueError('Assembled bundle checksum mismatch')
        partial.replace(destination)
    except BaseException:
        partial.unlink(missing_ok=True);raise


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    os.replace(temporary, path)


def call(colab, *args, timeout=180, check=True):
    result = subprocess.run([colab, '--auth=oauth2', *args], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, timeout=timeout)
    print(re.sub(r'(?i)(colab-runtime-proxy-token=)[^\s&]+', r'\1[REDACTED]', result.stdout), flush=True)
    if check and result.returncode:
        raise RuntimeError(f'{args[0]} exited {result.returncode}')
    return result
