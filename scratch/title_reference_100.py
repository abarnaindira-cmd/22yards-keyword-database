"""Amazon-style keyword-rich titles (v2) for the 100 SKUs.
Facts: our product name + master Excel. Search phrases: our harvested keywords + relevant competitor titles.
No unverified material/performance claims (silicone, anti-fog, UV, waterproof, premium...)."""

def cap_viva(c):
    return f"VIVA Sport One Color Swimming Cap for Men and Women, Swim Cap for Swimming Pool, Unisex Swimming Head Cap - {c}"

def speedo_cap(c):
    s = "Speedo Long Hair AU Swimming Cap for Women and Men, Swim Cap for Long Hair, Speedo Swimming Cap for Swimming Pool"
    return f"{s} - {c}" if c else s

def tyka_lower(line, colour, size):
    return f"TYKA {line} Men's Sports Lower, Track Pants for Men, Sports Lower Bottom - {colour}, Size {size}"

def tyka_jersey(line, sleeve, colour, size):
    return (f"TYKA {line} Men's {sleeve} Sleeve Cricket Jersey, Cricket Shirt for Men, "
            f"{sleeve} Sleeve Sports T-Shirt - {colour}, Size {size}")

def tt_ball(model, colour="White"):
    return f"Koxtons {model} Table Tennis Ball, TT Balls for Table Tennis, Ping Pong Ball for Practice and Play - {colour}"

def dumbbell(w):
    return f"Koxtons Hexagon Dumbbell {w} kg (Single), Hex Dumbbell for Home Gym Workout, Gym Training Equipment for Men and Women"

def hundred_racket(model, c):
    return f"Hundred {model} Strung Tennis Racket, Tennis Racquet for Adults, Lawn Tennis Racket for Practice and Play - {c}"

TITLES = {
    "T2YVIVA000017": cap_viva("Pink"),
    "T2YVIVA000018": cap_viva("Grey"),
    "T2YVIVA000015": cap_viva("Dark Pink"),
    "T2YVIVA000016": cap_viva("Red"),
    "T2YVIVA000013": cap_viva("Blue"),
    "T2YVIVA000008": "VIVA Country Swimming Goggles, Swim Goggles for Men and Women, Swimming Goggles for Swimming Pool",
    "T2YVIVA000007": "VIVA Sports Dylan F-100 Swimming Mask, Swim Mask for Adults, Swimming Mask for Men and Women - Size Sr",
    "T2YVIVA000005": "VIVA Sports EP-05 Swimming Ear Plugs, Swim Ear Plug for Men, Women and Kids, Swimming Accessories",
    "T2YVIVA000003": "VIVA Sports EP-07 Swimming Ear Plugs, Swim Ear Plug for Men, Women and Kids, Swimming Accessories",
    "T2YVIVA000001": "VIVA Single Pocket Swimming Bag, Swim Bag for Swimming Accessories, Swimming Kit Bag for Men, Women and Kids",
    "T2YSPEEDO000008": "Speedo Biofuse 2.0 Unisex Adult Swimming Goggles for Men and Women, Speedo Swim Goggles for Swimming Pool - Black/Smoke",
    "T2YSPEEDO000005": "Speedo Biofuse 2.0 Unisex Adult Swimming Goggles for Men and Women, Speedo Swim Goggles for Swimming Pool - White/Smoke",
    "T2YSPEEDO000021": "Speedo Futura Classic Unisex Adult Swimming Goggles with Smoke Lens, Speedo Swim Goggles for Men and Women - Red/Smoke",
    "T2YSPEEDO000017": "Speedo Hydropulse Unisex Adult Mirror-Lens Swimming Goggles for Men and Women, Speedo Swim Goggles - Grey/Silver",
    "T2YSPEEDO000014": "Speedo Hydropulse Unisex Adult Mirror-Lens Swimming Goggles for Men and Women, Speedo Swim Goggles - Navy/Blue",
    "T2YSPEEDO000011": "Speedo Hydropulse Unisex Swimming Goggles for Men and Women, Speedo Swim Goggles for Swimming Pool",
    "T2YSPEEDO000001": speedo_cap("Blue/Purple"),
    "T2YSPEEDO000002": speedo_cap(""),
    "T2YSPEEDO000003": speedo_cap("Black"),
    "T2YSPEEDO000004": speedo_cap("Pink"),
    "T2YSPEEDO000024": "Speedo Swimming Goggles 809297C101, Speedo Swim Goggles for Swimming Pool and Swim Practice",
    "T2YSISCAA000015": "SISCAA Royal Carrom Striker for Carrom Board, Carrom Board Striker for Indoor Carrom Game",
    "T2YSISCAA000012": "SISCAA Junior Carrom Coins Set, Carrom Board Coins for Kids and Adults, Carrom Board Accessories (1 Set)",
    "T2YSISCAA000010": "SISCAA Commander Carrom Coins Set, Carrom Board Coins for Carrom Game, Carrom Board Accessories",
    "T2YSISCAA000007": "SISCAA Tournament Fighter Carrom Board 16mm, Full Size Carrom Board for Indoor Family Carrom Game",
    "T2YSISCAA000004": "SISCAA Tournament Fighter Carrom Board 20mm, Full Size Carrom Board for Indoor Family Carrom Game",
    "T2YSISCAA000001": "SISCAA Champion Fighter Carrom Board 24mm, Full Size Carrom Board for Indoor Family Carrom Game",
    "T2YVECTORX000001": "Vector X Mirage Football Shoes, Football Sports Shoes for Football Game and Practice - Black/White",
    "T2YVECTORX000007": "Vector X Cyber Table Tennis Set, TT Set for Table Tennis, Ping Pong Set for Indoor and Outdoor Play",
    "T2YEVERLAST000011": "Everlast Toning Tube Hard Resistance, Resistance Tube for Home Gym Workout and Gym Training - Blue",
    "T2YEVERLAST000010": "Everlast Toning Tube Light Resistance, Resistance Tube for Home Gym Workout and Gym Training - Green",
    "T2YEVERLAST000005": "Everlast Toning Tube Medium Resistance, Resistance Tube for Home Gym Workout and Gym Training - Red",
    "T2YGKI000001": "GKI Euro V Wooden Table Tennis Racquet, TT Bat for Table Tennis, Ping Pong Paddle for Practice and Play",
    "T2YJONEX000002": "Jonex Turf Hockey Ball, Field Hockey Ball for Turf and Ground, Hockey Ball for Practice and Match",
    "T2YKONEX000001": "Konex Pro Chess Board, Chess Board for Kids and Adults, Chess Board Game for Indoor Play",
    "T2YNIVIA000007": "Nivia G-2020 Rubber Volleyball VB-496, Nivia Volleyball Size 4 for Indoor and Outdoor Play - Yellow and Blue",
    "T2YNIVIA000006": "Nivia VB492 Spot Volleyball Size 4, Nivia Volleyball for Indoor and Outdoor Play, Volley Ball for Practice",
    "T2YSIXIT000007": "Sixit Heavy Cricket Tennis Ball, Tennis Ball for Cricket, Cricket Ball for Street and Tennis Ball Cricket",
    "T2YSMART000001": "Smart Pro Pacific Swimming Costume for Women, Ladies Swimming Costume, Swimwear for Women for Swimming Pool",
    "T2YTRINITY000001": "Smart Pro Trinity Swimming Costume, Swim Costume for Swimming Pool, Swimwear for Swimming",
    "T2YSPALDING000007": "Spalding Real Madrid Basketball Size 7, Spalding Basketball Ball for Indoor and Outdoor Play",
    "T2YSPALDING000005": "Spalding Olympiacos Basketball Size 7, Spalding Basketball Ball for Indoor and Outdoor Play",
    "T2YSPALDING000001": "Spalding TF-150 Euro Basketball Size 7, Spalding Basketball Ball for Indoor and Outdoor Play",
    "T2YSYNCO000001": "Synco Winit Super Full Size Carrom Board 8mm, Synco Carrom Board for Indoor Family Carrom Game",
    "T2YVIXEN000001": "Vixen Rollon Chess Board, Chess Board for Kids and Adults, Chess Board Game for Indoor Play",
    "T2YKOXTONS000020": "Koxtons ZORO Skipping Rope with Plastic Handle, Beaded Design Jump Rope for Men and Women, Skipping Rope for Workout",
    "T2YKOXTONS000018": "Koxtons CLUB Skipping Rope with Weighted Handles, Jump Rope for Men and Women, Skipping Rope for Gym Workout",
    "T2YKOXTONS000014": dumbbell("2.5"),
    "T2YKOXTONS000013": dumbbell("5"),
    "T2YKOXTONS000012": dumbbell("7.5"),
    "T2YKOXTONS000011": dumbbell("10"),
    "T2YKOXTONS000010": "Koxtons Cork Sheet Dart Board 18 Inch, Dart Board for Kids and Adults, Dart Game for Indoor Play",
    "T2YKOXTONS000007": "Koxtons Folding Carrom Board Stand, Foldable Carrom Stand for Carrom Board - Black",
    "T2YKOXTONS000006": "Koxtons Klub Carrom Powder 250 g, Carrom Board Powder for Carrom Game",
    "T2YKOXTONS000005": "Koxtons Impact Table Tennis Racquet, TT Bat for Table Tennis, Ping Pong Paddle for Practice and Play",
    "T2YKOXTONS000004": tt_ball("2 Star"),
    "T2YKOXTONS000003": tt_ball("Tournament"),
    "T2YKOXTONS000002": tt_ball("Force"),
    "T2YKOXTONS000001": tt_ball("3 Star"),
    "T2YKOXTONS000015": "Koxtons Basketball Net 4mm, Basketball Net Replacement for Basketball Ring, Basketball Hoop Net",
    "T2YKOXTONS000025": "Koxtons Shehnshah Chess Pieces, Chessmen for Chess Board Set, Chess Pieces for Kids and Adults",
    "T2YKOXTONS000023": "Koxtons Tournament Chess Pieces, Chessmen for Chess Board Set, Chess Pieces for Kids and Adults",
    "T2YKOXTONS000021": "Koxtons Nawab Chess Pieces, Chessmen for Chess Board Set, Chess Pieces for Kids and Adults",
    "T2YKOXTONS000027": "Koxtons Chess Rollon Board, Chess Board for Kids and Adults, Chess Board Game for Indoor Play",
    "T2YHUNDRED000001": hundred_racket("Bazooka", "White/Black"),
    "T2YHUNDRED000002": hundred_racket("Bazooka", "Black/Yellow"),
    "T2YHUNDRED000007": hundred_racket("Galactic", "White/Black"),
    "T2YHUNDRED000008": hundred_racket("Galactic", "White/Grey"),
    "T2YHUNDRED000009": hundred_racket("Galactic", "Navy/Blue"),
    "T2YHUNDRED000013": "Hundred 1 in 1 Racket Cover Full Cover, Tennis Racket Cover, Racket Cover Bag for Tennis Racquet",
}

_TYKA = [
    ("lower", "Align", None, "Off White", ["T2YTYKA000027:S", "T2YTYKA000028:M", "T2YTYKA000029:L", "T2YTYKA000030:XL", "T2YTYKA000031:XXL"]),
    ("jersey", "Align", "Full", "Off White", ["T2YTYKA000012:S", "T2YTYKA000013:M", "T2YTYKA000014:L", "T2YTYKA000015:XL", "T2YTYKA000016:XXL"]),
    ("jersey", "Align", "Half", "Off White", ["T2YTYKA000017:S", "T2YTYKA000018:M", "T2YTYKA000019:L", "T2YTYKA000020:XL", "T2YTYKA000021:XXL"]),
    ("lower", "Prima", None, "White", ["T2YTYKA000022:S", "T2YTYKA000023:M", "T2YTYKA000024:L", "T2YTYKA000025:XL", "T2YTYKA000026:XXL"]),
    ("jersey", "Prima", "Full", "White", ["T2YTYKA000007:S", "T2YTYKA000008:M", "T2YTYKA000010:L", "T2YTYKA000011:XL", "T2YTYKA000009:XXL"]),
    ("jersey", "Prima", "Half", "White", ["T2YTYKA000001:S", "T2YTYKA000003:M", "T2YTYKA000002:L", "T2YTYKA000004:XL", "T2YTYKA000006:XXL"]),
]
for kind, line, sleeve, colour, items in _TYKA:
    for it in items:
        sku, size = it.split(":")
        TITLES[sku] = tyka_lower(line, colour, size) if kind == "lower" else tyka_jersey(line, sleeve, colour, size)
