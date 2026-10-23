"""Independent stdlib probes of frozen PR142; write only this evidence directory.

Run: python docs/implementation/evidence/adr0033-hardening-rereview-20261023/independent-audit/probe_independent.py
No product imports, extraction, build, installation or network access occurs.
"""
from __future__ import annotations
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tarfile
import tempfile
import zlib

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
CHECKER = ROOT / 'scripts/check_sdist_contract.py'
spec = importlib.util.spec_from_file_location('independent_reviewed_contract', CHECKER)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
PREFIX = 'repo_catalog-0.2.0/'
PKG = b'Metadata-Version: 2.4\nName: repo-catalog\nVersion: 0.2.0\n\n'
RETAINED = ROOT / 'docs/implementation/evidence/adr0033-independent-review-20261023/archive/counterexamples'

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def tar_bytes(inputs, metadata=PKG):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        for name, body in (inputs | {'PKG-INFO': metadata}).items():
            member = tarfile.TarInfo(PREFIX + name)
            member.size = len(body)
            archive.addfile(member, io.BytesIO(body))
    return out.getvalue()

def checksum(raw):
    raw = bytearray(raw)
    raw[148:156] = b' ' * 8
    raw[148:156] = f'{sum(raw[:512]):06o}\0 '.encode()
    return bytes(raw)

def mutation(raw, start, end, value):
    changed = bytearray(raw)
    assert len(value) == end-start
    changed[start:end] = value
    return checksum(changed)

def extension(kind, payload):
    header = tarfile.TarInfo('ignored-extension')
    header.type = kind
    header.size = len(payload)
    return header.tobuf(format=tarfile.USTAR_FORMAT) + payload + b'\0'*(-len(payload)%512)

def gzip_header(raw, flags=0, extra=b'', name=b'', comment=b'', hcrc=False):
    flags |= 2 if hcrc else 0
    header = b'\x1f\x8b\x08' + bytes([flags]) + b'\0'*4 + b'\0\xff'
    if flags & 4:
        header += struct.pack('<H',len(extra)) + extra
    if flags & 8:
        header += name+b'\0'
    if flags & 16:
        header += comment+b'\0'
    if hcrc:
        header += struct.pack('<H',zlib.crc32(header)&65535)
    compressed = zlib.compressobj(wbits=-15)
    body = compressed.compress(raw)+compressed.flush()
    return header+body+struct.pack('<II',zlib.crc32(raw),len(raw)&0xffffffff)

def main():
    result = {'reviewed_head': subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'reviewed_tree': subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=ROOT,text=True).strip(),
              'checker_sha256':sha(CHECKER.read_bytes()), 'python':sys.version,
              'executable':sys.executable,'zlib_runtime':zlib.ZLIB_RUNTIME_VERSION,
              'cases':[], 'cli':[]}
    with tempfile.TemporaryDirectory(prefix='adr0033-independent-rereview-') as temp:
        work = Path(temp)
        source = work/'source'
        inputs = {'pyproject.toml':b'[project]\nname="repo-catalog"\nversion="0.2.0"\n',
                  'README.md':b'# Independent fixture\n', '.gitignore':b'__pycache__/\n',
                  'src/repo_catalog/__init__.py':b'', 'src/repo_catalog/data.sql':b'SELECT 1;\n',
                  'src/repo_catalog/data.json':b'{}\n','src/repo_catalog/data.graphql':b'query { viewer { login } }\n'}
        for name,body in inputs.items():
            p=source/name
            p.parent.mkdir(parents=True,exist_ok=True)
            p.write_bytes(body)
        base = tar_bytes(inputs)
        used=sum(512+((len(body)+511)//512)*512 for body in (inputs|{'PKG-INFO':PKG}).values())
        paths={}
        def check(label, compressed, expected='rejected', src=source, cli=False):
            path=work/(label+'.tar.gz')
            path.write_bytes(compressed)
            paths[label]=path
            try:
                receipt=c.check_sdist(path,src)
                actual='accepted'
                detail={key:receipt[key] for key in ('compressed_bytes','tar_stream_bytes','unpacked_bytes','raw_header_count','member_count','file_count')}
            except Exception as error:
                actual='rejected'
                detail={'exception':type(error).__name__,'message':str(error)}
            case={'id':label,'expected':expected,'actual':actual,'matches_expectation':actual==expected,
                  'archive_bytes':len(compressed),'archive_sha256':sha(compressed),'detail':detail}
            result['cases'].append(case)
            if cli:
                output=work/(label+'.receipt.json')
                cmd=[sys.executable,str(CHECKER),'--source-root',str(src),'--sdist',str(path),'--output',str(output)]
                proc=subprocess.run(cmd,capture_output=True,text=True)
                receipt=json.loads(output.read_text()) if output.exists() else None
                wanted=0 if expected=='accepted' else 1
                result['cli'].append({'id':label,'command':cmd,'exit_code':proc.returncode,'expected_exit_code':wanted,
                                      'receipt':receipt if wanted else {'status':receipt['status']},
                                      'stdout':proc.stdout,'stderr':proc.stderr,
                                      'matches_expectation':proc.returncode==wanted and receipt['status']==('passed' if not wanted else 'failed')})
            return case
        check('plain-ustar-control',gzip.compress(base,mtime=0),'accepted',cli=True)
        check('minimal-two-zero-blocks',gzip.compress(base[:used]+b'\0'*1024),'accepted')
        check('gzip-all-optional-fields-valid',gzip_header(base,flags=28,extra=b'AA\x01\x00x',name=b'source.tar',comment=b'build metadata',hcrc=True),'accepted')
        hdr=gzip_header(base,flags=28,extra=b'AA\x01\x00x',name=b'source.tar',comment=b'build metadata',hcrc=True)
        changed=bytearray(hdr); changed[10+2+5+len(b'source.tar')+1+len(b'build metadata')+1]^=1
        check('gzip-optional-header-crc-corrupt',bytes(changed),cli=True)
        for flag in (32,64,128):
            check('gzip-reserved-flag-'+str(flag),gzip_header(base,flags=flag))
        for label,raw in [('gzip-junk',gzip.compress(base)+b'JUNK'),('gzip-trailing-zero',gzip.compress(base)+b'\0'),
                          ('gzip-empty-second-member',gzip.compress(base)+gzip.compress(b'')),
                          ('gzip-second-tar-member',gzip.compress(base)+gzip.compress(base)),
                          ('gzip-missing-trailer',gzip.compress(base)[:-8]),
                          ('gzip-truncated-deflate',gzip.compress(base)[:-12])]:
            check(label,raw,cli=True)
        for position in (-8,-4):
            changed=bytearray(gzip.compress(base)); changed[position]^=128
            check('gzip-corrupt-trailer-'+str(position),bytes(changed))
        for n in (0,1):
            check('tar-end-blocks-'+str(n),gzip.compress(base[:used]+b'\0'*(512*n)))
        check('tar-hidden-second-after-end',gzip.compress(base+base),cli=True)
        check('tar-hidden-second-after-one-zero',gzip.compress(base[:used]+b'\0'*512+base))
        check('tar-unframed-tail',gzip.compress(base+b'x'))
        check('tar-aligned-nonzero-tail',gzip.compress(base+b'x'+b'\0'*511))
        changed=bytearray(base); changed[512+len(inputs['pyproject.toml'])]=1
        check('tar-nonzero-body-alignment',gzip.compress(changed))
        for label,start,end,value in [
            ('negative-size',124,136,b'-0000000001\0'),
            ('giant-size',124,136,b'77777777777\0'),
            ('base256-giant-size',124,136,b'\x80'+b'\xff'*11),
            ('directory-with-body',156,157,tarfile.DIRTYPE),
            ('regular-with-linkname',157,257,b'../../escape'+b'\0'*88),
            ('unsafe-ustar-prefix',345,500,b'../escape'+b'\0'*146),
            ('invalid-utf8-name',0,100,b'\xff'+b'\0'*99),
        ]:
            check('tar-'+label,gzip.compress(mutation(base,start,end,value)))
        for kind in (b'x',b'g',b'L',b'K',b'S',b'V',b'1',b'2',b'3',b'4',b'6',b'7',b'Z'):
            check('tar-unapproved-kind-'+kind.decode(),gzip.compress(extension(kind,b'10 x=y\n')+base))
        for label,metadata in [
            ('duplicate-mixed-case',PKG.replace(b'\n\n',b'\nnAmE: attacker\n\n')),
            ('duplicate-metadata-version',PKG.replace(b'\n\n',b'\nmetadata-version: 2.4\n\n')),
            ('duplicate-version',PKG.replace(b'\n\n',b'\nVERSION: 0.2.0\n\n')),
            ('folded-name',PKG.replace(b'Name: repo-catalog',b'Name: repo-\n catalog')),
            ('embedded-nul-name',PKG.replace(b'repo-catalog',b'repo-catalog\0')),
            ('embedded-cr-name',PKG.replace(b'repo-catalog',b'repo-catalog\rInjected: yes')),
            ('invalid-header-separator',PKG.replace(b'Name:',b'Name :')),
            ('unsupported-metadata-version',PKG.replace(b'2.4',b'3.0')),
            ('trailing-version-data',PKG.replace(b'0.2.0',b'0.2.0 junk')),
            ('header-continuation-after-version',PKG.replace(b'0.2.0',b'0.2.0\n injected')),
            ('missing-body-separator',b'not a header\n'+PKG),
        ]:
            # Bare CR is a parser-supported line separator, producing a valid
            # unrelated field; this does not alter the parsed Name identity.
            check('metadata-'+label,gzip.compress(tar_bytes(inputs,metadata)),
                  'accepted' if label == 'embedded-cr-name' else 'rejected',
                  cli=label in ('duplicate-mixed-case','unsupported-metadata-version'))
        for name in ('data.sql','data.json','data.graphql'):
            reduced={key:value for key,value in inputs.items() if key != 'src/repo_catalog/'+name}
            check('missing-resource-'+name,gzip.compress(tar_bytes(reduced)))
        for label,metadata in [('crlf',PKG.replace(b'\n',b'\r\n')),('no-description',PKG.rstrip(b'\n')+b'\n')]:
            check('metadata-valid-'+label,gzip.compress(tar_bytes(inputs,metadata)),'accepted')
        for label in ('pax-hidden-log','concatenated','metadata1','metadata2','corrupt-gzip-crc','missing-gzip-trailer','malformed-second-gzip-member'):
            check('retained-'+label,(RETAINED/(label+'.tar.gz')).read_bytes(),src=RETAINED/'source',cli=True)
        # Verify ordering independently: an over-budget stream must never invoke
        # the tar header parser, including a compressed high-ratio PAX envelope.
        calls=[]
        original=c.check_tar_structure
        def forbidden(raw):
            calls.append(len(raw))
            raise AssertionError('tar parsing invoked before stream bound')
        c.check_tar_structure=forbidden
        try:
            case=check('inflation-before-any-tar-parse',gzip.compress(extension(b'x',b'A'*(c.MAX_TAR_STREAM+512))+base))
            case['tar_parse_calls']=calls[:]
            case['matches_expectation'] &= not calls and 'budget exceeded' in case['detail'].get('message','')
        finally:
            c.check_tar_structure=original
    result['summary']={'cases':len(result['cases']),'cli_cases':len(result['cli']),
                       'unexpected_results':[case['id'] for case in result['cases']+result['cli'] if not case['matches_expectation']],
                       'initial_expectation_correction':'Initial bare-CR case expected rejection. BytesParser treats CR as a line separator, leaving the required Name exact and adding only an unrelated header. No applicable identity requirement forbids this; integrated wheel metadata equality remains additional validation. Initial exit1/results retained separately.',
                       'scope':'Independent bounded archive/identity probes only; no pytest suite, product behavior, wheel builds or release acceptance.'}
    (HERE/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['summary'],indent=2))
    return bool(result['summary']['unexpected_results'])

if __name__=='__main__':
    raise SystemExit(main())
