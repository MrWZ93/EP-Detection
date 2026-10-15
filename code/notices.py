"""Build dependency notices without embedding installation paths."""
import importlib.metadata,pathlib,sys
out=['# Third-party dependency notices\n\nThe application bundles Python and open-source dependencies. The project license does not replace their licenses.\n']
for dist in sorted(importlib.metadata.distributions(),key=lambda d:d.metadata['Name'].lower()):
 out.append('\n## '+dist.metadata['Name']+' '+dist.version+'\n')
 out.append('License metadata: '+str(dist.metadata.get('License-Expression') or dist.metadata.get('License') or 'See upstream license')+'\n')
 for f in dist.files or []:
  if 'license' in pathlib.PurePosixPath(str(f)).name.lower() and ('.dist-info/' in str(f)):
   try:out.append('\n'+dist.locate_file(f).read_text(errors='replace')+'\n')
   except OSError:pass
for p in [pathlib.Path(sys.base_prefix)/'LICENSE',pathlib.Path(sys.base_prefix)/'lib'/'python3.11'/'LICENSE.txt']:
 if p.exists():out.append('\n## Python runtime\n'+p.read_text(errors='replace'))
pathlib.Path('THIRD_PARTY_NOTICES.txt').write_text('\n'.join(out))
