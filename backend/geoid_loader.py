"""
ジオイドデータ読み込みモジュール
- JPGEO2024 (ISG形式)
- JPGEO2024+Hrefconv2024 (ISG形式、離島用)
- gsigeo2011 (ASC形式)
"""
import numpy as np
from dataclasses import dataclass
from pathlib import Path
import re


@dataclass
class GeoidGrid:
    """ジオイドグリッドデータ"""
    name: str
    lat_min: float  # 度
    lat_max: float  # 度
    lon_min: float  # 度
    lon_max: float  # 度
    delta_lat: float  # 度
    delta_lon: float  # 度
    nrows: int
    ncols: int
    nodata: float
    data: np.ndarray  # shape: (nrows, ncols)

    def get_geoid_height(self, lat: float, lon: float) -> float | None:
        """
        指定した緯度経度のジオイド高を双線形補間で取得

        Args:
            lat: 緯度（度）
            lon: 経度（度）

        Returns:
            ジオイド高（m）、範囲外またはnodataの場合はNone
        """
        # 範囲チェック
        if not (self.lat_min <= lat <= self.lat_max and
                self.lon_min <= lon <= self.lon_max):
            return None

        # グリッドインデックス計算（北から南へ並んでいる）
        row_f = (self.lat_max - lat) / self.delta_lat
        col_f = (lon - self.lon_min) / self.delta_lon

        row0 = int(row_f)
        col0 = int(col_f)

        # 境界処理
        row1 = min(row0 + 1, self.nrows - 1)
        col1 = min(col0 + 1, self.ncols - 1)

        # 双線形補間の重み
        dr = row_f - row0
        dc = col_f - col0

        # 4点の値を取得
        v00 = self.data[row0, col0]
        v01 = self.data[row0, col1]
        v10 = self.data[row1, col0]
        v11 = self.data[row1, col1]

        # nodataチェック（nodataに近い値を除外）
        def is_nodata(v):
            return abs(v - self.nodata) < 1.0

        if any(is_nodata(v) for v in [v00, v01, v10, v11]):
            return None

        # 双線形補間
        value = (v00 * (1 - dr) * (1 - dc) +
                 v01 * (1 - dr) * dc +
                 v10 * dr * (1 - dc) +
                 v11 * dr * dc)

        return float(value)


def parse_dms(dms_str: str) -> float:
    """度分秒文字列を度に変換 (例: "15°00'00\"" -> 15.0)"""
    match = re.match(r"(\d+)°(\d+)'(\d+)\"?", dms_str.strip())
    if match:
        d, m, s = map(int, match.groups())
        return d + m / 60 + s / 3600
    return float(dms_str)


def load_isg(filepath: Path) -> GeoidGrid:
    """ISG形式のジオイドデータを読み込む"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    header_end = content.find('end_of_head')
    header_section = content[:header_end]
    data_section = content[header_end:].split('\n', 1)[1]

    def get_value(key: str) -> str:
        pattern = rf"{key}\s*[:=]\s*(.+)"
        match = re.search(pattern, header_section, re.IGNORECASE)
        return match.group(1).strip() if match else ""

    name = get_value("model name")
    lat_min = parse_dms(get_value("lat min"))
    lat_max = parse_dms(get_value("lat max"))
    lon_min = parse_dms(get_value("lon min"))
    lon_max = parse_dms(get_value("lon max"))
    delta_lat = parse_dms(get_value("delta lat"))
    delta_lon = parse_dms(get_value("delta lon"))
    nrows = int(get_value("nrows"))
    ncols = int(get_value("ncols"))
    nodata = float(get_value("nodata"))

    values = []
    for line in data_section.strip().split('\n'):
        line = line.strip()
        if line:
            values.extend(map(float, line.split()))

    data = np.array(values).reshape(nrows, ncols)

    return GeoidGrid(
        name=name, lat_min=lat_min, lat_max=lat_max,
        lon_min=lon_min, lon_max=lon_max,
        delta_lat=delta_lat, delta_lon=delta_lon,
        nrows=nrows, ncols=ncols, nodata=nodata, data=data
    )


def load_asc(filepath: Path) -> GeoidGrid:
    """ASC形式のジオイドデータ（gsigeo2011）を読み込む"""
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    header = lines[0].split()
    lat_min = float(header[0])
    lon_min = float(header[1])
    delta_lat = float(header[2])
    delta_lon = float(header[3])
    nrows = int(header[4])
    ncols = int(header[5])

    lat_max = lat_min + delta_lat * (nrows - 1)
    lon_max = lon_min + delta_lon * (ncols - 1)

    values = []
    for line in lines[1:]:
        line = line.strip()
        if line:
            values.extend(map(float, line.split()))

    data = np.array(values).reshape(nrows, ncols)
    data = np.flipud(data)  # 南→北を北→南に反転

    return GeoidGrid(
        name="gsigeo2011_ver2_2",
        lat_min=lat_min, lat_max=lat_max,
        lon_min=lon_min, lon_max=lon_max,
        delta_lat=delta_lat, delta_lon=delta_lon,
        nrows=nrows, ncols=ncols, nodata=999.0, data=data
    )


# 離島判定用の大まかな範囲（本土外）
ISLAND_REGIONS = [
    # 沖縄本島以南
    {"name": "沖縄・先島諸島", "lat_max": 27.0, "lon_min": 122.0, "lon_max": 132.0},
    # 小笠原諸島
    {"name": "小笠原諸島", "lat_min": 24.0, "lat_max": 28.0, "lon_min": 140.0, "lon_max": 143.0},
    # 南鳥島
    {"name": "南鳥島", "lat_min": 24.0, "lat_max": 25.0, "lon_min": 153.0, "lon_max": 155.0},
]


def is_island_region(lat: float, lon: float) -> str | None:
    """
    離島地域かどうかを判定

    Returns:
        離島地域名（離島の場合）、本土の場合はNone
    """
    for region in ISLAND_REGIONS:
        lat_min = region.get("lat_min", 0)
        lat_max = region.get("lat_max", 90)
        lon_min = region.get("lon_min", 0)
        lon_max = region.get("lon_max", 180)

        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return region["name"]
    return None


class GeoidManager:
    """ジオイドデータ管理クラス"""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self._geoid2024: GeoidGrid | None = None
        self._geoid2024_island: GeoidGrid | None = None
        self._geoid2011: GeoidGrid | None = None

    @property
    def geoid2024(self) -> GeoidGrid:
        """JPGEO2024（本土用）"""
        if self._geoid2024 is None:
            self._geoid2024 = load_isg(
                self.base_path / "gsigeoid2024" / "JPGEO2024.isg"
            )
        return self._geoid2024

    @property
    def geoid2024_island(self) -> GeoidGrid:
        """JPGEO2024+Hrefconv2024（離島用）"""
        if self._geoid2024_island is None:
            self._geoid2024_island = load_isg(
                self.base_path / "gsigeoid2024" / "JPGEO2024+Hrefconv2024.isg"
            )
        return self._geoid2024_island

    @property
    def geoid2011(self) -> GeoidGrid:
        """gsigeo2011"""
        if self._geoid2011 is None:
            self._geoid2011 = load_asc(
                self.base_path / "gsigeo2011_ver2_2_asc" / "program" / "gsigeo2011_ver2_2.asc"
            )
        return self._geoid2011

    def get_geoid2024_height(self, lat: float, lon: float, use_island_correction: bool = False) -> float | None:
        """
        ジオイド2024高を取得

        Args:
            lat: 緯度（度）
            lon: 経度（度）
            use_island_correction: 離島補正を使用するか

        Returns:
            ジオイド高（m）
        """
        if use_island_correction:
            return self.geoid2024_island.get_geoid_height(lat, lon)
        return self.geoid2024.get_geoid_height(lat, lon)

    def get_geoid2011_height(self, lat: float, lon: float) -> float | None:
        """ジオイド2011高を取得"""
        return self.geoid2011.get_geoid_height(lat, lon)

    def check_island(self, lat: float, lon: float) -> str | None:
        """離島地域かどうかをチェック"""
        return is_island_region(lat, lon)
