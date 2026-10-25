MASS_STATE_PLANE = "EPSG:26986"
SQFT_TO_M2 = 0.092903
ACRE_TO_M2 = 4046.86

CANDIDATE_CLASSES = ["commercial", "industrial", "exempt", "mixed"]
MIN_FOOTPRINT_M2 = 250
DISTRIBUTION_TYPES = ["distribution", "minor_distribution"]

PEAK_W_PER_M2 = {
    "grocery": 160,
    "restaurant": 150,
    "health": 110,
    "fuel": 90,
    "industrial": 90,
    "office": 80,
    "retail": 70,
    "hotel": 60,
    "school": 45,
    "auto_service": 45,
    "worship": 30,
    "warehouse": 20,
    "commercial": 65,
    "mixed": 50,
    "exempt": 50,
}

LOAD_KEYWORDS = [
    (("supermarket", "grocery"), "grocery"),
    (("eating and drinking", "restaurant"), "restaurant"),
    (("hospital", "nursing", "medical", "clinic", "care and treatment"), "health"),
    (("fuel", "gasoline"), "fuel"),
    (("auto repair", "automotive", "vehicle"), "auto_service"),
    (("warehouse", "storage", "distribution"), "warehouse"),
    (("manufactur", "industrial", "factory", "mill"), "industrial"),
    (("office", "bank"), "office"),
    (("school", "college", "universit", "education"), "school"),
    (("hotel", "motel", "inns"), "hotel"),
    (("church", "religious", "worship"), "worship"),
    (("retail", "store", "shopping", "sales"), "retail"),
]

NO_DEMAND_CHARGE_BELOW_KW = 20
LARGE_RATE_FROM_KW = 200
PEAK_SHAVE_FRACTION = 0.25
MAX_BATTERY_KW = 100
INCENTIVE_USD_PER_KW_YEAR = 200
INCENTIVE_PAGE = "ngrid_connectedsolutions"
INCENTIVE_QUOTE = "$200/kW"
SPACE_NEEDED_M2 = 500

LOAD_SPIKINESS = {
    "restaurant": 1.0,
    "grocery": 0.9,
    "fuel": 0.8,
    "retail": 0.7,
    "school": 0.7,
    "industrial": 0.7,
    "auto_service": 0.6,
    "hotel": 0.6,
    "office": 0.5,
    "commercial": 0.5,
    "mixed": 0.4,
    "exempt": 0.4,
    "health": 0.4,
    "worship": 0.3,
    "warehouse": 0.3,
}

SCORE_WEIGHTS = {
    "savings": 0.45,
    "spikiness": 0.15,
    "space": 0.15,
    "grid": 0.15,
    "confidence": 0.10,
}
