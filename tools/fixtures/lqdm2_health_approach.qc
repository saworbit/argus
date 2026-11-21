// Private stock health fixture. The controller owns movement after placement.
entity ha_bot, ha_target, ha_lastnode;
float ha_started, ha_case, ha_mode, ha_refused;

void() HealthApproachBefore =
{
    local entity bot, item;
    local vector box, seat;
    if (time < 2 || ha_case) return;
    ha_case = cvar ("scratch2");
    if (mapname != "lqdm2" || ha_case < 1 || ha_case > 4)
        error ("HA wrong map or fixture case");

    bot = argus_bots;
    while (bot != world)
    {
        Argus_Nav_Abort (bot);
        if (bot.ar_slot == 0) ha_bot = bot;
        else
        {
            bot.health = 0; bot.solid = SOLID_NOT; bot.movetype = MOVETYPE_NONE;
            bot.nextthink = 0; bot.think = SUB_Null;
            bot.ar_respawntime = time + 3600;
        }
        bot = bot.ar_chain;
    }
    seat = '-272 207.75 216';
    box = '-200 312 0';
    if (ha_case == 1) box = '-248 264 0';
    if (ha_case == 3) seat = '-239 209 248';
    if (ha_case == 4) seat = '-264 200 216';
    item = find (world, classname, "item_health");
    while (item != world && (fabs (item.origin_x - box_x) > 1 || fabs (item.origin_y - box_y) > 1))
        item = find (item, classname, "item_health");
    if (ha_bot == world || item == world || item.solid != SOLID_TRIGGER)
        error ("HA missing bot or live stock health pack");

    Argus_TaskClear (ha_bot);
    Argus_TaskPlace (ha_bot, seat);
    if (!(ha_bot.flags & FL_ONGROUND) || ha_bot.groundentity != world)
        error ("HA start has no world support");
    ha_target = item;
    ha_started = time;
    ha_mode = -1;
    ha_bot.health = 50;
    ha_bot.ar_moveyaw = vectoyaw (Argus_GoalPoint (item) - ha_bot.origin);
    ha_bot.angles_y = ha_bot.ar_moveyaw;
    ha_bot.ar_lastpos = ha_bot.origin;
    ha_bot.ar_nextstall = time + 2;
    ha_bot.ar_goal = item;
    ha_bot.ar_enemy = world;
    ha_bot.ar_goalstart = time;
    ha_bot.ar_pending = 1;

    dprint ("BHVRPL begin lqdm2_health_approach\n");
    dprint ("HA begin dt_ms "); dprint (ftos (frametime * 1000)); dprint ("\n");
    dprint ("HA start "); dprint (ftos (ha_case)); dprint (" pos ");
    dprint (vtos (ha_bot.origin)); dprint (" target "); dprint (vtos (item.origin));
    dprint (" support world\n");
};

void() HealthApproachAfter =
{
    if (!ha_started) return;
    if (ha_mode != ha_bot.ar_mode || ha_lastnode != ha_bot.ar_node)
    {
        ha_mode = ha_bot.ar_mode; ha_lastnode = ha_bot.ar_node;
        dprint ("HA mode "); dprint (ftos (ha_mode)); dprint (" node ");
        dprint (vtos (ha_lastnode.origin)); dprint (" pos ");
        dprint (vtos (ha_bot.origin)); dprint ("\n");
    }
    if (!ha_refused && ha_bot.ar_blockedlast >= ha_started)
    {
        ha_refused = 1;
        dprint ("HA refusal "); dprint (vtos (ha_bot.origin));
        dprint (" yaw "); dprint (ftos (ha_bot.ar_moveyaw)); dprint ("\n");
    }
    if (ha_target.solid == SOLID_NOT || time > ha_started + 6 || ha_bot.health <= 0)
    {
        dprint ("HA end elapsed "); dprint (ftos (time - ha_started));
        dprint (" taken "); dprint (ftos (ha_target.solid == SOLID_NOT));
        dprint (" hp "); dprint (ftos (ha_bot.health)); dprint ("\n");
        ha_started = 0;
    }
};
