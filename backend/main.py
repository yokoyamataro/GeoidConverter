"""
ジオイド変換 WebAPI
"""
import os
import uuid
import json
import shutil
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path
from enum import Enum
from typing import Optional

from geoid_loader import GeoidManager
from coordinate import latlon_to_plane, plane_to_latlon, get_zone_name, PLANE_ORIGINS
from las_processor import get_las_info, process_las_file, LASInfo, ProcessingStats

app = FastAPI(title="Geoid Converter API", version="1.0.0")

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ジオイドデータの読み込み
BASE_PATH = Path(os.environ.get("GEOID_DATA_PATH", Path(__file__).parent.parent))
geoid_manager = GeoidManager(BASE_PATH)

# LASファイル処理用のディレクトリ
LAS_UPLOAD_DIR = Path(os.environ.get("LAS_UPLOAD_DIR", Path(__file__).parent / "uploads"))
LAS_OUTPUT_DIR = Path(os.environ.get("LAS_OUTPUT_DIR", Path(__file__).parent / "outputs"))
LAS_JOBS_FILE = Path(os.environ.get("LAS_JOBS_FILE", Path(__file__).parent / "jobs.json"))

# ディレクトリ作成
LAS_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
LAS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ジョブの有効期限（日数）
JOB_EXPIRY_DAYS = 7


class CoordType(str, Enum):
    LATLON = "latlon"  # 経緯度
    PLANE = "plane"    # 平面直角座標


class HeightType(str, Enum):
    ELLIPSOID = "ellipsoid"   # 楕円体高
    GEOID2024 = "geoid2024"   # ジオイド2024高（標高）
    GEOID2011 = "geoid2011"   # ジオイド2011高（標高）


class PointInput(BaseModel):
    name: str
    x: float  # 緯度 or X座標
    y: float  # 経度 or Y座標
    z: float  # 高さ


class ConvertRequest(BaseModel):
    points: list[PointInput]
    input_coord_type: CoordType
    input_height_type: HeightType
    output_height_type: HeightType
    zone: int | None = None  # 平面直角座標の場合必須
    use_island_correction: bool = False  # 離島補正を使用


class PointOutput(BaseModel):
    name: str
    lat: float
    lon: float
    input_height: float
    output_height: float
    geoid_height: float | None  # 使用したジオイド高
    is_island: bool
    island_region: str | None
    warning: str | None = None


class ConvertResponse(BaseModel):
    points: list[PointOutput]
    has_island_points: bool  # 離島の点が含まれているか


# LAS関連のモデル
class LASJobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class LASJobInfo(BaseModel):
    job_id: str
    status: LASJobStatus
    filename: str
    point_count: int
    created_at: str
    expires_at: str
    progress: float = 0.0  # 0-100
    error: Optional[str] = None
    stats: Optional[dict] = None


class LASUploadResponse(BaseModel):
    job_id: str
    filename: str
    point_count: int
    area_km2: float
    estimated_time: str
    message: str


# ジョブ管理
def load_jobs() -> dict:
    """ジョブ情報を読み込み"""
    if LAS_JOBS_FILE.exists():
        with open(LAS_JOBS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_jobs(jobs: dict):
    """ジョブ情報を保存"""
    with open(LAS_JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)


def update_job(job_id: str, **kwargs):
    """ジョブ情報を更新"""
    jobs = load_jobs()
    if job_id in jobs:
        jobs[job_id].update(kwargs)
        save_jobs(jobs)


def cleanup_expired_jobs():
    """期限切れジョブを削除"""
    jobs = load_jobs()
    now = datetime.now()
    expired = []

    for job_id, job in jobs.items():
        expires_at = datetime.fromisoformat(job["expires_at"])
        if now > expires_at:
            expired.append(job_id)
            # ファイル削除
            input_file = LAS_UPLOAD_DIR / f"{job_id}.las"
            output_file = LAS_OUTPUT_DIR / f"{job_id}.las"
            if input_file.exists():
                input_file.unlink()
            if output_file.exists():
                output_file.unlink()

    for job_id in expired:
        del jobs[job_id]

    if expired:
        save_jobs(jobs)

    return len(expired)


@app.get("/")
def root():
    return {"message": "Geoid Converter API", "version": "1.0.0"}


@app.get("/zones")
def get_zones():
    """平面直角座標系の系番号一覧を取得"""
    return {
        "zones": [
            {"zone": z, "name": get_zone_name(z), "origin": {"lat": lat, "lon": lon}}
            for z, (lat, lon) in PLANE_ORIGINS.items()
        ]
    }


@app.post("/convert", response_model=ConvertResponse)
def convert_points(request: ConvertRequest):
    """座標・高さ変換を実行"""

    # 平面直角座標の場合、系番号が必要
    if request.input_coord_type == CoordType.PLANE and request.zone is None:
        raise HTTPException(status_code=400, detail="平面直角座標の場合、系番号(zone)が必要です")

    results = []
    has_island = False

    for point in request.points:
        # 経緯度に変換
        if request.input_coord_type == CoordType.PLANE:
            latlon = plane_to_latlon(point.x, point.y, request.zone)
            lat, lon = latlon.lat, latlon.lon
        else:
            lat, lon = point.x, point.y

        # 離島チェック
        island_region = geoid_manager.check_island(lat, lon)
        is_island = island_region is not None
        if is_island:
            has_island = True

        # ジオイド高の取得
        warning = None
        geoid_height = None

        if request.input_height_type == HeightType.ELLIPSOID:
            # 楕円体高から標高へ
            if request.output_height_type == HeightType.GEOID2024:
                geoid_height = geoid_manager.get_geoid2024_height(
                    lat, lon, use_island_correction=request.use_island_correction and is_island
                )
                if geoid_height is None:
                    warning = "ジオイド高を取得できません（範囲外または海域）"
                    output_height = point.z
                else:
                    output_height = point.z - geoid_height

            elif request.output_height_type == HeightType.GEOID2011:
                geoid_height = geoid_manager.get_geoid2011_height(lat, lon)
                if geoid_height is None:
                    warning = "ジオイド高を取得できません（範囲外または海域）"
                    output_height = point.z
                else:
                    output_height = point.z - geoid_height
            else:
                output_height = point.z

        elif request.input_height_type == HeightType.GEOID2024:
            # ジオイド2024高から
            if request.output_height_type == HeightType.ELLIPSOID:
                geoid_height = geoid_manager.get_geoid2024_height(
                    lat, lon, use_island_correction=request.use_island_correction and is_island
                )
                if geoid_height is None:
                    warning = "ジオイド高を取得できません（範囲外または海域）"
                    output_height = point.z
                else:
                    output_height = point.z + geoid_height

            elif request.output_height_type == HeightType.GEOID2011:
                g2024 = geoid_manager.get_geoid2024_height(
                    lat, lon, use_island_correction=request.use_island_correction and is_island
                )
                g2011 = geoid_manager.get_geoid2011_height(lat, lon)
                if g2024 is None or g2011 is None:
                    warning = "ジオイド高を取得できません（範囲外または海域）"
                    output_height = point.z
                else:
                    # 標高(2024) → 楕円体高 → 標高(2011)
                    ellipsoid_h = point.z + g2024
                    output_height = ellipsoid_h - g2011
                    geoid_height = g2024 - g2011  # 差分として記録
            else:
                output_height = point.z

        elif request.input_height_type == HeightType.GEOID2011:
            # ジオイド2011高から
            if request.output_height_type == HeightType.ELLIPSOID:
                geoid_height = geoid_manager.get_geoid2011_height(lat, lon)
                if geoid_height is None:
                    warning = "ジオイド高を取得できません（範囲外または海域）"
                    output_height = point.z
                else:
                    output_height = point.z + geoid_height

            elif request.output_height_type == HeightType.GEOID2024:
                g2011 = geoid_manager.get_geoid2011_height(lat, lon)
                g2024 = geoid_manager.get_geoid2024_height(
                    lat, lon, use_island_correction=request.use_island_correction and is_island
                )
                if g2011 is None or g2024 is None:
                    warning = "ジオイド高を取得できません（範囲外または海域）"
                    output_height = point.z
                else:
                    # 標高(2011) → 楕円体高 → 標高(2024)
                    ellipsoid_h = point.z + g2011
                    output_height = ellipsoid_h - g2024
                    geoid_height = g2011 - g2024
            else:
                output_height = point.z
        else:
            output_height = point.z

        # 離島の場合の警告
        if is_island and not request.use_island_correction:
            if warning:
                warning += f"。離島地域（{island_region}）です。離島補正の使用を検討してください。"
            else:
                warning = f"離島地域（{island_region}）です。離島補正の使用を検討してください。"

        results.append(PointOutput(
            name=point.name,
            lat=lat,
            lon=lon,
            input_height=point.z,
            output_height=output_height,
            geoid_height=geoid_height,
            is_island=is_island,
            island_region=island_region,
            warning=warning
        ))

    return ConvertResponse(points=results, has_island_points=has_island)


@app.get("/geoid/{lat}/{lon}")
def get_geoid_info(lat: float, lon: float):
    """指定した緯度経度のジオイド情報を取得"""
    g2024 = geoid_manager.get_geoid2024_height(lat, lon, use_island_correction=False)
    g2024_island = geoid_manager.get_geoid2024_height(lat, lon, use_island_correction=True)
    g2011 = geoid_manager.get_geoid2011_height(lat, lon)
    island_region = geoid_manager.check_island(lat, lon)

    return {
        "lat": lat,
        "lon": lon,
        "geoid2024": g2024,
        "geoid2024_with_island_correction": g2024_island,
        "geoid2011": g2011,
        "is_island": island_region is not None,
        "island_region": island_region
    }


# LAS処理のバックグラウンドタスク
def process_las_background(
    job_id: str,
    input_path: Path,
    output_path: Path,
    zone: int,
    input_height_type: str,
    output_height_type: str,
    use_island_correction: bool
):
    """バックグラウンドでLASファイルを処理"""
    try:
        update_job(job_id, status="processing", progress=0.0)

        # 進捗コールバック
        def progress_callback(processed: int, total: int):
            progress = (processed / total) * 100 if total > 0 else 0
            update_job(job_id, progress=progress)

        # 処理実行
        stats = process_las_file(
            input_path=input_path,
            output_path=output_path,
            zone=zone,
            geoid_manager=geoid_manager,
            input_height_type=input_height_type,
            output_height_type=output_height_type,
            use_island_correction=use_island_correction,
            progress_callback=progress_callback
        )

        # 完了
        update_job(
            job_id,
            status="completed",
            progress=100.0,
            stats={
                "total_points": stats.total_points,
                "processed_points": stats.processed_points,
                "failed_points": stats.failed_points,
                "min_correction": stats.min_correction,
                "max_correction": stats.max_correction,
                "avg_correction": stats.avg_correction
            }
        )

        # 入力ファイル削除
        if input_path.exists():
            input_path.unlink()

    except Exception as e:
        update_job(job_id, status="failed", error=str(e))
        # ファイル削除
        if input_path.exists():
            input_path.unlink()
        if output_path.exists():
            output_path.unlink()


@app.post("/las/upload", response_model=LASUploadResponse)
async def upload_las(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    zone: int = 9,
    input_height_type: str = "ellipsoid",
    output_height_type: str = "geoid2024",
    use_island_correction: bool = False
):
    """
    LASファイルをアップロードして変換ジョブを開始

    - zone: 平面直角座標の系番号 (1-19)
    - input_height_type: 入力高さタイプ (ellipsoid/geoid2024/geoid2011)
    - output_height_type: 出力高さタイプ (ellipsoid/geoid2024/geoid2011)
    - use_island_correction: 離島補正を使用
    """
    # 期限切れジョブのクリーンアップ
    cleanup_expired_jobs()

    # ファイル拡張子チェック
    if not file.filename.lower().endswith(('.las', '.laz')):
        raise HTTPException(status_code=400, detail="LASまたはLAZファイルのみ対応しています")

    # 系番号チェック
    if zone < 1 or zone > 19:
        raise HTTPException(status_code=400, detail="系番号は1-19の範囲で指定してください")

    # 高さタイプチェック
    valid_types = ["ellipsoid", "geoid2024", "geoid2011"]
    if input_height_type not in valid_types or output_height_type not in valid_types:
        raise HTTPException(status_code=400, detail="高さタイプはellipsoid/geoid2024/geoid2011のいずれかを指定してください")

    if input_height_type == output_height_type:
        raise HTTPException(status_code=400, detail="入力と出力の高さタイプが同じです")

    # ジョブID生成
    job_id = str(uuid.uuid4())

    # ファイル保存
    input_path = LAS_UPLOAD_DIR / f"{job_id}.las"
    output_path = LAS_OUTPUT_DIR / f"{job_id}.las"

    try:
        with open(input_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ファイル保存に失敗しました: {e}")

    # LASファイル情報取得
    try:
        info = get_las_info(input_path)
    except Exception as e:
        input_path.unlink()
        raise HTTPException(status_code=400, detail=f"LASファイルの読み込みに失敗しました: {e}")

    # ジョブ作成
    now = datetime.now()
    expires_at = now + timedelta(days=JOB_EXPIRY_DAYS)

    jobs = load_jobs()
    jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "filename": file.filename,
        "point_count": info.point_count,
        "zone": zone,
        "input_height_type": input_height_type,
        "output_height_type": output_height_type,
        "use_island_correction": use_island_correction,
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "progress": 0.0,
        "error": None,
        "stats": None
    }
    save_jobs(jobs)

    # バックグラウンド処理開始
    background_tasks.add_task(
        process_las_background,
        job_id,
        input_path,
        output_path,
        zone,
        input_height_type,
        output_height_type,
        use_island_correction
    )

    return LASUploadResponse(
        job_id=job_id,
        filename=file.filename,
        point_count=info.point_count,
        area_km2=info.area_km2,
        estimated_time="処理中...",
        message=f"ジョブを開始しました。{info.point_count:,}点を処理します。"
    )


@app.get("/las/job/{job_id}", response_model=LASJobInfo)
def get_job_status(job_id: str):
    """ジョブの状態を取得"""
    jobs = load_jobs()

    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")

    job = jobs[job_id]
    return LASJobInfo(
        job_id=job["job_id"],
        status=job["status"],
        filename=job["filename"],
        point_count=job["point_count"],
        created_at=job["created_at"],
        expires_at=job["expires_at"],
        progress=job["progress"],
        error=job.get("error"),
        stats=job.get("stats")
    )


@app.get("/las/download/{job_id}")
def download_las(job_id: str):
    """処理済みLASファイルをダウンロード"""
    jobs = load_jobs()

    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")

    job = jobs[job_id]

    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail=f"ジョブはまだ完了していません（状態: {job['status']}）")

    output_path = LAS_OUTPUT_DIR / f"{job_id}.las"

    if not output_path.exists():
        raise HTTPException(status_code=404, detail="出力ファイルが見つかりません")

    # ダウンロードファイル名を生成
    original_name = Path(job["filename"]).stem
    download_name = f"{original_name}_converted.las"

    return FileResponse(
        path=output_path,
        filename=download_name,
        media_type="application/octet-stream"
    )


@app.get("/las/jobs")
def list_jobs():
    """全ジョブの一覧を取得"""
    cleanup_expired_jobs()
    jobs = load_jobs()
    return {"jobs": list(jobs.values())}


@app.delete("/las/job/{job_id}")
def delete_job(job_id: str):
    """ジョブを削除"""
    jobs = load_jobs()

    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")

    # ファイル削除
    input_file = LAS_UPLOAD_DIR / f"{job_id}.las"
    output_file = LAS_OUTPUT_DIR / f"{job_id}.las"
    if input_file.exists():
        input_file.unlink()
    if output_file.exists():
        output_file.unlink()

    del jobs[job_id]
    save_jobs(jobs)

    return {"message": "ジョブを削除しました"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
