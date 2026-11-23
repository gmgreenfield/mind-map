"""Example map for trying the app: two topics, branches up to four levels deep.

Positions are computed with the real layout code, so seeding also exercises
place_child on a crowded map.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .layout import place_child
from .store import Store


@dataclass
class Node:
    title: str
    messages: list[tuple[str, str]]
    brief: str | None = None
    children: list["Node"] = field(default_factory=list)


def brief(goal: str, context: list[str], questions: list[str]) -> str:
    return (
        f"## Goal\n{goal}\n\n## Context\n"
        + "\n".join(f"- {c}" for c in context)
        + "\n\n## Open questions\n"
        + "\n".join(f"- {q}" for q in questions)
    )


COFFEE = Node(
    "Opening a small coffee roastery",
    [
        ("user", "I'm thinking about opening a small-batch coffee roastery in Leeds. "
                 "I have about £40k saved and I've been home-roasting for three years. "
                 "Where do I even start?"),
        ("assistant", "That's a solid base — the home-roasting experience matters more than "
                      "people think. I'd split it into four tracks:\n\n"
                      "1. **Business model** — wholesale to cafés, retail bags, subscriptions, or a mix.\n"
                      "2. **Equipment and space** — the roaster is the big-ticket item, and ventilation "
                      "decides which premises you can use.\n"
                      "3. **Brand** — name, packaging, story.\n"
                      "4. **Money** — pricing, margins and runway.\n\n"
                      "With £40k, wholesale-first is usually the safest: fewer customers, bigger orders."),
        ("user", "Wholesale-first makes sense. I'd still like a small online shop for bags."),
        ("assistant", "Good combination. Wholesale gives you steady volume, and the shop gives you "
                      "margin and a direct relationship with drinkers. Each of the four tracks "
                      "deserves its own branch."),
    ],
    children=[
        Node(
            "Naming and brand",
            [
                ("user", "I like names tied to Leeds or Yorkshire but don't want anything twee."),
                ("assistant", "Then avoid flat caps and whippets. Lean on place and material instead: "
                              "the canals, the mills, the stone. Some directions:\n\n"
                              "- **Millstone Roasters** — industrial heritage, sturdy.\n"
                              "- **Aire Coffee** — the river; short and clean.\n"
                              "- **Kirkgate** — the market; locals will get it.\n\n"
                              "Check Companies House and trademarks before you fall in love with one."),
                ("user", "Aire is my favourite. Could it be confused with air?"),
                ("assistant", "A little, out loud — but that's arguably a feature: light, fresh. "
                              "Pair it with the river visually so the reference lands."),
            ],
            brief=brief(
                "Choose a name and brand direction for the roastery.",
                ["Small-batch roastery in Leeds, wholesale-first plus an online shop.",
                 "Founder has £40k and three years of home roasting.",
                 "Wants a Leeds/Yorkshire feel without being twee."],
                ["Which name?", "What should the packaging look like?"],
            ),
            children=[
                Node(
                    "Logo ideas for Aire",
                    [
                        ("user", "Give me three logo concepts for Aire Coffee."),
                        ("assistant", "1. **River line** — a single flowing line that forms the 'A'.\n"
                                      "2. **Bean and ripple** — a bean with a ripple cut through it.\n"
                                      "3. **Wordmark only** — a strong serif 'AIRE', with the river "
                                      "suggested in the underline.\n\n"
                                      "For bags and stickers, option 1 scales down best."),
                    ],
                    brief=brief(
                        "Develop logo concepts for 'Aire Coffee'.",
                        ["The name refers to the River Aire in Leeds.",
                         "Possible confusion with 'air' should be resolved visually via the river.",
                         "Will appear on retail bags, wholesale boxes and stickers."],
                        ["Symbol or wordmark?", "Colour palette?"],
                    ),
                ),
            ],
        ),
        Node(
            "Choosing a roaster",
            [
                ("user", "What size roaster should I get to start?"),
                ("assistant", "For wholesale-first, a **5 kg** drum roaster is the sweet spot. "
                              "It does roughly 15–20 kg an hour, which covers a dozen café "
                              "accounts with room to grow. 1–2 kg machines are great for "
                              "sample roasting but you'll outgrow them in months."),
                ("user", "New 5 kg machines seem to cost £25–35k. That's most of my savings."),
                ("assistant", "That's the crunch. Two ways out: buy used, or lease. Used is "
                              "usually the better deal if you can inspect it in person."),
            ],
            brief=brief(
                "Pick the right roaster for a wholesale-first start.",
                ["Budget is £40k in total; a new 5 kg roaster costs £25–35k.",
                 "Wholesale-first with an online shop."],
                ["Which capacity?", "New, used or leased?"],
            ),
            children=[
                Node(
                    "Used vs new roasters",
                    [
                        ("user", "What should I check when buying a used roaster?"),
                        ("assistant", "- **Drum and bearings** — listen for grinding; ask when they were serviced.\n"
                                      "- **Burner** — gas type has to match your supply; conversions cost money.\n"
                                      "- **Controls** — older machines may lack data logging; check it works "
                                      "with roast-profiling software.\n"
                                      "- **Afterburner** — you may need one for permits; budget £5–10k if not.\n\n"
                                      "A good used 5 kg roaster runs £12–18k."),
                    ],
                    brief=brief(
                        "Decide between a used and a new 5 kg roaster.",
                        ["New 5 kg roasters cost £25–35k against a £40k total budget.",
                         "Used is likely better value if inspected in person."],
                        ["What to inspect?", "What hidden costs come with used machines?"],
                    ),
                    children=[
                        Node(
                            "Ventilation and permits",
                            [
                                ("user", "Do I need permission for the smoke?"),
                                ("assistant", "Very likely. Talk to Leeds City Council's environmental "
                                              "health team early. Roasting smoke and smell are the usual "
                                              "objections, which is why an **afterburner** or catalytic "
                                              "converter often decides whether a unit is viable. Industrial "
                                              "units are much easier than anything near homes."),
                            ],
                            brief=brief(
                                "Understand ventilation and permit requirements for roasting.",
                                ["A used roaster may lack an afterburner (adds £5–10k).",
                                 "Location is Leeds; premises not chosen yet."],
                                ["Which permits?", "Industrial unit or high street?"],
                            ),
                        ),
                    ],
                ),
            ],
        ),
        Node(
            "Wholesale pricing",
            [
                ("user", "How should I price wholesale versus retail?"),
                ("assistant", "Work it out from cost per kg:\n\n"
                              "- Green beans: £7–9/kg; you lose ~15% weight in roasting.\n"
                              "- Roasted cost, including labour and packaging: ~£14/kg.\n"
                              "- **Wholesale**: £20–24/kg.\n"
                              "- **Retail**: £8–9 per 250 g bag, i.e. £32–36/kg.\n\n"
                              "Retail margin is much better, but wholesale moves the volume."),
            ],
            brief=brief(
                "Set wholesale and retail prices.",
                ["Wholesale-first with an online shop for bags.",
                 "Small-batch speciality positioning."],
                ["Cost per kg?", "Wholesale price?", "Bag price?"],
            ),
        ),
        Node(
            "First 90 days plan",
            [
                ("user", "What should the first 90 days look like?"),
                ("assistant", "**Days 1–30:** register the company, lock in the name, start the "
                              "permit conversation, shortlist premises.\n\n"
                              "**Days 31–60:** buy the roaster, fit out, find two green-bean "
                              "importers, develop three core roasts.\n\n"
                              "**Days 61–90:** sample-drop ten cafés, aim to sign three, and soft-launch "
                              "the online shop with friends and family."),
            ],
            brief=brief(
                "Plan the first 90 days to the first wholesale accounts.",
                ["£40k budget; wholesale-first plus an online shop.",
                 "Brand, roaster choice and pricing are being explored in sibling branches."],
                ["Order of steps?", "What can run in parallel?"],
            ),
        ),
    ],
)

KYOTO = Node(
    "Kyoto trip in April",
    [
        ("user", "Planning 6 days in Kyoto in early April with my partner. First time in Japan."),
        ("assistant", "Early April is cherry blossom season — beautiful, but busy, so **book "
                      "accommodation now**. Six days lets you do Kyoto properly plus one or two "
                      "day trips. Do you lean more towards temples and gardens, food, or walking?"),
        ("user", "Food and walking, some temples but not every single one."),
        ("assistant", "Then base yourselves somewhere walkable, go to the famous temples at "
                      "opening time, and spend the afternoons on neighbourhoods and markets."),
    ],
    children=[
        Node(
            "Day trips from Kyoto",
            [
                ("user", "Which day trips are worth it?"),
                ("assistant", "- **Nara** — deer, the giant Buddha, 45 minutes away. Easy win.\n"
                              "- **Osaka** — food city; go for an evening.\n"
                              "- **Arashiyama** — technically Kyoto, but it feels like a day out.\n"
                              "- **Himeji** — the best original castle; a longer trip.\n\n"
                              "With six days I'd do Nara and an Osaka evening."),
            ],
            brief=brief(
                "Choose day trips from Kyoto.",
                ["6 days in early April (cherry blossom season), first time in Japan.",
                 "Interests: food and walking, some temples."],
                ["Which trips?", "How many days to spend on them?"],
            ),
            children=[
                Node(
                    "Nara itinerary",
                    [
                        ("user", "Plan a relaxed day in Nara."),
                        ("assistant", "1. Train from Kyoto at about 8:30 (Kintetsu line).\n"
                                      "2. Tōdai-ji first, before the tour groups.\n"
                                      "3. Wander Nara Park and meet the deer — buy the crackers, "
                                      "watch your map.\n"
                                      "4. Lunch in Naramachi, the old merchant quarter.\n"
                                      "5. Kasuga Taisha's lantern paths in the afternoon.\n"
                                      "6. Back in Kyoto for dinner."),
                    ],
                    brief=brief(
                        "Plan one relaxed day in Nara.",
                        ["Day trip from a Kyoto base, early April.",
                         "Couple who like food and walking more than back-to-back temples."],
                        ["Morning order?", "Where to eat lunch?"],
                    ),
                ),
            ],
        ),
        Node(
            "Where to stay",
            [
                ("user", "Which area should we stay in?"),
                ("assistant", "**Higashiyama / Gion** if you want atmosphere and walking — "
                              "but it's pricier and busy in blossom season. **Around Shijō–Karasuma** "
                              "if you want central, practical, and lots of food. For a first trip "
                              "with food as a priority, I'd pick Shijō."),
            ],
            brief=brief(
                "Pick a neighbourhood to stay in.",
                ["6 days, early April, booking soon.",
                 "Priorities: food and walkability."],
                ["Which area?", "Ryokan or hotel?"],
            ),
        ),
        Node(
            "Food to try",
            [
                ("user", "What food shouldn't we miss?"),
                ("assistant", "- **Nishiki Market** — graze through it at lunchtime.\n"
                              "- **Yudofu** (tofu hot pot) near Nanzen-ji.\n"
                              "- **Obanzai** — Kyoto home-style small plates.\n"
                              "- **Matcha** anything in Uji, if you have half a day.\n"
                              "- A **kaiseki** dinner once — book ahead."),
            ],
            brief=brief(
                "List the Kyoto food experiences not to miss.",
                ["Couple on their first trip to Japan; food is the top priority."],
                ["Which dishes?", "What needs booking?"],
            ),
        ),
    ],
)

TREES = [(COFFEE, (0.0, 0.0)), (KYOTO, (0.0, 1600.0))]


def seed(store: Store) -> dict[str, int]:
    """Insert the demo map. Returns {title: session id}."""
    ids: dict[str, int] = {}

    def add(node: Node, parent_id: int | None, pos: tuple[float, float]) -> None:
        s = store.create_session(node.title, parent_id=parent_id, brief=node.brief, x=pos[0], y=pos[1])
        ids[node.title] = s.id
        for role, content in node.messages:
            store.add_message(s.id, role, content)
        for child in node.children:
            parent = store.get_session(s.id)
            gp = store.get_session(parent.parent_id) if parent.parent_id else None
            occupied = [(o.x, o.y) for o in store.sessions()]
            child_pos = place_child((parent.x, parent.y), occupied, (gp.x, gp.y) if gp else None)
            add(child, s.id, child_pos)

    for tree, origin in TREES:
        add(tree, None, origin)
    return ids


def count(node: Node) -> int:
    return 1 + sum(count(c) for c in node.children)
