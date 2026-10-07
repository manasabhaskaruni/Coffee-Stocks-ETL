"""Port code -> readable name. Unknown codes fall back to the raw code and are recorded."""

PORT_NAMES = {
    # Arabica
    "ANT": "Antwerp", "BAR": "Barcelona", "HA/BR": "Hamburg/Bremen",
    "HOU": "Houston", "MIAMI": "Miami", "NOLA": "New Orleans",
    "NY": "New York", "VA": "Virginia",
    # Robusta
    "AMS": "Amsterdam", "BRE": "Bremen", "FEL": "Felixstowe",
    "HAM": "Hamburg", "LEH": "Le Havre", "LIV": "Liverpool",
    "LON": "London", "ROT": "Rotterdam", "TRI": "Trieste",
    "NOR": "Norfolk"  
}

UNMAPPED_PORTS: set = set()


def map_port(code: str) -> str:
    code = str(code).strip()
    name = PORT_NAMES.get(code)
    if name is None:
        UNMAPPED_PORTS.add(code)
        return code
    return name