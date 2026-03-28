"""
LASファイル処理モジュール
- バウンディングボックスから処理戦略を決定
- チャンク処理で大容量ファイルに対応
- ジオイド高のキャッシュで高速化
"""
import laspy
import numpy as np
from pathlib import Path
from dataclasses import dataclass
from typing import Generator
import tempfile
import shutil

from geoid_loader import GeoidManager
from coordinate import plane_to_latlon


@dataclass
class LASInfo:
    """LASファイルの情報"""
    point_count: int
    min_x: float
    max_x: float
    min_y: float
    max_y: float
    min_z: float
    max_z: float
    version: str
    point_format: int

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    @property
    def area_km2(self) -> float:
        return (self.width * self.height) / 1_000_000


@dataclass
class ProcessingStats:
    """処理統計"""
    total_points: int
    processed_points: int
    failed_points: int  # ジオイド高取得失敗
    min_correction: float
    max_correction: float
    avg_correction: float


def get_las_info(filepath: Path) -> LASInfo:
    """
    LASファイルのヘッダー情報を取得（点群データは読まない）

    Args:
        filepath: LASファイルパス

    Returns:
        LASInfo オブジェクト
    """
    with laspy.open(filepath) as las_file:
        header = las_file.header
        return LASInfo(
            point_count=header.point_count,
            min_x=header.x_min,
            max_x=header.x_max,
            min_y=header.y_min,
            max_y=header.y_max,
            min_z=header.z_min,
            max_z=header.z_max,
            version=f"{header.version.major}.{header.version.minor}",
            point_format=header.point_format.id
        )


class GeoidCache:
    """
    ジオイド高のキャッシュ
    同じグリッド位置の点は同じジオイド高を使用
    """

    def __init__(self, geoid_manager: GeoidManager, precision: int = 4):
        """
        Args:
            geoid_manager: ジオイドデータマネージャー
            precision: キャッシュの精度（小数点以下桁数）
                       4 = 約10m精度、3 = 約100m精度
        """
        self.geoid_manager = geoid_manager
        self.precision = precision
        self._cache_2024: dict[tuple, float | None] = {}
        self._cache_2024_island: dict[tuple, float | None] = {}
        self._cache_2011: dict[tuple, float | None] = {}
        self.hit_count = 0
        self.miss_count = 0

    def _make_key(self, lat: float, lon: float) -> tuple:
        return (round(lat, self.precision), round(lon, self.precision))

    def get_geoid2024(self, lat: float, lon: float, use_island: bool = False) -> float | None:
        key = self._make_key(lat, lon)
        cache = self._cache_2024_island if use_island else self._cache_2024

        if key in cache:
            self.hit_count += 1
            return cache[key]

        self.miss_count += 1
        value = self.geoid_manager.get_geoid2024_height(lat, lon, use_island_correction=use_island)
        cache[key] = value
        return value

    def get_geoid2011(self, lat: float, lon: float) -> float | None:
        key = self._make_key(lat, lon)

        if key in self._cache_2011:
            self.hit_count += 1
            return self._cache_2011[key]

        self.miss_count += 1
        value = self.geoid_manager.get_geoid2011_height(lat, lon)
        self._cache_2011[key] = value
        return value

    @property
    def hit_rate(self) -> float:
        total = self.hit_count + self.miss_count
        return self.hit_count / total if total > 0 else 0


def process_las_chunk(
    x_coords: np.ndarray,
    y_coords: np.ndarray,
    z_coords: np.ndarray,
    zone: int,
    geoid_cache: GeoidCache,
    input_height_type: str,
    output_height_type: str,
    use_island_correction: bool = False
) -> tuple[np.ndarray, int]:
    """
    点群データのチャンクを処理

    Returns:
        (変換後のZ座標, 失敗点数)
    """
    new_z = np.copy(z_coords)
    failed_count = 0

    for i in range(len(z_coords)):
        # 平面直角座標 → 経緯度
        latlon = plane_to_latlon(x_coords[i], y_coords[i], zone)
        lat, lon = latlon.lat, latlon.lon

        # 離島チェック
        is_island = geoid_cache.geoid_manager.check_island(lat, lon) is not None
        use_island = use_island_correction and is_island

        # ジオイド高取得
        if output_height_type == "geoid2024" or input_height_type == "geoid2024":
            g2024 = geoid_cache.get_geoid2024(lat, lon, use_island)
        else:
            g2024 = None

        if output_height_type == "geoid2011" or input_height_type == "geoid2011":
            g2011 = geoid_cache.get_geoid2011(lat, lon)
        else:
            g2011 = None

        # 変換
        if input_height_type == "ellipsoid":
            if output_height_type == "geoid2024":
                if g2024 is not None:
                    new_z[i] = z_coords[i] - g2024
                else:
                    failed_count += 1
            elif output_height_type == "geoid2011":
                if g2011 is not None:
                    new_z[i] = z_coords[i] - g2011
                else:
                    failed_count += 1

        elif input_height_type == "geoid2024":
            if output_height_type == "ellipsoid":
                if g2024 is not None:
                    new_z[i] = z_coords[i] + g2024
                else:
                    failed_count += 1
            elif output_height_type == "geoid2011":
                if g2024 is not None and g2011 is not None:
                    ellipsoid_h = z_coords[i] + g2024
                    new_z[i] = ellipsoid_h - g2011
                else:
                    failed_count += 1

        elif input_height_type == "geoid2011":
            if output_height_type == "ellipsoid":
                if g2011 is not None:
                    new_z[i] = z_coords[i] + g2011
                else:
                    failed_count += 1
            elif output_height_type == "geoid2024":
                if g2011 is not None and g2024 is not None:
                    ellipsoid_h = z_coords[i] + g2011
                    new_z[i] = ellipsoid_h - g2024
                else:
                    failed_count += 1

    return new_z, failed_count


def process_las_file(
    input_path: Path,
    output_path: Path,
    zone: int,
    geoid_manager: GeoidManager,
    input_height_type: str = "ellipsoid",
    output_height_type: str = "geoid2024",
    use_island_correction: bool = False,
    chunk_size: int = 1_000_000,
    progress_callback: callable = None
) -> ProcessingStats:
    """
    LASファイルを変換

    Args:
        input_path: 入力LASファイル
        output_path: 出力LASファイル
        zone: 平面直角座標の系番号
        geoid_manager: ジオイドデータマネージャー
        input_height_type: 入力高さタイプ (ellipsoid/geoid2024/geoid2011)
        output_height_type: 出力高さタイプ
        use_island_correction: 離島補正を使用
        chunk_size: 一度に処理する点数
        progress_callback: 進捗コールバック (processed, total) -> None

    Returns:
        ProcessingStats
    """
    # ファイル情報取得
    info = get_las_info(input_path)

    # キャッシュ精度を範囲サイズで決定
    if info.width < 500 and info.height < 500:
        precision = 5  # 約1m精度（密なデータ向け）
    elif info.width < 5000 and info.height < 5000:
        precision = 4  # 約10m精度
    else:
        precision = 3  # 約100m精度（広域データ向け）

    geoid_cache = GeoidCache(geoid_manager, precision)

    # 統計
    total_points = 0
    failed_points = 0
    corrections = []

    # 入力ファイルを開く
    with laspy.open(input_path) as reader:
        # 出力ファイルの準備
        with laspy.open(output_path, mode='w', header=reader.header) as writer:

            # チャンクごとに処理
            for points in reader.chunk_iterator(chunk_size):
                x = points.x
                y = points.y
                z = points.z

                # 変換
                new_z, failed = process_las_chunk(
                    x, y, z, zone, geoid_cache,
                    input_height_type, output_height_type,
                    use_island_correction
                )

                # 補正量を記録
                corrections.extend((new_z - z).tolist())

                # Z座標を更新
                points.z = new_z

                # 書き込み
                writer.write_points(points)

                total_points += len(points)
                failed_points += failed

                # 進捗コールバック
                if progress_callback:
                    progress_callback(total_points, info.point_count)

    # 統計計算
    corrections = np.array(corrections)
    valid_corrections = corrections[~np.isnan(corrections)]

    return ProcessingStats(
        total_points=total_points,
        processed_points=total_points - failed_points,
        failed_points=failed_points,
        min_correction=float(valid_corrections.min()) if len(valid_corrections) > 0 else 0,
        max_correction=float(valid_corrections.max()) if len(valid_corrections) > 0 else 0,
        avg_correction=float(valid_corrections.mean()) if len(valid_corrections) > 0 else 0
    )
