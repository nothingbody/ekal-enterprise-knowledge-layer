"""Desktop release management API — upload, list, and delete installer files."""

import hashlib
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query

from app.models.user import User
from app.core.security import get_admin_user

router = APIRouter()
logger = logging.getLogger(__name__)

# 默认可写目录（Dockerfile 中 appuser 对 /app/downloads 有权限；勿默认用 /usr/share/nginx/...）
DOWNLOADS_DIR = Path(os.environ.get("DOWNLOADS_DIR", "/app/downloads"))


def _parse_version(filename: str) -> str:
    import re
    match = re.search(r"(\d+\.\d+\.\d+)", filename)
    return match.group(1) if match else "unknown"


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _get_releases() -> list[dict]:
    if not DOWNLOADS_DIR.is_dir():
        return []

    latest_file = DOWNLOADS_DIR / "zhishu-setup-latest.exe"
    latest_hash = _file_sha256(latest_file) if latest_file.is_file() else ""

    releases = []
    for f in DOWNLOADS_DIR.iterdir():
        if f.suffix in (".exe", ".dmg", ".AppImage", ".deb"):
            if f.name == "zhishu-setup-latest.exe":
                continue
            stat = f.stat()
            file_hash = _file_sha256(f)
            releases.append({
                "filename": f.name,
                "size_mb": round(stat.st_size / (1024 * 1024), 1),
                "version": _parse_version(f.name),
                "uploaded_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "is_latest": file_hash == latest_hash and bool(latest_hash),
            })
    releases.sort(key=lambda x: x["uploaded_at"], reverse=True)
    return releases


@router.get("/public/latest")
async def get_latest_release():
    """Public endpoint: return latest release version, size, and date (no auth)."""
    if not DOWNLOADS_DIR.is_dir():
        return {"version": None, "size_mb": None, "release_date": None}

    latest_file = DOWNLOADS_DIR / "zhishu-setup-latest.exe"
    if not latest_file.is_file():
        return {"version": None, "size_mb": None, "release_date": None}

    stat = latest_file.stat()
    version = "unknown"
    for f in DOWNLOADS_DIR.iterdir():
        if f.suffix in (".exe",) and f.name != "zhishu-setup-latest.exe":
            if _file_sha256(f) == _file_sha256(latest_file):
                version = _parse_version(f.name)
                break

    if version == "unknown":
        yml_path = DOWNLOADS_DIR / "latest.yml"
        if yml_path.is_file():
            import re
            txt = yml_path.read_text(encoding="utf-8")
            m = re.search(r"^version:\s*(.+)", txt, re.MULTILINE)
            if m:
                version = m.group(1).strip()

    return {
        "version": version,
        "size_mb": round(stat.st_size / (1024 * 1024), 1),
        "release_date": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime("%Y-%m-%d"),
    }


@router.get("/download/{filename}")
async def download_release(filename: str, _admin: User = Depends(get_admin_user)):
    """Serve a release file for download (admin only, for dev environments without nginx)."""
    from fastapi.responses import FileResponse
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(400, "非法文件名")
    target = DOWNLOADS_DIR / filename
    if not target.is_file():
        raise HTTPException(404, "文件不存在")
    return FileResponse(str(target), filename=filename, media_type="application/octet-stream")


@router.get("/")
async def list_releases(_admin: User = Depends(get_admin_user)):
    """List all uploaded desktop installer files."""
    return {"releases": _get_releases()}


@router.post("/upload")
async def upload_release(
    file: UploadFile = File(...),
    set_as_latest: bool = Query(True),
    _admin: User = Depends(get_admin_user),
):
    """Upload a new desktop installer and optionally set it as the latest version."""
    if not file.filename:
        raise HTTPException(400, "文件名不能为空")

    if not file.filename.endswith((".exe", ".dmg", ".AppImage", ".deb")):
        raise HTTPException(400, "仅支持 .exe / .dmg / .AppImage / .deb 格式")

    try:
        DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

        dest = DOWNLOADS_DIR / file.filename
        total_size = 0
        with open(dest, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                total_size += len(chunk)

        size_mb = round(total_size / (1024 * 1024), 1)
        logger.info("Uploaded release: %s (%.1f MB)", file.filename, size_mb)

        if set_as_latest:
            latest = DOWNLOADS_DIR / "zhishu-setup-latest.exe"
            if latest.exists() or latest.is_symlink():
                latest.unlink()
            import shutil
            shutil.copy2(str(dest), str(latest))
            logger.info("Set %s as latest", file.filename)

            _generate_latest_yml(file.filename, total_size)

        return {
            "message": f"上传成功: {file.filename} ({size_mb} MB)",
            "filename": file.filename,
            "size_mb": size_mb,
            "is_latest": set_as_latest,
            "version": _parse_version(file.filename),
        }
    except PermissionError as exc:
        logger.exception("releases upload permission denied: %s", DOWNLOADS_DIR)
        raise HTTPException(
            status_code=503,
            detail="无法写入发布目录，请确认 DOWNLOADS_DIR 对运行用户可写（Docker 建议挂载到 /app/downloads）",
        ) from exc
    except OSError as exc:
        logger.exception("releases upload failed: %s", exc)
        raise HTTPException(status_code=500, detail="保存安装包失败，请检查磁盘空间与目录权限") from exc


@router.delete("/{filename}")
async def delete_release(
    filename: str,
    _admin: User = Depends(get_admin_user),
):
    """Delete a desktop installer file."""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(400, "非法文件名")

    target = DOWNLOADS_DIR / filename
    if not target.is_file():
        raise HTTPException(404, "文件不存在")

    target.unlink()

    if filename == "zhishu-setup-latest.exe":
        yml_path = DOWNLOADS_DIR / "latest.yml"
        if yml_path.exists():
            yml_path.unlink()
    logger.info("Deleted release: %s", filename)
    return {"message": f"已删除: {filename}"}


@router.post("/{filename}/set-latest")
async def set_latest_release(
    filename: str,
    _admin: User = Depends(get_admin_user),
):
    """Set a specific release as the latest (used for auto-update)."""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(400, "非法文件名")

    source = DOWNLOADS_DIR / filename
    if not source.is_file():
        raise HTTPException(404, "文件不存在")

    latest = DOWNLOADS_DIR / "zhishu-setup-latest.exe"
    if latest.exists() or latest.is_symlink():
        latest.unlink()

    import shutil
    shutil.copy2(str(source), str(latest))

    _generate_latest_yml(filename, source.stat().st_size)

    logger.info("Set %s as latest release", filename)
    return {"message": f"已将 {filename} 设为最新版本"}


def _generate_latest_yml(filename: str, file_size: int):
    """Generate latest.yml for electron-updater auto-update.

    electron-updater expects SHA512 in base64 encoding.
    """
    import base64

    version = _parse_version(filename)
    file_path = DOWNLOADS_DIR / filename

    sha512_b64 = ""
    try:
        h = hashlib.sha512()
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
        sha512_b64 = base64.b64encode(h.digest()).decode("ascii")
    except Exception:
        pass

    yml_content = f"""version: {version}
files:
  - url: zhishu-setup-latest.exe
    sha512: {sha512_b64}
    size: {file_size}
path: zhishu-setup-latest.exe
sha512: {sha512_b64}
releaseDate: '{datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")}'
"""
    yml_path = DOWNLOADS_DIR / "latest.yml"
    yml_path.write_text(yml_content, encoding="utf-8")
    logger.info("Generated latest.yml for v%s", version)
