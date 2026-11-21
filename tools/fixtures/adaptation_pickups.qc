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

void(entity foe) AdaptationDenial =
{
    local entity near, far, seat, items, startnode, goalnode;
    local float ready;

    items = argus_itemchain;
    startnode = an_startnode;
    goalnode = an_goalnode;
    ready = an_shopready;
    seat = spawn ();
    setorigin (seat, self.origin);
    seat.an_mark = an_gen;
    an_startnode = seat;
    an_shopready = TRUE;

    near = AdaptationPickupItem ("item_armor1", self.origin + '100 0 0');
    far = AdaptationPickupItem ("item_armor1", self.origin + '440 0 0');
    near.ar_goalnode = seat;
    far.ar_goalnode = seat;
    near.ar_gnodeset = TRUE;
    far.ar_gnodeset = TRUE;
    near.ar_nextitem = far;
    argus_itemchain = near;
    self.ar_warmor = 1;
    foe.classname = "player";
    setorigin (foe, far.origin);
    self.ar_obsenemy = world;
    self.ar_sndweap = 0;
    Argus_PickGoal ();
    AfCheck ("unseen_opponent_leaves_pickup_ranking_alone", self.ar_goal == near);

    Argus_ObserveEnemy (foe);
    setorigin (foe, near.origin);
    Argus_PickGoal ();
    AfCheck ("denial_uses_last_sighting", self.ar_goal == far);

    self.ar_seen = time - 0.5;
    AfMemory (far.origin, IT_LIGHTNING, 0.2);
    Argus_PickGoal ();
    AfCheck ("denial_can_use_fresh_gunfire", self.ar_goal == far);
    self.ar_sndtime = time - 0.7;
    Argus_PickGoal ();
    AfCheck ("denial_expires_stale_evidence", self.ar_goal == near);

    argus_itemchain = items;
    an_startnode = startnode;
    an_goalnode = goalnode;
    an_shopready = ready;
    remove (near);
    remove (far);
    remove (seat);
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
    AdaptationDenial (foe);

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
