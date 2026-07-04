# API台帳

- データ状態: production
- 取込元: claude-design-bundle
- 取込日: 2026-07-04
- 登録件数: 50件

| ID | 名称 | カテゴリ | 提供元 | 形式 | APIキー | 信頼度 | 優先度 | 状態 | 最新検証 | 利用説明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GSI-TILE-STD-001 | 地理院標準地図タイル | 地図 | 国土地理院 | XYZ Tile, PNG | not_required | A | 5 | 本格利用候補 | success | 国内案件の共通ベースマップとして最優先で利用します。現場位置、候補地、リスクレイヤを重ねる土台になります。 |
| GSI-TILE-PALE-001 | 地理院淡色地図タイル | 地図 | 国土地理院 | XYZ Tile, PNG | not_required | A | 5 | 接続検証済 | success | 背景地図、位置確認、現地概況の把握に利用します。Web地図や台帳画面のベースレイヤとして扱いやすいデータです。 |
| GSI-TILE-PHOTO-001 | 地理院写真タイル | 地図 | 国土地理院 | XYZ Tile, JPEG | not_required | A | 4 | 接続検証済 | success | 背景地図、位置確認、現地概況の把握に利用します。Web地図や台帳画面のベースレイヤとして扱いやすいデータです。 |
| GSI-ELEVATION-001 | 地理院標高タイル | 地形 | 国土地理院 | XYZ Tile, DEM, PNG | not_required | A | 5 | 実装接続済 | success | 候補地の標高、周辺地形、概略勾配の把握に使います。造成、排水、災害リスクの初期確認に役立ちます。 |
| GSI-VECTOR-001 | 地理院Vector | 地形 | 国土地理院 | Vector Tile, PBF | not_required | A | 4 | 接続候補 | success | 標高、地形、勾配、地盤・施工条件の初期確認に利用します。候補地比較や危険箇所の一次把握に向きます。 |
| MLIT-KSJ-N03-001 | 国土数値情報 行政区域 | 行政 | 国土交通省 | GeoJSON, GML, SHP | not_required | A | 5 | 本格利用候補 | success | 住所・座標を行政区域にひも付ける基礎データです。案件管理、地域別集計、許認可確認の起点になります。 |
| MLIT-KSJ-L03-001 | 国土数値情報 土地利用細分メッシュ | 土地 | 国土交通省 | GeoJSON, GML, SHP | not_required | A | 4 | 接続候補 | success | 土地利用やメッシュ情報を用いて、候補地の周辺特性や利用状況を把握します。計画初期の比較検討に向きます。 |
| MLIT-KSJ-A09-001 | 国土数値情報 都市地域 | 都市 | 国土交通省 | GeoJSON, GML, SHP | not_required | A | 4 | 接続候補 | success | 都市計画、用途地域、規制確認の入口として利用します。詳細判断では自治体の公式資料と照合してください。 |
| MLIT-KSJ-ROAD-001 | 国土数値情報 道路密度・道路延長 | 交通 | 国土交通省 | GeoJSON, GML, SHP | not_required | B | 3 | 接続候補 | success | 道路、鉄道、港湾、空港などの交通・物流条件を確認します。搬入ルート、近接施工、制限確認の初期調査に使います。 |
| MLIT-KSJ-RAIL-001 | 国土数値情報 鉄道 | 交通 | 国土交通省 | GeoJSON, GML, SHP | not_required | B | 3 | 接続候補 | success | 道路、鉄道、港湾、空港などの交通・物流条件を確認します。搬入ルート、近接施工、制限確認の初期調査に使います。 |
| MLIT-KSJ-PORT-001 | 国土数値情報 港湾 | 交通 | 国土交通省 | GeoJSON, GML, SHP | not_required | A | 4 | 接続候補 | success | 道路、鉄道、港湾、空港などの交通・物流条件を確認します。搬入ルート、近接施工、制限確認の初期調査に使います。 |
| MLIT-KSJ-AIRPORT-001 | 国土数値情報 空港 | 交通 | 国土交通省 | GeoJSON, GML, SHP | not_required | B | 3 | 接続候補 | success | 道路、鉄道、港湾、空港などの交通・物流条件を確認します。搬入ルート、近接施工、制限確認の初期調査に使います。 |
| MLIT-KSJ-FLOOD-001 | 国土数値情報 洪水浸水想定区域 | 防災 | 国土交通省 | GeoJSON, GML, SHP | not_required | A | 5 | 接続検証済 | success | 洪水、土砂災害、津波、高潮などの災害リスクを地図上で確認します。現場安全、候補地評価、防災計画の初期判断に使います。 |
| MLIT-KSJ-LANDSLIDE-001 | 国土数値情報 土砂災害警戒区域 | 防災 | 国土交通省 | GeoJSON, GML, SHP | not_required | A | 5 | 接続候補 | success | 洪水、土砂災害、津波、高潮などの災害リスクを地図上で確認します。現場安全、候補地評価、防災計画の初期判断に使います。 |
| MLIT-KSJ-TSUNAMI-001 | 国土数値情報 津波浸水想定 | 防災 | 国土交通省 | GeoJSON, GML, SHP | not_required | A | 4 | 接続候補 | success | 洪水、土砂災害、津波、高潮などの災害リスクを地図上で確認します。現場安全、候補地評価、防災計画の初期判断に使います。 |
| MLIT-KSJ-STORM-SURGE-001 | 国土数値情報 高潮浸水想定 | 防災 | 国土交通省 | GeoJSON, GML, SHP | not_required | A | 4 | 接続候補 | success | 洪水、土砂災害、津波、高潮などの災害リスクを地図上で確認します。現場安全、候補地評価、防災計画の初期判断に使います。 |
| GSI-HAZARD-FLOOD-001 | ハザードマップ洪水タイル | 防災 | 国土地理院/国土交通省 | XYZ Tile, PNG | not_required | A | 5 | 実装接続済 | success | 洪水浸水想定をWeb地図上に重ね、候補地や現場周辺のリスクを直感的に確認します。 |
| GSI-HAZARD-LANDSLIDE-001 | ハザードマップ土砂災害タイル | 防災 | 国土地理院/国土交通省 | XYZ Tile, PNG | not_required | A | 4 | 接続候補 | success | 洪水、土砂災害、津波、高潮などの災害リスクを地図上で確認します。現場安全、候補地評価、防災計画の初期判断に使います。 |
| GSI-HAZARD-TSUNAMI-001 | ハザードマップ津波タイル | 防災 | 国土地理院/国土交通省 | XYZ Tile, PNG | not_required | A | 4 | 接続候補 | success | 洪水、土砂災害、津波、高潮などの災害リスクを地図上で確認します。現場安全、候補地評価、防災計画の初期判断に使います。 |
| GSI-HAZARD-STORM-SURGE-001 | ハザードマップ高潮タイル | 防災 | 国土地理院/国土交通省 | XYZ Tile, PNG | not_required | A | 4 | 接続候補 | success | 洪水、土砂災害、津波、高潮などの災害リスクを地図上で確認します。現場安全、候補地評価、防災計画の初期判断に使います。 |
| MLIT-REINFOLIB-LANDPRICE-001 | 不動産情報ライブラリ 地価公示 | 不動産 | 国土交通省 | API, GeoJSON, PBF | unknown | A | 4 | 接続検証済 | - | 地価、取引価格、周辺施設などを確認し、候補地評価や事業性検討の参考にします。利用条件とAPIキー要否を必ず確認してください。 |
| MLIT-REINFOLIB-LANDPRICE-LOCAL-001 | 不動産情報ライブラリ 地価調査 | 不動産 | 国土交通省 | API, GeoJSON, PBF | unknown | A | 3 | 調査中 | - | 地価、取引価格、周辺施設などを確認し、候補地評価や事業性検討の参考にします。利用条件とAPIキー要否を必ず確認してください。 |
| MLIT-REINFOLIB-TRADE-001 | 不動産情報ライブラリ 不動産取引価格 | 不動産 | 国土交通省 | API, JSON | unknown | B | 3 | 調査中 | - | 地価、取引価格、周辺施設などを確認し、候補地評価や事業性検討の参考にします。利用条件とAPIキー要否を必ず確認してください。 |
| MLIT-REINFOLIB-CITYPLAN-001 | 不動産情報ライブラリ 都市計画 | 都市 | 国土交通省 | API, GeoJSON, PBF | unknown | A | 4 | 調査中 | - | 都市計画、用途地域、規制確認の入口として利用します。詳細判断では自治体の公式資料と照合してください。 |
| MLIT-REINFOLIB-SCHOOL-001 | 不動産情報ライブラリ 学校 | 周辺 | 国土交通省 | API, GeoJSON, PBF | unknown | C | 2 | 調査中 | - | 学校、医療機関など周辺施設の把握に利用します。工事影響、生活環境、説明資料作成の補助情報です。 |
| MLIT-REINFOLIB-MEDICAL-001 | 不動産情報ライブラリ 医療機関 | 周辺 | 国土交通省 | API, GeoJSON, PBF | unknown | C | 2 | 調査中 | - | 学校、医療機関など周辺施設の把握に利用します。工事影響、生活環境、説明資料作成の補助情報です。 |
| MLIT-PLATEAU-001 | PLATEAU 3D都市モデル | 3D都市 | 国土交通省 | CityGML, 3D Tiles, GeoJSON | not_required | A | 4 | 接続検証済 | success | 都市スケールの3D確認、BIM/CIM連携、景観・日影・都市空間検討の基礎データとして使います。 |
| MLIT-PLATEAU-SDK-001 | PLATEAU SDK/ユースケースデータ | 3D都市 | 国土交通省 | SDK, Sample Data | not_required | B | 3 | 接続候補 | success | 3D都市モデルやCityGMLを使い、景観、BIM/CIM、都市スケールの空間検討に利用します。大容量データのため範囲を絞って扱います。 |
| JMA-FORECAST-001 | 気象庁 天気予報JSON | 気象 | 気象庁 | JSON | not_required | B | 5 | 本格利用候補 | success | 施工可否、作業計画、現場安全確認に使う天気予報データです。地域コードを指定して予報情報を取得します。 |
| JMA-AMEDAS-001 | 気象庁 アメダスJSON | 気象 | 気象庁 | JSON | not_required | B | 4 | 接続候補 | success | 天気、観測、警報、台風などを確認し、施工判断、現場安全、工程調整に利用します。仕様変更や速報性の扱いに注意します。 |
| JMA-WARNING-001 | 気象庁 警報注意報JSON | 気象 | 気象庁 | JSON | not_required | B | 4 | 接続候補 | success | 天気、観測、警報、台風などを確認し、施工判断、現場安全、工程調整に利用します。仕様変更や速報性の扱いに注意します。 |
| JMA-EARTHQUAKE-001 | 気象庁 地震情報 | 気象 | 気象庁 | XML, JSON相当 | not_required | B | 3 | 調査中 | success | 天気、観測、警報、台風などを確認し、施工判断、現場安全、工程調整に利用します。仕様変更や速報性の扱いに注意します。 |
| JMA-TYPHOON-001 | 気象庁 台風情報 | 気象 | 気象庁 | JSON相当, XML相当 | not_required | B | 3 | 調査中 | failure | 天気、観測、警報、台風などを確認し、施工判断、現場安全、工程調整に利用します。仕様変更や速報性の扱いに注意します。 |
| MLIT-WATER-RAIN-001 | 水文水質データベース 雨量 | 河川 | 国土交通省 | Web, CSV相当 | not_required | B | 3 | 調査中 | - | 雨量、水位、流量、河川防災情報を確認し、出水リスクや河川工事の判断材料にします。リアルタイム性と公式発表の扱いを確認します。 |
| MLIT-WATER-LEVEL-001 | 水文水質データベース 水位 | 河川 | 国土交通省 | Web, CSV相当 | not_required | B | 3 | 調査中 | - | 雨量、水位、流量、河川防災情報を確認し、出水リスクや河川工事の判断材料にします。リアルタイム性と公式発表の扱いを確認します。 |
| MLIT-WATER-FLOW-001 | 水文水質データベース 流量 | 河川 | 国土交通省 | Web, CSV相当 | not_required | C | 2 | 調査中 | - | 雨量、水位、流量、河川防災情報を確認し、出水リスクや河川工事の判断材料にします。リアルタイム性と公式発表の扱いを確認します。 |
| MLIT-RIVER-DISASTER-001 | 川の防災情報 | 河川 | 国土交通省 | Web, 地図 | not_required | B | 3 | 調査中 | - | 雨量、水位、流量、河川防災情報を確認し、出水リスクや河川工事の判断材料にします。リアルタイム性と公式発表の扱いを確認します。 |
| JCG-UMISHIRU-001 | 海上保安庁 海しる | 海象 | 海上保安庁 | API, 地図, データ | unknown | A | 3 | 調査中 | - | 海洋、波浪、潮位などを確認し、港湾・海洋土木の施工判断や安全確認に利用します。観測地点と利用条件を確認します。 |
| NOWPHAS-WAVE-001 | NOWPHAS 港湾波浪情報 | 海象 | 港湾空港技術研究所等 | Web, CSV相当 | unknown | A | 3 | 調査中 | - | 海洋、波浪、潮位などを確認し、港湾・海洋土木の施工判断や安全確認に利用します。観測地点と利用条件を確認します。 |
| MOE-AIR-POLLUTION-001 | 環境省 大気汚染物質広域監視 | 環境 | 環境省 | Web, CSV相当 | not_required | B | 2 | 調査中 | - | 大気、水質、環境監視などを確認し、環境影響や安全配慮の参考情報として利用します。公式データの取得条件を確認します。 |
| OSM-OVERPASS-001 | OpenStreetMap Overpass API | 国際地図 | OSM | Overpass QL, JSON, XML | not_required | B | 3 | 接続候補 | success | 海外案件や国内データの補完に使う地図・地物データです。利用ポリシー、アクセス制限、ライセンスを確認してください。 |
| OSM-TILE-001 | OSM Tile | 国際地図 | OSM | XYZ Tile, PNG | not_required | B | 2 | 調査中 | success | 海外案件や国内データの補完に使う地図・地物データです。利用ポリシー、アクセス制限、ライセンスを確認してください。 |
| OPENTOPOGRAPHY-API-001 | OpenTopography API | 国際地形 | OpenTopography | REST, GeoTIFF | unknown | B | 2 | 調査中 | - | 海外の標高・地形データを取得し、広域地形解析や比較研究に利用します。データセットごとのライセンスを確認します。 |
| OVERTURE-MAPS-001 | Overture Maps | 国際建物 | Overture Maps Foundation | Parquet, GeoParquet | not_required | B | 3 | 調査中 | - | 海外の建物・基盤地物データを使い、都市分析や海外案件の初期調査に利用します。大容量データの抽出設計が必要です。 |
| NOAA-NWS-001 | NOAA NWS API | 国際気象 | NOAA/NWS | REST, JSON-LD | not_required | B | 3 | 接続検証済 | success | 米国の天気・予報APIとして、海外案件やAPI設計比較に使います。JSON-LDで地点情報から予報系データへ接続できます。 |
| NOAA-CDO-001 | NOAA Climate Data Online API | 国際気象 | NOAA/NCEI | REST, JSON | required | C | 2 | 保留 | - | 海外気象・気候データを使い、海外案件や比較研究の気象条件を確認します。User-AgentやAPIキー要件に注意します。 |
| USGS-WATER-001 | USGS Water Data APIs | 国際水文 | USGS | REST, JSON | not_required | A | 4 | 接続検証済 | success | 米国の水位・流量データを取得し、海外水文データの比較、研究、サンプル実装に使います。 |
| USGS-EARTHQUAKE-001 | USGS Earthquake API | 国際災害 | USGS | GeoJSON | not_required | A | 3 | 接続候補 | success | 地震など国際的な災害データを使い、広域リスク把握や研究に利用します。国内公式情報とは用途を分けます。 |
| OPENAQ-API-001 | OpenAQ API | 国際環境 | OpenAQ | REST, JSON | unknown | B | 2 | 調査中 | - | 海外・国際的な環境観測データを使い、大気環境や環境比較に利用します。APIバージョンと認証要件を確認してください。 |
| NASA-FIRMS-001 | NASA Earthdata / FIRMS | 衛星 | NASA | API, GeoJSON, CSV | required | C | 2 | 保留 | - | 衛星観測、火災、災害関連データを使い、広域監視や災害初動の参考にします。APIキーと利用条件の確認が必要です。 |
