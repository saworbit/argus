// Exercise the real fixed-task assignment and stock e1m8 pusher physics.
float task_fixture_phase;
entity task_fixture_plat;
float task_fixture_z;
float task_fixture_until;
void() plat_go_up;

void(entity bot, vector start) TaskPlacementAssign =
{
    bot.ar_taskplace = start;
    bot.ar_taskstaged = 1;
    cvar_set ("scratch1", "3842");
    cvar_set ("scratch2", "673");
    cvar_set ("scratch3", "321");
    cvar_set ("scratch4", "-712");
    Argus_TaskControl (bot.ar_slot);
    cvar_set ("scratch1", "0");
};

void(entity bot) TaskPlacementState =
{
    dprint (" lift "); dprint (ftos (bot.ar_hoplift));
    dprint (" boarded "); dprint (ftos (bot.ar_boarded));
    dprint (" door "); dprint (ftos (bot.ar_hopdoor));
    dprint (" ground "); dprint (ftos (bot.groundentity == task_fixture_plat));
    dprint (" pending "); dprint (ftos (bot.ar_pending));
    dprint ("\n");
};

void() TaskPlacementFixture =
{
    local entity bot, saved;
    local vector start;

    if (task_fixture_phase == 3 || time < 1.5)
        return;
    bot = argus_bots;
    if (bot == world || bot.deadflag != DEAD_NO)
        return;

    if (!task_fixture_phase)
    {
        task_fixture_plat = find (world, model, "*3");
        if (task_fixture_plat.classname != "plat" || task_fixture_plat.state != STATE_BOTTOM)
            objerror ("task placement fixture requires e1m8 south lift at bottom");

        dprint ("BHVRPL begin task_placement\n");
        bot.ar_hoplift = 1;
        bot.ar_boarded = 1;
        bot.ar_hopdoor = 1;
        bot.ar_door = task_fixture_plat;
        bot.flags = bot.flags | FL_ONGROUND;
        bot.groundentity = task_fixture_plat;
        start = '673 321 -712';
        TaskPlacementAssign (bot, start);
        dprint ("TASKFIX released"); TaskPlacementState (bot);

        bot.groundentity = world;
        bot.flags = bot.flags - (bot.flags & FL_ONGROUND);

        start = (task_fixture_plat.absmin + task_fixture_plat.absmax) * 0.5;
        start_z = task_fixture_plat.origin_z + task_fixture_plat.maxs_z + 24.125;
        TaskPlacementAssign (bot, start);
        dprint ("TASKFIX acquired"); TaskPlacementState (bot);
        task_fixture_z = bot.origin_z;
        task_fixture_until = time + 0.3;
        task_fixture_phase = 2;
        saved = self;
        self = task_fixture_plat;
        plat_go_up ();
        self = saved;
        return;
    }

    if (time >= task_fixture_until)
    {
        dprint ("TASKFIX ride "); dprint (ftos (bot.origin_z - task_fixture_z));
        dprint (" ground "); dprint (ftos (bot.groundentity == task_fixture_plat));
        dprint ("\n");
        task_fixture_phase = 3;
    }
};
