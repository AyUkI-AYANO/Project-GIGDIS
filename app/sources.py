"""Data source definitions for Project GIGDIS alpha0.1.0."""

RSS_SOURCES = [
    {
        "name": "Reuters World News",
        "url": "https://feeds.reuters.com/reuters/worldNews",
        "credibility": 0.95,
    },
    {
        "name": "BBC World",
        "url": "http://feeds.bbci.co.uk/news/world/rss.xml",
        "credibility": 0.92,
    },
    {
        "name": "Al Jazeera",
        "url": "https://www.aljazeera.com/xml/rss/all.xml",
        "credibility": 0.88,
    },
]

COUNTRY_KEYWORDS = {
    "Ukraine": ["ukraine", "kyiv", "kiev", "dnipro"],
    "Russia": ["russia", "moscow", "kremlin"],
    "Israel": ["israel", "tel aviv", "jerusalem", "gaza"],
    "Palestine": ["palestine", "west bank", "ramallah"],
    "United States": ["united states", "u.s.", "washington", "new york"],
    "China": ["china", "beijing", "shanghai", "taiwan"],
    "Japan": ["japan", "tokyo"],
    "United Kingdom": ["united kingdom", "uk", "london", "britain"],
    "France": ["france", "paris"],
    "Germany": ["germany", "berlin"],
    "India": ["india", "new delhi", "mumbai"],
    "Pakistan": ["pakistan", "islamabad"],
    "Iran": ["iran", "tehran"],
    "Turkey": ["turkey", "ankara", "istanbul"],
    "South Korea": ["south korea", "seoul"],
    "North Korea": ["north korea", "pyongyang"],
}

COUNTRY_COORDS = {
    "Ukraine": (48.3794, 31.1656),
    "Russia": (61.5240, 105.3188),
    "Israel": (31.0461, 34.8516),
    "Palestine": (31.9522, 35.2332),
    "United States": (39.8283, -98.5795),
    "China": (35.8617, 104.1954),
    "Japan": (36.2048, 138.2529),
    "United Kingdom": (55.3781, -3.4360),
    "France": (46.2276, 2.2137),
    "Germany": (51.1657, 10.4515),
    "India": (20.5937, 78.9629),
    "Pakistan": (30.3753, 69.3451),
    "Iran": (32.4279, 53.6880),
    "Turkey": (38.9637, 35.2433),
    "South Korea": (35.9078, 127.7669),
    "North Korea": (40.3399, 127.5101),
}

TOPIC_KEYWORDS = {
    "conflict": ["war", "strike", "attack", "missile", "military", "conflict"],
    "disaster": ["earthquake", "flood", "hurricane", "wildfire", "disaster"],
    "public-health": ["virus", "disease", "outbreak", "health emergency"],
    "diplomacy": ["summit", "talks", "diplomatic", "sanction", "treaty"],
    "economy": ["inflation", "oil", "market", "trade", "economic"],
}
