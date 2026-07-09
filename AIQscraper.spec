# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for NetApp Active IQ Advisor
Builds a native desktop app from the existing HTML/JS dashboard + Python proxy.

Usage:
  Windows:  pyinstaller AIQscraper.spec
  macOS:    pyinstaller AIQscraper.spec

Output:
  Windows:  dist\NetApp_AIQ_Advisor\NetApp_AIQ_Advisor.exe  (+ support files)
  macOS:    dist/NetApp AIQ Advisor.app
"""

import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules

IS_MAC = sys.platform == 'darwin'
IS_WIN = sys.platform == 'win32'

block_cipher = None

# ---------------------------------------------------------------------------
# Static web assets to bundle alongside the Python code
# ---------------------------------------------------------------------------
web_datas = [
    ('index.html', '.'),
    ('app.js',     '.'),
    ('styles.css', '.'),
    ('chart.js',   '.'),
]

# ---------------------------------------------------------------------------
# pywebview: collect everything so platform-specific backends are included
# ---------------------------------------------------------------------------
webview_datas, webview_binaries, webview_hidden = collect_all('webview')

all_datas    = web_datas    + webview_datas
all_binaries = webview_binaries
all_hidden   = webview_hidden + collect_submodules('webview')

# Platform-specific hidden imports
if IS_WIN:
    all_hidden += [
        'webview.platforms.winforms',
        'clr', 'clr._ClrModule',
        'System', 'System.Windows.Forms',
        'pythonnet',
    ]
elif IS_MAC:
    all_hidden += [
        'webview.platforms.cocoa',
        'Foundation', 'AppKit', 'objc', 'WebKit',
    ]

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=all_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'PIL', 'Pillow', 'scipy'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ---------------------------------------------------------------------------
# macOS: one-directory build wrapped into a .app bundle
# ---------------------------------------------------------------------------
if IS_MAC:
    exe = EXE(
        pyz, a.scripts, [],
        exclude_binaries=True,
        name='NetApp_AIQ_Advisor',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        argv_emulation=True,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
    coll = COLLECT(
        exe, a.binaries, a.zipfiles, a.datas,
        strip=False, upx=False, upx_exclude=[],
        name='NetApp_AIQ_Advisor',
    )
    app = BUNDLE(
        coll,
        name='NetApp AIQ Advisor.app',
        icon=None,                          # drop icon.icns here to use it
        bundle_identifier='com.netapp.aiqadvisor',
        version='1.11.0',
        info_plist={
            'NSPrincipalClass': 'NSApplication',
            'NSAppleScriptEnabled': False,
            'CFBundleName': 'NetApp AIQ Advisor',
            'CFBundleDisplayName': 'NetApp AIQ Advisor',
            'CFBundleShortVersionString': '1.11.0',
            'LSMinimumSystemVersion': '10.13.0',
            'NSHighResolutionCapable': True,
        },
    )

# ---------------------------------------------------------------------------
# Windows / Linux: one-directory build (more reliable with WebView2 DLLs)
# ---------------------------------------------------------------------------
else:
    exe = EXE(
        pyz, a.scripts, [],
        exclude_binaries=True,
        name='NetApp_AIQ_Advisor',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,          # No console window in production
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=None,              # drop icon.ico here to use it
    )
    coll = COLLECT(
        exe, a.binaries, a.zipfiles, a.datas,
        strip=False, upx=True, upx_exclude=[],
        name='NetApp_AIQ_Advisor',
    )