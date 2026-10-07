from __future__ import annotations

from ....domain.entities import Category, Merchant
from ....application.ports.outbound import CategoryRepository, MerchantRepository

DEFAULT_CATEGORIES: list[dict] = [
    {"name": "Sin Categoria", "color": "#94a3b8", "icon": "", "labels": []},
    {
        "name": "Vivienda & Servicios",
        "color": "#3b82f6",
        "icon": "home",
        "labels": [],
        "children": [
            {"name": "Luz", "labels": ["cfe", "luz"]},
            {"name": "Agua", "labels": ["agua"]},
            {"name": "Renta", "labels": ["renta"]},
            {
                "name": "Internet y TV",
                "labels": ["izzi", "telmex", "sky", "totalplay", "internet"],
            },
            {"name": "Gas", "labels": ["gas"]},
        ],
    },
    {
        "name": "Comida & Supermercados",
        "color": "#a855f7",
        "icon": "shopping_cart",
        "labels": [],
        "children": [
            {
                "name": "Supermercado",
                "labels": ["walmart", "soriana", "chedraui", "costco"],
            },
            {"name": "Conveniencia", "labels": ["oxxo"]},
            {
                "name": "Restaurantes",
                "labels": [
                    "uber eats",
                    "didi food",
                    "rappi",
                    "restaurante",
                    "starbucks",
                    "vips",
                    "toks",
                    "burger",
                ],
            },
        ],
    },
    {
        "name": "Transporte",
        "color": "#eab308",
        "icon": "commute",
        "labels": [],
        "children": [
            {
                "name": "Gasolina",
                "labels": [
                    "gasolina",
                    "shell",
                    "mobil",
                    "bp",
                    "g500",
                    "pemex",
                    "costco gas",
                ],
            },
            {"name": "Apps", "labels": ["uber", "didi", "taxi"]},
            {"name": "Pasajes", "labels": ["ado", "aeromexico", "volaris"]},
        ],
    },
    {
        "name": "Entretenimiento",
        "color": "#ec4899",
        "icon": "movie",
        "labels": [],
        "children": [
            {
                "name": "Streaming",
                "labels": [
                    "netflix",
                    "spotify",
                    "prime",
                    "disney",
                    "hbo",
                    "apple tv",
                    "youtube",
                    "gamepass",
                ],
            },
            {"name": "Cine", "labels": ["cinepolis", "cinemex"]},
        ],
    },
    {
        # Money coming in as *earnings*. Conservative on purpose: "pago
        # recibido" and "deposito" are not here, because a friend paying you
        # back and a transfer from your own other account both arrive with
        # those words -- and those are transfers, flagged elsewhere, not income.
        # Payroll wording is what every Mexican employer's SPEI carries.
        "name": "Ingresos",
        "color": "#16a34a",
        "icon": "savings",
        "labels": [],
        "children": [
            {
                "name": "Nómina",
                "labels": [
                    "nomina",
                    "sueldo",
                    "salario",
                    "quincena",
                    "dispersion de nomina",
                    "pago de nomina",
                ],
            },
            {"name": "Honorarios", "labels": ["honorarios"]},
        ],
    },
    {
        # Money going out to *people and the bank*, not to a merchant: sends
        # to third parties, fees, interest, the card's annual charge. The
        # mirror of "Ingresos". Conservative on purpose: "pago" and "cargo"
        # are not here, because every purchase line carries them and would
        # steal rows from the merchant categories. "pago a terceros" is
        # longer than Transferencias' "transferencia", so a send to a person
        # files here rather than among the internal moves.
        "name": "Gasto",
        "color": "#dc2626",
        "icon": "outbound",
        "labels": [],
        "children": [
            {
                "name": "Envíos a terceros",
                "labels": [
                    "pago a terceros",
                    "envio a terceros",
                    "envio de dinero",
                ],
            },
            {
                "name": "Comisiones e intereses",
                "labels": ["comision", "iva comision", "intereses", "anualidad"],
            },
        ],
    },
    {
        "name": "Transferencias & Ajustes",
        "color": "#64748b",
        "icon": "payments",
        # "retiro"/"cajero" deliberately absent: a withdrawal's category is
        # unknown -- the statement cannot see what the cash bought -- so it is
        # a flag (`is_cash_withdrawal`), not a category (plan §2). Filing them
        # here made every ATM visit look like an internal transfer.
        "labels": [],
        "children": [
            {
                "name": "Transferencia",
                "labels": ["transferencia", "spei", "abono", "deposito"],
            },
            {"name": "Pago de tarjeta", "labels": ["pago tc"]},
        ],
    },
]

DEFAULT_MERCHANTS: list[dict] = [
    {"name": "Netflix", "labels": ["netflix", "netflix.com"]},
    {"name": "Spotify", "labels": ["spotify", "spotify mexico"]},
    {"name": "Uber", "labels": ["uber", "uber trip"]},
    {"name": "Didi", "labels": ["didi", "didi food"]},
    {"name": "Amazon", "labels": ["amazon", "amazon.com", "marketp amazon"]},
    {"name": "Walmart", "labels": ["walmart", "bodega aurrera", "sams club"]},
    {"name": "OXXO", "labels": ["oxxo"]},
    {"name": "CFE", "labels": ["cfe", "cfe contigo"]},
    {"name": "Mercado Pago", "labels": ["mercado pago", "merpago"]},
    {"name": "Starbucks", "labels": ["starbucks"]},
    {"name": "Uber Eats", "labels": ["uber eats"]},
    {"name": "Rappi", "labels": ["rappi"]},
    {"name": "Apple", "labels": ["apple.com/bill", "itunes.com", "icloud"]},
    {"name": "Telmex", "labels": ["telmex", "pago telmex"]},
    {"name": "Izzi", "labels": ["izzi", "izzi telecom"]},
    {"name": "Totalplay", "labels": ["totalplay"]},
    {"name": "Soriana", "labels": ["soriana"]},
    {"name": "Chedraui", "labels": ["chedraui"]},
    {"name": "Costco", "labels": ["costco", "costco gas"]},
    {"name": "Pemex", "labels": ["pemex"]},
    {"name": "Shell", "labels": ["shell"]},
    {"name": "Cinemex", "labels": ["cinemex"]},
    {"name": "Cinepolis", "labels": ["cinepolis"]},
]


def _key(name: str) -> str:
    return name.strip().lower()


def seed_reference_data(
    categories: CategoryRepository, merchants: MerchantRepository
) -> None:
    """Idempotently seed default categories and merchants.

    Per category, by name: a default added later ("Ingresos", then "Nómina")
    reaches a database that already has the others, while a category the user
    renamed is never touched — only *missing* names are inserted.

    Children attach to the parent of the same name. Matcher labels that used
    to live on the parent move onto the leaf so new classifications land
    there; a movement already filed on the parent stays until someone
    refines it. Extra labels the user added on a parent are kept.
    """
    _seed_categories(categories)
    if not merchants.get_all():
        merchants.add_many(
            [Merchant(name=m["name"], labels=m["labels"]) for m in DEFAULT_MERCHANTS]
        )


def _seed_categories(categories: CategoryRepository) -> None:
    by_name = {_key(c.name): c for c in categories.get_all()}

    missing_roots = [
        spec
        for spec in DEFAULT_CATEGORIES
        if _key(spec["name"]) not in by_name
    ]
    if missing_roots:
        categories.add_many(
            [
                Category(
                    name=spec["name"],
                    color=spec["color"],
                    icon=spec["icon"],
                    categorization_labels=list(spec["labels"]),
                )
                for spec in missing_roots
            ]
        )
        by_name = {_key(c.name): c for c in categories.get_all()}

    missing_children: list[Category] = []
    for spec in DEFAULT_CATEGORIES:
        parent = by_name.get(_key(spec["name"]))
        if parent is None:
            continue
        for child in spec.get("children") or []:
            if _key(child["name"]) in by_name:
                continue
            missing_children.append(
                Category(
                    name=child["name"],
                    color=child.get("color") or parent.color,
                    icon=child.get("icon") or parent.icon,
                    categorization_labels=list(child["labels"]),
                    parent_id=parent.id,
                )
            )
    if missing_children:
        categories.add_many(missing_children)
        by_name = {_key(c.name): c for c in categories.get_all()}

    dirty: dict = {}
    moved_by_parent: dict[str, set[str]] = {}
    for spec in DEFAULT_CATEGORIES:
        parent_key = _key(spec["name"])
        moved = moved_by_parent.setdefault(parent_key, set())
        parent = by_name.get(parent_key)
        for child in spec.get("children") or []:
            moved.update(_key(lbl) for lbl in child["labels"])
            row = by_name.get(_key(child["name"]))
            if row is None or parent is None:
                continue
            if row.parent_id != parent.id:
                row.parent_id = parent.id
                dirty[row.id] = row

    for spec in DEFAULT_CATEGORIES:
        row = by_name.get(_key(spec["name"]))
        if row is None:
            continue
        moved = moved_by_parent.get(_key(spec["name"])) or set()
        if not moved:
            continue
        kept = [lbl for lbl in row.categorization_labels if _key(lbl) not in moved]
        if kept != list(row.categorization_labels):
            row.categorization_labels = kept
            dirty[row.id] = row

    if dirty:
        categories.save_many(list(dirty.values()))
