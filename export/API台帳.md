# API台帳

| ID | 名称 | カテゴリ | 提供元 | 形式 | APIキー | 信頼度 | 優先度 | 状態 | 最新検証 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GSI-TILE-STD-001 | 地理院標準地図タイル | 地図 | 国土地理院 | XYZ Tile, PNG | not_required | A | 5 | 本格利用候補 | success |
| GSI-TILE-PALE-001 | 地理院淡色地図タイル | 地図 | 国土地理院 | XYZ Tile, PNG | not_required | A | 5 | 接続検証済 | - |
| GSI-TILE-PHOTO-001 | 地理院写真タイル | 地図 | 国土地理院 | XYZ Tile, JPEG | not_required | A | 4 | 接続検証済 | - |
| GSI-ELEVATION-001 | 地理院標高タイル | 地形 | 国土地理院 | XYZ Tile, DEM, PNG | not_required | A | 5 | 実装接続済 | success |
| GSI-VECTOR-001 | 地理院Vector | 地形 | 国土地理院 | Vector Tile, PBF | not_required | A | 4 | 接続候補 | - |
| MLIT-KSJ-N03-001 | 国土数値情報 行政区域 | 行政 | 国土交通省 | GeoJSON, GML, SHP | not_required | A | 5 | 本格利用候補 | warning |
| MLIT-KSJ-L03-001 | 国土数値情報 土地利用細分メッシュ | 土地 | 国土交通省 | GeoJSON, GML, SHP | not_required | A | 4 | 接続候補 | - |
| MLIT-KSJ-A09-001 | 国土数値情報 都市地域 | 都市 | 国土交通省 | GeoJSON, GML, SHP | not_required | A | 4 | 接続候補 | - |
| MLIT-KSJ-ROAD-001 | 国土数値情報 道路密度・道路延長 | 交通 | 国土交通省 | GeoJSON, GML, SHP | not_required | B | 3 | 接続候補 | - |
| MLIT-KSJ-RAIL-001 | 国土数値情報 鉄道 | 交通 | 国土交通省 | GeoJSON, GML, SHP | not_required | B | 3 | 接続候補 | - |
| MLIT-KSJ-PORT-001 | 国土数値情報 港湾 | 交通 | 国土交通省 | GeoJSON, GML, SHP | not_required | A | 4 | 接続候補 | - |
| MLIT-KSJ-AIRPORT-001 | 国土数値情報 空港 | 交通 | 国土交通省 | GeoJSON, GML, SHP | not_required | B | 3 | 接続候補 | - |
| MLIT-KSJ-FLOOD-001 | 国土数値情報 洪水浸水想定区域 | 防災 | 国土交通省 | GeoJSON, GML, SHP | not_required | A | 5 | 接続検証済 | warning |
| MLIT-KSJ-LANDSLIDE-001 | 国土数値情報 土砂災害警戒区域 | 防災 | 国土交通省 | GeoJSON, GML, SHP | not_required | A | 5 | 接続候補 | - |
| MLIT-KSJ-TSUNAMI-001 | 国土数値情報 津波浸水想定 | 防災 | 国土交通省 | GeoJSON, GML, SHP | not_required | A | 4 | 接続候補 | - |
| MLIT-KSJ-STORM-SURGE-001 | 国土数値情報 高潮浸水想定 | 防災 | 国土交通省 | GeoJSON, GML, SHP | not_required | A | 4 | 接続候補 | - |
| GSI-HAZARD-FLOOD-001 | ハザードマップ洪水タイル | 防災 | 国土地理院/国土交通省 | XYZ Tile, PNG | not_required | A | 5 | 実装接続済 | success |
| GSI-HAZARD-LANDSLIDE-001 | ハザードマップ土砂災害タイル | 防災 | 国土地理院/国土交通省 | XYZ Tile, PNG | not_required | A | 4 | 接続候補 | - |
| GSI-HAZARD-TSUNAMI-001 | ハザードマップ津波タイル | 防災 | 国土地理院/国土交通省 | XYZ Tile, PNG | not_required | A | 4 | 接続候補 | - |
| GSI-HAZARD-STORM-SURGE-001 | ハザードマップ高潮タイル | 防災 | 国土地理院/国土交通省 | XYZ Tile, PNG | not_required | A | 4 | 接続候補 | - |
| MLIT-REINFOLIB-LANDPRICE-001 | 不動産情報ライブラリ 地価公示 | 不動産 | 国土交通省 | API, GeoJSON, PBF | unknown | A | 4 | 接続検証済 | skipped |
| MLIT-REINFOLIB-LANDPRICE-LOCAL-001 | 不動産情報ライブラリ 地価調査 | 不動産 | 国土交通省 | API, GeoJSON, PBF | unknown | A | 3 | 調査中 | - |
| MLIT-REINFOLIB-TRADE-001 | 不動産情報ライブラリ 不動産取引価格 | 不動産 | 国土交通省 | API, JSON | unknown | B | 3 | 調査中 | - |
| MLIT-REINFOLIB-CITYPLAN-001 | 不動産情報ライブラリ 都市計画 | 都市 | 国土交通省 | API, GeoJSON, PBF | unknown | A | 4 | 調査中 | - |
| MLIT-REINFOLIB-SCHOOL-001 | 不動産情報ライブラリ 学校 | 周辺 | 国土交通省 | API, GeoJSON, PBF | unknown | C | 2 | 調査中 | - |
| MLIT-REINFOLIB-MEDICAL-001 | 不動産情報ライブラリ 医療機関 | 周辺 | 国土交通省 | API, GeoJSON, PBF | unknown | C | 2 | 調査中 | - |
| MLIT-PLATEAU-001 | PLATEAU 3D都市モデル | 3D都市 | 国土交通省 | CityGML, 3D Tiles, GeoJSON | not_required | A | 4 | 接続検証済 | warning |
| MLIT-PLATEAU-SDK-001 | PLATEAU SDK/ユースケースデータ | 3D都市 | 国土交通省 | SDK, Sample Data | not_required | B | 3 | 接続候補 | - |
| JMA-FORECAST-001 | 気象庁 天気予報JSON | 気象 | 気象庁 | JSON | not_required | B | 5 | 本格利用候補 | success |
| JMA-AMEDAS-001 | 気象庁 アメダスJSON | 気象 | 気象庁 | JSON | not_required | B | 4 | 接続候補 | - |
| JMA-WARNING-001 | 気象庁 警報注意報JSON | 気象 | 気象庁 | JSON | not_required | B | 4 | 接続候補 | - |
| JMA-EARTHQUAKE-001 | 気象庁 地震情報 | 気象 | 気象庁 | XML, JSON相当 | not_required | B | 3 | 調査中 | - |
| JMA-TYPHOON-001 | 気象庁 台風情報 | 気象 | 気象庁 | JSON相当, XML相当 | not_required | B | 3 | 調査中 | - |
| MLIT-WATER-RAIN-001 | 水文水質データベース 雨量 | 河川 | 国土交通省 | Web, CSV相当 | not_required | B | 3 | 調査中 | - |
| MLIT-WATER-LEVEL-001 | 水文水質データベース 水位 | 河川 | 国土交通省 | Web, CSV相当 | not_required | B | 3 | 調査中 | - |
| MLIT-WATER-FLOW-001 | 水文水質データベース 流量 | 河川 | 国土交通省 | Web, CSV相当 | not_required | C | 2 | 調査中 | - |
| MLIT-RIVER-DISASTER-001 | 川の防災情報 | 河川 | 国土交通省 | Web, 地図 | not_required | B | 3 | 調査中 | - |
| JCG-UMISHIRU-001 | 海上保安庁 海しる | 海象 | 海上保安庁 | API, 地図, データ | unknown | A | 3 | 調査中 | - |
| NOWPHAS-WAVE-001 | NOWPHAS 港湾波浪情報 | 海象 | 港湾空港技術研究所等 | Web, CSV相当 | unknown | A | 3 | 調査中 | - |
| MOE-AIR-POLLUTION-001 | 環境省 大気汚染物質広域監視 | 環境 | 環境省 | Web, CSV相当 | not_required | B | 2 | 調査中 | - |
| OSM-OVERPASS-001 | OpenStreetMap Overpass API | 国際地図 | OSM | Overpass QL, JSON, XML | not_required | B | 3 | 接続候補 | - |
| OSM-TILE-001 | OSM Tile | 国際地図 | OSM | XYZ Tile, PNG | not_required | B | 2 | 調査中 | - |
| OPENTOPOGRAPHY-API-001 | OpenTopography API | 国際地形 | OpenTopography | REST, GeoTIFF | unknown | B | 2 | 調査中 | - |
| OVERTURE-MAPS-001 | Overture Maps | 国際建物 | Overture Maps Foundation | Parquet, GeoParquet | not_required | B | 3 | 調査中 | - |
| NOAA-NWS-001 | NOAA NWS API | 国際気象 | NOAA/NWS | REST, JSON-LD | not_required | B | 3 | 接続検証済 | success |
| NOAA-CDO-001 | NOAA Climate Data Online API | 国際気象 | NOAA/NCEI | REST, JSON | required | C | 2 | 保留 | - |
| USGS-WATER-001 | USGS Water Data APIs | 国際水文 | USGS | REST, JSON | not_required | A | 4 | 接続検証済 | success |
| USGS-EARTHQUAKE-001 | USGS Earthquake API | 国際災害 | USGS | GeoJSON | not_required | A | 3 | 接続候補 | - |
| OPENAQ-API-001 | OpenAQ API | 国際環境 | OpenAQ | REST, JSON | unknown | B | 2 | 調査中 | - |
| NASA-FIRMS-001 | NASA Earthdata / FIRMS | 衛星 | NASA | API, GeoJSON, CSV | required | C | 2 | 保留 | - |
