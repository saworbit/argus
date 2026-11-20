// Exercise the real combat pickup clock on the dm2 stock progression.
float ap_done;
.float ap_fixture_flags;

entity(string type, vector seat) AdaptationPickupItem =
{
    local entity item;
    item = spawn ();
    item.classname = type;
    item.flags = FL_ITEM;
    item.solid = SOLID_TRIGGER;
    item.healamount = 25;
    setsize (item, '-8 -8 -8', '8 8 8');
    setorigin (item, seat);
    return item;
};

void() AdaptationPickupFixture =
{
    local entity saved, bot, foe, stock, healthbox, armour;
    local float deadline;

    if (!af_done || ap_done || mapname != "dm2") return;
    ap_done = 1;
    saved = self;
    bot = spawn ();
    bot.netname = "fixture";
    bot.ar_slot = 3;
    foe = spawn ();
    foe.health = 100;
    foe.weapon = IT_SHOTGUN;
    foe.flags = FL_ONGROUND;
    setorigin (bot, '1313 -471 184');
    setorigin (foe, '1409 -471 184');

    stock = argus_itemchain;
    while (stock != world)
    {
        stock.ap_fixture_flags = stock.flags;
        stock.flags = stock.flags - (stock.flags & FL_ITEM);
        stock = stock.ar_nextitem;
    }

    self = bot;
    Argus_BaseStats ();
    bot.health = 20;
    bot.ar_skill = 1;
    bot.flags = FL_ONGROUND;
    bot.weapon = IT_SHOTGUN;
    bot.items = IT_AXE | IT_SHOTGUN;
    bot.ammo_shells = 25;
    bot.ar_enemy = foe;
    bot.ar_targetscan = time + 5;
    bot.ar_react = time + 5;
    bot.ar_retreating = 0;
    bot.ar_retreatlock = 0;
    bot.invincible_finished = 0;
    Argus_ObserveEnemy (foe);

    healthbox = AdaptationPickupItem ("item_health", '1409 -471 184');
    armour = AdaptationPickupItem ("item_armorInv", '1313 -695 184');
    Argus_BattleItemScan ();
    AfCheck ("near_health_beats_distant_armour", bot.ar_bitem == healthbox);

    bot.ar_bitem = healthbox;
    deadline = time + 1;
    bot.ar_bitemend = deadline;
    bot.ar_bitemscan = 0;
    bot.invincible_finished = time + 3;
    Argus_Combat ();
    AfCheck ("keeps_pickup_commitment", bot.ar_bitem == healthbox && bot.ar_bitemend == deadline);
    bot.ar_bitem = healthbox;
    bot.ar_bitemend = time - 0.05;
    bot.ar_bitemscan = 0;
    Argus_Combat ();
    AfCheck ("expired_pickup_cools_and_replans", bot.ar_bitemlast == healthbox
             && bot.ar_bitemcool > time + 7 && bot.ar_bitem == armour);

    stock = argus_itemchain;
    while (stock != world)
    {
        stock.flags = stock.ap_fixture_flags;
        stock = stock.ar_nextitem;
    }
    self = saved;
    remove (healthbox);
    remove (armour);
    remove (bot);
    remove (foe);
};
