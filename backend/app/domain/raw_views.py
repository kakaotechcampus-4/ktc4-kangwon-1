VIEWS = {
    "v_raw_stores": "commercial_area",
    "v_raw_lifecycle": "business_lifecycle",
    "v_raw_floating": "floating_population",
    "v_raw_resident": "resident_population",
    "v_raw_worker": "worker_population",
    "v_raw_map": "map",
    "v_raw_regulation": "regulation",
}


LOCAL_VIEWS = set(VIEWS) | {"v_ref_district_counts"}
FIELDS = {
    "store_count": ("SIMILR_INDUTY_STOR_CO", "store_count", "개"),
    "opening_count": ("OPBIZ_STOR_CO", "opening_count", "개"),
    "closing_count": ("CLSBIZ_STOR_CO", "closing_count", "개"),
    "name": ("place_name", "place_name", "이름"),
    "kakao_category": ("category_name", "kakao_category", "분류"),
    "distance_m": ("distance", "distance_m", "m"),
}
