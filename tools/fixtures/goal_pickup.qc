// Private fixture for the touch event and the existing arrival heuristic.
float gp_fixture_done;

void() GoalPickupFixture =
{
    local entity oldself, oldother, bot, passer, box;
    local float before;

    if (gp_fixture_done || time < 2) return;
    gp_fixture_done = TRUE;
    oldself = self;
    oldother = other;
    bot = argus_bots;
    passer = bot.ar_chain;
    if (bot == world || passer == world)
        error ("goal pickup fixture needs two bots");

    dprint ("BHVRPL begin goal_pickup\n");
    box = spawn ();
    box.classname = "item_health";
    box.noise = "items/health1.wav";
    box.healamount = 25;
    box.solid = SOLID_TRIGGER;
    setorigin (box, '-239 -599 -72');
    self = box;
    other = bot;
    bot.ar_goal = box;
    bot.health = 60;

    dprint ("GPFIX own_touch\n");
    health_touch ();
    if (bot.health != 85 || box.solid != SOLID_NOT)
        error ("goal pickup fixture own touch did not heal");

    dprint ("GPFIX refused_touch\n");
    box.solid = SOLID_TRIGGER;
    bot.health = bot.max_health;
    health_touch ();
    if (box.solid != SOLID_TRIGGER)
        error ("goal pickup fixture accepted a full-health touch");

    dprint ("GPFIX arrival_without_touch\n");
    self = bot;
    setorigin (bot, box.origin);
    bot.ar_mode = 1;
    bot.ar_pending = 0;
    bot.ar_node = world;
    bot.ar_enemy = world;
    bot.ar_goalstart = time;
    bot.ar_nextai = time + 3;
    before = bot.ar_goals;
    Argus_AI ();
    if (bot.ar_goals != before + 1 || box.solid != SOLID_TRIGGER)
        error ("goal pickup fixture did not exercise heuristic arrival");

    dprint ("GPFIX other_picker\n");
    self = box;
    other = passer;
    bot.ar_goal = box;
    passer.ar_goal = world;
    passer.health = 60;
    health_touch ();
    if (passer.health != 85 || box.solid != SOLID_NOT || bot.ar_goal != box)
        error ("goal pickup fixture did not exercise a different picker");

    bot.ar_goal = world;
    remove (box);
    self = oldself;
    other = oldother;
    dprint ("GPFIX end\n");
};
