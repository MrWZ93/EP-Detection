# Build from the repository root with PyInstaller. No user data is collected.
from pathlib import Path
root=Path(SPECPATH)
a=Analysis([str(root/'code'/'launcher.py')],pathex=[str(root/'code')],binaries=[],datas=[(str(root/'web'),'web'),(str(root/'cloud_config.json'),'.'),(str(root/'THIRD_PARTY_NOTICES.txt'),'.')],hiddenimports=['uvicorn.logging','uvicorn.loops.auto','uvicorn.protocols.http.auto','uvicorn.protocols.http.h11_impl','uvicorn.lifespan.on'],hookspath=[],excludes=['pytest','IPython','matplotlib','pandas'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='EP Desktop',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False,target_arch='arm64' if __import__('sys').platform=='darwin' else None,codesign_identity=None,entitlements_file=None)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='EP Desktop')
if __import__('sys').platform=='darwin':
 app=BUNDLE(coll,name='EP Desktop.app',icon=None,bundle_identifier='org.epstudy.desktop',info_plist={'CFBundleShortVersionString':'1.0.0','CFBundleVersion':'2','NSHighResolutionCapable':True,'NSHumanReadableCopyright':'EP Detection project'})
