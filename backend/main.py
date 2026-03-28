"""
ジオイド変換 WebAPI
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
from enum import Enum

from geoid_loader import GeoidManager
from coordinate import latlon_to_plane, plane_to_latlon, get_zone_name, PLANE_ORIGINS

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
import os
BASE_PATH = Path(os.environ.get("GEOID_DATA_PATH", Path(__file__).parent.parent))
geoid_manager = GeoidManager(BASE_PATH)


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
