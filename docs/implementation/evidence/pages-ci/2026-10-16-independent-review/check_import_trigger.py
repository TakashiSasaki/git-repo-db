import json, runpy, sys
from pathlib import Path
import yaml
root = Path.cwd()
sys.argv = ['scripts/schema_viz.py', '--check']
try:
    runpy.run_path('scripts/schema_viz.py', run_name='__main__')
except SystemExit as error:
    assert error.code in (None, 0)
module = runpy.run_path('tests/unit/test_build_docs_site.py')
config = yaml.safe_load(Path('.github/workflows/pages.yml').read_text())
patterns = (config.get('on') or config[True])['push']['paths']
loaded = sorted({Path(m.__file__).relative_to(root).as_posix() for m in tuple(sys.modules.values()) if getattr(m, '__file__', None) and str(root / 'src/repo_catalog') in m.__file__})
missing = [p for p in loaded if not module['_eval_github_workflow_trigger'](patterns, [p])]
print(json.dumps({'loaded':loaded, 'missing':missing}, indent=2))
assert not missing, missing
