"""Independent stdlib archive counterexamples; writes only disposable synthetic data.
Run from repository root: python PATH/probe_archive.py --output PATH/results.json
The target validator is imported from the caller's pinned checkout; no product import.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[5]
spec = importlib.util.spec_from_file_location('reviewed_contract', ROOT / 'scripts/check_sdist_contract.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
DIST = 'repo_catalog-0.2.0/'
PKG = b'Metadata-Version: 2.4\nName: repo-catalog\nVersion: 0.2.0\n\n'


def make_source(root, products=4):
    (root / 'src/repo_catalog').mkdir(parents=True)
    raw = {'pyproject.toml': b'[project]\nname="repo-catalog"\nversion="0.2.0"\n',
           'README.md': b'# Synthetic\n', '.gitignore': b'__pycache__/\n',
           'src/repo_catalog/__init__.py': b'',
           'src/repo_catalog/schema.sql': b'SELECT 1;\n',
           'src/repo_catalog/contract.json': b'{}',
           'src/repo_catalog/query.graphql': b'query { viewer { login } }'}
    for i in range(products - 4):
        raw[f'src/repo_catalog/input_{i:04}.py'] = b''
    for name, value in raw.items():
        (root / name).write_bytes(value)
    return raw | {'PKG-INFO': PKG}


def write_tar(path, inputs, *, omit=(), altered=None, extra=(), pax=None, fmt=tarfile.PAX_FORMAT):
    inputs = inputs | (altered or {})
    with tarfile.open(path, 'w:gz', format=fmt) as t:
        for i, (name, raw) in enumerate(inputs.items()):
            if name in omit:
                continue
            m = tarfile.TarInfo(DIST + name)
            m.size = len(raw)
            if pax and i == 0:
                m.pax_headers = pax
            t.addfile(m, io.BytesIO(raw))
        for name, kind, payload in extra:
            m = tarfile.TarInfo(name)
            m.type = kind
            if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                m.linkname = '../../escaped'
            if kind == tarfile.REGTYPE:
                m.size = len(payload)
            t.addfile(m, io.BytesIO(payload))
    return path


def run(output):
    result = {'reviewed_head': subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'validator_sha256': hashlib.sha256((ROOT/'scripts/check_sdist_contract.py').read_bytes()).hexdigest(),
              'python': sys.version, 'executable': sys.executable, 'cases': []}
    with tempfile.TemporaryDirectory(prefix='adr0033-independent-archive-') as temp:
        work = Path(temp)
        src = work/'source'
        inputs = make_source(src)
        def check(label, path, expected, source=src):
            try:
                r = c.check_sdist(path, source)
                actual = 'accepted'
                detail = {k:r[k] for k in ('compressed_bytes','unpacked_bytes','member_count','file_count','product_files')}
            except Exception as e:
                actual = 'rejected'
                detail = {'exception':type(e).__name__, 'message':str(e)}
            result['cases'].append({'id':label,'expected':expected,'actual':actual,'matches_expectation':actual==expected, 'detail':detail})
            return result['cases'][-1]
        base = write_tar(work/'base.tar.gz',inputs)
        check('valid-control',base,'accepted')
        for i,name in enumerate(('/outside','../outside',DIST+'../outside',DIST+'./README.md',DIST+'a//b',DIST+'C:/x',DIST+'x\\y','other-0.2.0/a',DIST+'README.md',DIST+'docs/log.txt',DIST+'src/repo_catalog/hidden.zip',DIST+'src/repo_catalog/run.exe')):
            check('invalid-name-'+str(i),write_tar(work/f'name{i}.tar.gz',inputs,extra=[(name,tarfile.REGTYPE,b'')]),'rejected')
        for i,kind in enumerate((tarfile.SYMTYPE,tarfile.LNKTYPE,tarfile.FIFOTYPE,tarfile.CHRTYPE,tarfile.BLKTYPE)):
            check('special-'+repr(kind),write_tar(work/f'special{i}.tar.gz',inputs,extra=[(DIST+'special',kind,b'')]),'rejected')
        for i,name in enumerate(('src/repo_catalog/schema.sql','src/repo_catalog/contract.json','src/repo_catalog/query.graphql','.gitignore','PKG-INFO')):
            check('missing-'+name,write_tar(work/f'missing{i}.tar.gz',inputs,omit=[name]),'rejected')
        check('changed-product',write_tar(work/'changed.tar.gz',inputs,altered={'src/repo_catalog/schema.sql':b'SELECT 2;'}),'rejected')
        for i,metadata in enumerate((b'Name: wrong\nVersion: 0.2.0\nMetadata-Version: 2.4\n\n',PKG.replace(b'2.4',b'garbage'),PKG.replace(b'Name: repo-catalog',b'Name: repo-catalog\nName: attacker'))):
            check('metadata-'+str(i),write_tar(work/f'metadata{i}.tar.gz',inputs,altered={'PKG-INFO':metadata}),'rejected')
        # Exact configured compressed boundary; tar/gzip accepts trailing zero padding.
        for delta in (0,1):
            p = work/f'compressed-{delta}.tar.gz'
            p.write_bytes(base.read_bytes() + b'\0'*(c.MAX_COMPRESSED-base.stat().st_size+delta))
            check('compressed-boundary-'+str(delta),p,'accepted' if delta==0 else 'rejected')
        # Exact configured regular-file logical-size budget, with valid metadata prefix.
        current = sum(map(len,inputs.values()))
        for delta in (0,1):
            metadata = PKG + b'A'*(c.MAX_UNPACKED-current+delta)
            check('unpacked-boundary-'+str(delta),write_tar(work/f'unpacked-{delta}.tar.gz',inputs,altered={'PKG-INFO':metadata}),'accepted' if delta==0 else 'rejected')
        for delta in (0,1):
            boundary = work/f'member-source-{delta}'
            boundary_inputs=make_source(boundary,products=c.MAX_MEMBERS-4+delta)
            check('member-boundary-'+str(delta),write_tar(work/f'members-{delta}.tar.gz',boundary_inputs),'accepted' if delta==0 else 'rejected',boundary)
        # PAX header payload is processed by tarfile before yielding a visible member.
        p=write_tar(work/'pax-hidden-log.tar.gz',inputs,pax={'review.hidden_log':'A'*(10*1024*1024)})
        case=check('unallowlisted-10MiB-pax-data',p,'rejected')
        case['detail']['decompressed_tar_bytes']=len(gzip.decompress(p.read_bytes()))
        case['detail']['hidden_pax_value_bytes']=10*1024*1024
        # End-of-archive causes tarfile to stop without inspecting a second gzip/tar stream.
        hidden=work/'hidden.tar.gz'
        write_tar(hidden,{'docs/hidden-evidence.log':b'A'*(10*1024*1024)})
        p=work/'concatenated.tar.gz'
        p.write_bytes(base.read_bytes()+hidden.read_bytes())
        case=check('concatenated-gzip-tar-with-hidden-log',p,'rejected')
        case['detail']['decompressed_tar_bytes']=len(gzip.decompress(p.read_bytes()))
        # The checker must consume/validate the gzip framing, not only tar members.
        for label, raw in (
            ('corrupt-gzip-crc',base.read_bytes()[:-8]+b'\0'*8),
            ('missing-gzip-trailer',base.read_bytes()[:-8]),
            ('malformed-second-gzip-member',base.read_bytes()+b'\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\xffgarbage'),
        ):
            path=work/(label+'.tar.gz')
            path.write_bytes(raw)
            case=check(label,path,'rejected')
            try:
                gzip.decompress(raw)
                case['independent_gzip_validation']='accepted'
            except Exception as e:
                case['independent_gzip_validation']={'exception':type(e).__name__,'message':str(e)}
        # Standalone CLI acceptance is independently recorded for the two payloads.
        result['cli_unexpected_acceptances']=[]
        for label in ('pax-hidden-log','concatenated','metadata1','metadata2'):
            path=work/(label+'.tar.gz')
            receipt=work/(label+'.json')
            proc=subprocess.run([sys.executable,str(ROOT/'scripts/check_sdist_contract.py'),'--source-root',str(src),'--sdist',str(path),'--output',str(receipt)],capture_output=True,text=True)
            result['cli_unexpected_acceptances'].append({'id':label,'exit_code':proc.returncode,'receipt_status':json.loads(receipt.read_text())['status'],'stderr':proc.stderr})
        # CLI refusal creates a failed receipt and extracts nothing.
        bad=write_tar(work/'bad-cli.tar.gz',inputs,extra=[('/escaped',tarfile.REGTYPE,b'bad')])
        receipt=work/'receipt.json'
        proc=subprocess.run([sys.executable,str(ROOT/'scripts/check_sdist_contract.py'),'--source-root',str(src),'--sdist',str(bad),'--output',str(receipt)],capture_output=True,text=True)
        result['cli_rejection']={'exit_code':proc.returncode,'stderr':proc.stderr,'receipt':json.loads(receipt.read_text()),'extraction_performed':False}
        # Retain small synthetic specimens without extracting their contents.
        specimens=output.parent/'counterexamples'
        specimens.mkdir(exist_ok=False)
        for label in ('pax-hidden-log','concatenated','metadata1','metadata2','corrupt-gzip-crc','missing-gzip-trailer','malformed-second-gzip-member'):
            archive=work/(label+'.tar.gz')
            (specimens/archive.name).write_bytes(archive.read_bytes())
        fixture=specimens/'source'
        for name,raw in inputs.items():
            if name=='PKG-INFO':
                continue
            destination=fixture/name
            destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_bytes(raw)
    result['summary']={'cases':len(result['cases']),'expectation_matches':sum(x['matches_expectation'] for x in result['cases']),'unexpected_acceptances':[x['id'] for x in result['cases'] if not x['matches_expectation']]}
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['summary']))
    return 1 if result['summary']['unexpected_acceptances'] else 0

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    raise SystemExit(run(parser.parse_args().output))
