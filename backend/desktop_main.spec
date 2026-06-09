# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for bundling the RAG Platform backend as a desktop sidecar.
Usage: pyinstaller --noconfirm desktop_main.spec
"""
import importlib
import os
import pathlib
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Path to shared package (rag_platform_common) — build is run from backend/
_SHARED_DIR = os.path.abspath(os.path.join(os.getcwd(), '..', 'shared'))
if os.path.isdir(_SHARED_DIR):
    sys.path.insert(0, _SHARED_DIR)


def _collect_pkg_tree(pkg_name, extensions=('.py', '.pyd', '.so', '.json', '.yaml', '.yml', '.txt', '.sql')):
    """Copy an entire installed package as datas, preserving directory structure.

    This is required for packages like chromadb 0.6.x that use implicit
    namespace packages (directories without __init__.py).  collect_submodules
    and hiddenimports cannot handle these; the files must exist on disk at
    runtime so Python's file-system importer can discover them.
    """
    try:
        pkg = importlib.import_module(pkg_name)
    except Exception:
        return []
    pkg_dir = pathlib.Path(pkg.__file__).parent
    site_packages = pkg_dir.parent
    pairs = []
    for f in pkg_dir.rglob('*'):
        if f.is_file() and f.suffix in extensions:
            # Skip test directories to reduce bundle size
            rel = f.relative_to(site_packages)
            parts = rel.parts
            if any(p in ('test', 'tests', '__pycache__') for p in parts):
                continue
            dest_dir = str(rel.parent)
            pairs.append((str(f), dest_dir))
    return pairs


# Collect data files for packages that need them
datas = []
datas += collect_data_files('tiktoken')
# chromadb 0.6.x: copy entire package tree (namespace packages need files on disk)
datas += _collect_pkg_tree('chromadb')
datas += collect_data_files('chromadb')
datas += collect_data_files('pydantic')
datas += collect_data_files('jieba')
try:
    datas += collect_data_files('certifi')
except Exception:
    pass

# Include the app package
datas += [('app', 'app')]
# Include rag_platform_common from shared (required for desktop build)
if os.path.isdir(_SHARED_DIR):
    _COMMON_PKG = os.path.join(_SHARED_DIR, 'rag_platform_common')
    if os.path.isdir(_COMMON_PKG):
        datas += [(_COMMON_PKG, 'rag_platform_common')]

# Frontend assets are copied by electron-builder as extraResources.
# Runtime database / key / vector data live in the user's writable data dir.

# Collect all submodules for tricky packages
hiddenimports = []
hiddenimports += collect_submodules('chromadb')
hiddenimports += collect_submodules('tiktoken')
hiddenimports += collect_submodules('app')
hiddenimports += collect_submodules('uvicorn')
hiddenimports += collect_submodules('fastapi')
hiddenimports += collect_submodules('starlette')
hiddenimports += collect_submodules('sqlalchemy')
hiddenimports += collect_submodules('httpx')
hiddenimports += collect_submodules('httpcore')
hiddenimports += collect_submodules('openai')
hiddenimports += collect_submodules('slowapi')
hiddenimports += collect_submodules('sqlparse')
hiddenimports += collect_submodules('numpy')
hiddenimports += collect_submodules('jwt')
hiddenimports += collect_submodules('cryptography')
hiddenimports += collect_submodules('pydantic')
hiddenimports += collect_submodules('pydantic_settings')
hiddenimports += collect_submodules('celery')
hiddenimports += collect_submodules('celery.fixups')
hiddenimports += collect_submodules('kombu')
hiddenimports += collect_submodules('amqp')
hiddenimports += collect_submodules('billiard')
hiddenimports += collect_submodules('rag_platform_common') if os.path.isdir(_SHARED_DIR) else []
hiddenimports += [
    'rag_platform_common',
    'rag_platform_common.password',
    'rag_platform_common.jwt_utils',
    'aiosqlite',
    'sqlite3',
    'passlib.handlers.bcrypt',
    'bcrypt',
    'multipart',
    'tabulate',
    'sqlalchemy.dialects.sqlite',
    'sqlalchemy.dialects.sqlite.aiosqlite',
    'engineio.async_drivers.aiohttp',
    'jieba',
    'rank_bm25',
    'fitz',  # PyMuPDF
    'docx',
    'pptx',
    'openpyxl',
    'bs4',
    'lxml',
    'sqlparse',
    'httpx',
    'httpcore',
    'httpcore._async',
    'httpcore._sync',
    'anyio',
    'anyio._backends',
    'anyio._backends._asyncio',
    'sniffio',
    'certifi',
    'pandas',
    'pandas.io.formats.style',
    'slowapi',
    'slowapi.util',
    'slowapi.errors',
    'slowapi.extension',
    'starlette.staticfiles',
    'openai',
    'h11',
    'olefile',
    'chardet',
]

a = Analysis(
    ['desktop_main.py'],
    pathex=['.', _SHARED_DIR] if os.path.isdir(_SHARED_DIR) else ['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy', 'notebook', 'jupyter', 'torch', 'torchvision', 'torchaudio', 'tensorflow', 'keras', 'transformers', 'sentence_transformers', 'sklearn', 'cv2', 'pyarrow', 'plotly', 'polars', '_polars_runtime_32', 'onnxruntime', 'tokenizers', 'hf_xet', 'xarray', 'nltk', 'jax', 'jaxlib'],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='desktop_main',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=os.path.join('..', 'desktop', 'icon.ico') if os.path.exists(os.path.join('..', 'desktop', 'icon.ico')) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='desktop_main',
)
