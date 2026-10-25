"""Measure bounded inflation in separate sequential stdlib child processes."""
from __future__ import annotations
import gzip
import importlib.util
import json
from pathlib import Path
import resource
import subprocess
import sys
import tarfile
import tempfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]

def child(mebibytes):
    spec=importlib.util.spec_from_file_location('bounded_contract', ROOT/'scripts/check_sdist_contract.py')
    c=importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
    calls=[]
    original_header=tarfile.TarInfo.frombuf
    def forbidden_header(*args,**kwargs):
        calls.append('TarInfo.frombuf')
        raise AssertionError('tar header parser reached')
    tarfile.TarInfo.frombuf=forbidden_header
    original_decoder=c.zlib.decompressobj
    produced=[]
    class Decoder:
        def __init__(self): self.inner=original_decoder(16+c.zlib.MAX_WBITS)
        def decompress(self,data,max_length):
            out=self.inner.decompress(data,max_length)
            produced.append(len(out))
            return out
        def __getattr__(self,name): return getattr(self.inner,name)
    c.zlib.decompressobj=lambda *args:Decoder()
    with tempfile.TemporaryDirectory(prefix='bounded-gzip-audit-') as temp:
        path=Path(temp)/'opaque-pax.tar.gz'
        # Stream construction prevents the generator itself inflating max RSS.
        info=tarfile.TarInfo('unapproved-pax'); info.type=b'x'; info.size=mebibytes*1024*1024
        with gzip.open(path,'wb',compresslevel=6) as out:
            out.write(info.tobuf(format=tarfile.USTAR_FORMAT))
            for _ in range(mebibytes*16): out.write(b'A'*65536)
            out.write(b'\0'*1024)
        before=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        try:
            c.check_sdist(path,Path(temp)/'nonexistent-source')
            error=None
        except Exception as exc:
            error={'type':type(exc).__name__,'message':str(exc)}
        after=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        data={'input_logical_payload_bytes':mebibytes*1024*1024,'compressed_bytes':path.stat().st_size,
              'output_bytes_produced':sum(produced),'largest_output_chunk':max(produced),'tar_header_parser_calls':calls,
              'max_tar_stream':c.MAX_TAR_STREAM,'rss_unit':'KiB on Linux','max_rss_before_validation':before,
              'max_rss_after_validation':after,'error':error}
        data['passed']=(error and error['type']=='ValueError' and 'decompressed tar stream budget exceeded' in error['message']
                        and not calls and sum(produced)==c.MAX_TAR_STREAM+1 and max(produced)<=65536)
        print(json.dumps(data))
        return 0 if data['passed'] else 1

def main():
    results=[]
    for size in (16,64):
        cmd=[sys.executable,str(Path(__file__).resolve()),'--child',str(size)]
        proc=subprocess.run(cmd,capture_output=True,text=True)
        results.append({'command':cmd,'exit_code':proc.returncode,'stdout':proc.stdout,'stderr':proc.stderr,
                        'measurement':json.loads(proc.stdout) if proc.returncode==0 else None})
    output={'execution':'Sequential bounded counterexample child processes; no concurrent benchmark claim.',
            'measurements':results,'passed':all(row['exit_code']==0 for row in results)}
    (HERE/'bounded-memory-results.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps(output,indent=2))
    return 0 if output['passed'] else 1

if __name__=='__main__':
    raise SystemExit(child(int(sys.argv[2])) if len(sys.argv)>1 and sys.argv[1]=='--child' else main())
