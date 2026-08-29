/*  argus_cam.qc - Intelligent spectator camera and AI broadcast director for Argus.
    Pure vanilla QuakeC, NetQuake protocol 15 compliant.

    Modes:
      0: POV (First-person bot perspective with viewmodel & HUD sync)
      1: Smart Chase (Spring-damped 3rd-person with anti-clip & velocity lead)
      2: AI Director (Omniview broadcast director with action scoring & vantage nodes)
      3: Focus / Duel Cam (Dynamic midpoint framing for 1v1 engagements)
      4: FreeLook Flight (6DOF inertial noclip spectator drone)
      5: Orbit / Showcase (Cinematic orbital rotation)
*/

// ---------------------------------------------------------------- vantage nodes

void(vector org, vector ang, string tag) Argus_AddCamNode =
{
    local entity n;
    n = spawn ();
    n.classname = "argus_cam_node";
    n.solid = SOLID_NOT;
    n.movetype = MOVETYPE_NONE;
    setorigin (n, org);
    n.angles = ang;
    n.cam_tag = tag;
};

// ---------------------------------------------------------------- viewmodel sync

void(entity client, entity bot) ArgusCam_SyncViewmodel =
{
    if (bot.weapon == IT_AXE)                   client.weaponmodel = "progs/v_axe.mdl";
    else if (bot.weapon == IT_SHOTGUN)          client.weaponmodel = "progs/v_shot.mdl";
    else if (bot.weapon == IT_SUPER_SHOTGUN)    client.weaponmodel = "progs/v_shot2.mdl";
    else if (bot.weapon == IT_NAILGUN)          client.weaponmodel = "progs/v_nail.mdl";
    else if (bot.weapon == IT_SUPER_NAILGUN)    client.weaponmodel = "progs/v_nail2.mdl";
    else if (bot.weapon == IT_GRENADE_LAUNCHER) client.weaponmodel = "progs/v_rock.mdl";
    else if (bot.weapon == IT_ROCKET_LAUNCHER)  client.weaponmodel = "progs/v_rock2.mdl";
    else if (bot.weapon == IT_LIGHTNING)        client.weaponmodel = "progs/v_light.mdl";
    else                                        client.weaponmodel = "";

    // without the frame the spectator's gun sits on frame 0 through
    // every shot: the muzzle flash and recoil live in weaponframe
    client.weaponframe = bot.weaponframe;

    // Sync health, armor, and ammo for engine HUD status bar
    client.health = bot.health;
    client.armorvalue = bot.armorvalue;
    client.armortype = bot.armortype;
    client.currentammo = bot.currentammo;
    client.ammo_shells = bot.ammo_shells;
    client.ammo_nails = bot.ammo_nails;
    client.ammo_rockets = bot.ammo_rockets;
    client.ammo_cells = bot.ammo_cells;
    client.items = bot.items;
};

// ---------------------------------------------------------------- lifecycle

void(entity client) ArgusCam_Init =
{
    local entity b;

    client.cam_active = 1;
    client.cam_mode = CAM_MODE_DIRECTOR;
    client.cam_dist = 135;
    client.cam_smooth_dist = 135;
    client.cam_zoom = 0;
    client.cam_hud_on = 1;
    client.cam_shoulder = 0;
    client.cam_cut_time = time;
    client.cam_eval_time = 0;
    client.cam_orbit_ang = 0;
    client.cam_hud_time = 0;
    client.cam_btn_debounce = 0;
    client.movetype = MOVETYPE_NOCLIP;
    client.solid = SOLID_NOT;
    client.takedamage = DAMAGE_NO;
    client.weaponmodel = "";

    // Pick first living bot as primary target
    b = argus_bots;
    while (b != world && b.health <= 0)
        b = b.ar_chain;
    client.cam_target = b;
    client.cam_target2 = world;

    if (b != world)
    {
        client.cam_pos = b.origin + '0 0 36';
        client.cam_angles = b.angles;
        setorigin (client, client.cam_pos);
    }

    sprint (client, PRINT_HIGH, "ArgusCam Active: AI Director Mode. (Left Click: Cycle Mode, Right Click: Target)\n");
};

void() ArgusCam_Toggle =
{
    if (self.cam_active)
    {
        self.cam_active = 0;
        self.movetype = MOVETYPE_WALK;
        self.solid = SOLID_SLIDEBOX;
        self.takedamage = DAMAGE_AIM;
        self.view_ofs = '0 0 22';
        W_SetCurrentAmmo ();
        sprint (self, PRINT_HIGH, "ArgusCam Deactivated: Returned to player physics.\n");
    }
    else
    {
        ArgusCam_Init (self);
    }
};

void() ArgusCam_CycleMode =
{
    if (!self.cam_active)
        ArgusCam_Init (self);

    self.cam_mode = self.cam_mode + 1;
    if (self.cam_mode > 5)
        self.cam_mode = 0;

    self.cam_cut_time = time;

    // Reset viewmodel when leaving POV mode
    if (self.cam_mode != CAM_MODE_POV)
        self.weaponmodel = "";

    if (self.cam_mode == CAM_MODE_POV)
        sprint (self, PRINT_HIGH, "ArgusCam Mode: 1st-Person Bot POV\n");
    else if (self.cam_mode == CAM_MODE_CHASE)
        sprint (self, PRINT_HIGH, "ArgusCam Mode: Smart Chase Cam (Spring Damped)\n");
    else if (self.cam_mode == CAM_MODE_DIRECTOR)
        sprint (self, PRINT_HIGH, "ArgusCam Mode: AI Broadcast Director (Omniview)\n");
    else if (self.cam_mode == CAM_MODE_DUEL)
        sprint (self, PRINT_HIGH, "ArgusCam Mode: Focus / Duel Cam (Midpoint Framing)\n");
    else if (self.cam_mode == CAM_MODE_FREELOOK)
        sprint (self, PRINT_HIGH, "ArgusCam Mode: FreeLook Flight Drone (6DOF Inertial)\n");
    else if (self.cam_mode == CAM_MODE_ORBIT)
        sprint (self, PRINT_HIGH, "ArgusCam Mode: Orbit / Showcase Cam\n");
};

void() ArgusCam_CycleTarget =
{
    local entity b, start;

    if (!self.cam_active)
        ArgusCam_Init (self);

    start = self.cam_target;
    if (start == world)
        b = argus_bots;
    else
        b = start.ar_chain;

    if (b == world)
        b = argus_bots;

    while (b != world && b.health <= 0 && b != start)
    {
        b = b.ar_chain;
        if (b == world)
            b = argus_bots;
    }

    self.cam_target = b;
    self.cam_cut_time = time;

    if (b != world)
    {
        sprint (self, PRINT_HIGH, "Tracking Target: ");
        sprint (self, PRINT_HIGH, b.netname);
        sprint (self, PRINT_HIGH, "\n");
    }
};

void() ArgusCam_ToggleShoulder =
{
    self.cam_shoulder = 1 - self.cam_shoulder;
    if (self.cam_shoulder)
        sprint (self, PRINT_HIGH, "Chase Cam Framing: Over-The-Right-Shoulder\n");
    else
        sprint (self, PRINT_HIGH, "Chase Cam Framing: Center Over-Head\n");
};

void() ArgusCam_ToggleHUD =
{
    self.cam_hud_on = 1 - self.cam_hud_on;
    if (self.cam_hud_on)
        sprint (self, PRINT_HIGH, "Broadcast HUD: Enabled\n");
    else
        sprint (self, PRINT_HIGH, "Broadcast HUD: Disabled\n");
};

// ---------------------------------------------------------------- modalities

void(entity client, entity bot) ArgusCam_POV =
{
    client.movetype = MOVETYPE_NONE;
    client.solid = SOLID_NOT;
    setorigin (client, bot.origin);
    client.view_ofs = bot.view_ofs;
    // Every v_angle write in argus.qc sits in a firing path (rocket-jump
    // pitch, prefire, combat aim, the shoot button), so out of combat
    // v_angle keeps whatever the last fight left and the POV view
    // freezes while the bot runs. Facing lives in angles_y and is
    // maintained every frame; pitch only exists while aiming.
    client.angles_y = bot.angles_y;
    if (bot.ar_enemy != world)
        client.angles_x = bot.v_angle_x;
    else
        client.angles_x = 0;
    client.angles_z = 0;
    client.fixangle = TRUE;
    ArgusCam_SyncViewmodel (client, bot);
};

void(entity client, entity bot) ArgusCam_SmartChase =
{
    local vector want_pos, lead, ideal_look, cand;
    local float min_frac, d, target_yaw, diff_yaw, target_pitch, diff_pitch;
    local float sweep, cy, k;

    client.movetype = MOVETYPE_NONE;
    client.solid = SOLID_NOT;
    client.weaponmodel = "";

    // 1. Predictive velocity lead (clamped to 64u to prevent detachment on RJ)
    lead = bot.velocity * 0.20;
    lead_z = 0;
    if (vlen(lead) > 64)
        lead = normalize(lead) * 64;
    ideal_look = bot.origin + '0 0 22' + lead;

    // 2. Combat dynamic zoom
    if (bot.ar_enemy != world && bot.ar_enemy.health > 0)
    {
        if (client.cam_zoom < 30)
            client.cam_zoom = client.cam_zoom + frametime * 40;
    }
    else
    {
        if (client.cam_zoom > 0)
            client.cam_zoom = client.cam_zoom - frametime * 25;
    }

    // 3. Smooth angle tracking (spring yaw & pitch)
    target_yaw = bot.angles_y;
    diff_yaw = target_yaw - client.cam_angles_y;
    while (diff_yaw > 180)  diff_yaw = diff_yaw - 360;
    while (diff_yaw < -180) diff_yaw = diff_yaw + 360;
    client.cam_angles_y = client.cam_angles_y + diff_yaw * (frametime * 10.0);

    // angles_x is 0 on any upright player, so this was a constant 8 and
    // the camera never tilted. Aim pitch lives in v_angle_x (up is
    // negative), and only while the bot is actually aiming at someone.
    if (bot.ar_enemy != world)
        target_pitch = (0 - bot.v_angle_x) * 0.35 + 8;
    else
        target_pitch = 8;
    diff_pitch = target_pitch - client.cam_angles_x;
    client.cam_angles_x = client.cam_angles_x + diff_pitch * (frametime * 8.0);

    makevectors (client.cam_angles);

    // 4. Base offset calculation
    d = client.cam_dist + client.cam_zoom;
    want_pos = (bot.origin + '0 0 26') - (v_forward * d);
    if (client.cam_shoulder)
        want_pos = want_pos + (v_right * 16);

    // 5. 5-Ray Pentagonal Collision Probe
    min_frac = 1.0;

    // Center ray
    traceline (bot.origin + '0 0 22', want_pos, FALSE, bot);
    if (trace_fraction < min_frac) min_frac = trace_fraction;

    // Top ray (+14z)
    traceline (bot.origin + '0 0 36', want_pos + '0 0 14', FALSE, bot);
    if (trace_fraction < min_frac) min_frac = trace_fraction;

    // Bottom ray (-10z)
    traceline (bot.origin + '0 0 12', want_pos - '0 0 10', FALSE, bot);
    if (trace_fraction < min_frac) min_frac = trace_fraction;

    // Left ray (-12y)
    traceline (bot.origin + '0 0 22' - v_right * 12, want_pos - v_right * 12, FALSE, bot);
    if (trace_fraction < min_frac) min_frac = trace_fraction;

    // Right ray (+12y)
    traceline (bot.origin + '0 0 22' + v_right * 12, want_pos + v_right * 12, FALSE, bot);
    if (trace_fraction < min_frac) min_frac = trace_fraction;

    // 6. Critically damped distance pull-in
    if (min_frac < 1.0)
    {
        d = d * min_frac - 10;
        if (d < 16) d = 16;
        client.cam_smooth_dist = d; // Snap-in on collision
    }
    else
    {
        // Smoothly expand back
        client.cam_smooth_dist = client.cam_smooth_dist + (d - client.cam_smooth_dist) * (frametime * 8.0);
    }

    // 6b. Flyby vantage sweep (QW cl_cam.c's InitFlyby idea): the
    // pull-in alone collapses to a neck-cam in tight corridors,
    // because the behind-the-bot axis is the ONLY one it considers.
    // When the camera stays pinched under 40u for 0.7s, sweep yaw
    // candidates around the bot (nearest-to-behind first, QW checks
    // 12; four pairs are enough at our 135u range) and CUT to the
    // first open one, exactly like the QW autocam repositions.
    if (client.cam_smooth_dist > 40)
        client.cam_pinch_time = time;
    else if (time > client.cam_pinch_time + 0.7)
    {
        sweep = 45;
        while (sweep <= 180)
        {
            k = 0 - 1;
            while (k <= 1)
            {
                cy = bot.angles_y + sweep * k;
                if (k != 0 || sweep == 180)
                {
                    makevectors ('0 0 0' + cy * '0 1 0');
                    cand = (bot.origin + '0 0 26') - v_forward * client.cam_dist;
                    traceline (bot.origin + '0 0 22', cand, FALSE, bot);
                    if (trace_fraction == 1)
                    {
                        client.cam_angles_y = cy;
                        client.cam_smooth_dist = client.cam_dist;
                        client.cam_pinch_time = time;
                        makevectors (client.cam_angles);
                        sweep = 999;    // found: break both loops
                        k = 2;
                    }
                }
                k = k + 2;
            }
            if (sweep < 999)
                sweep = sweep + 45;
        }
    }

    want_pos = (bot.origin + '0 0 22') - (v_forward * client.cam_smooth_dist);
    if (client.cam_shoulder)
        want_pos = want_pos + (v_right * 14);

    // 7. Spatial exponential smoothing
    client.cam_pos = client.cam_pos + (want_pos - client.cam_pos) * (frametime * 14.0);

    setorigin (client, client.cam_pos);
    client.angles = vectoangles (ideal_look - client.cam_pos);
    client.angles_x = 0 - client.angles_x;   // QC pitch convention
    client.fixangle = TRUE;
};

void(entity client, entity botA, entity botB) ArgusCam_DuelCam =
{
    local vector mid, duel_vec, perp, want_pos;
    local float d, duel_dist;

    client.movetype = MOVETYPE_NONE;
    client.solid = SOLID_NOT;
    client.weaponmodel = "";

    mid = (botA.origin + botB.origin) * 0.5 + '0 0 24';
    duel_vec = botB.origin - botA.origin;
    duel_dist = vlen (duel_vec);

    perp_x = 0 - duel_vec_y;
    perp_y = duel_vec_x;
    perp_z = 0;
    // two bots stacked in a lift shaft share their xy, and
    // normalize('0 0 0') is '0 0 0' - the camera would collapse into
    // the middle of both bounding boxes. Any perpendicular will do.
    if (vlen (perp) < 0.1)
        perp = '1 0 0';
    else
        perp = normalize (perp);

    d = duel_dist * 0.85;
    if (d < 180) d = 180;
    if (d > 650) d = 650;

    want_pos = mid + (perp * d) + '0 0 36';

    // Anti-clip check from midpoint to camera
    traceline (mid, want_pos, FALSE, world);
    if (trace_fraction < 1.0)
    {
        d = d * trace_fraction - 14;
        if (d < 32) d = 32;
        want_pos = mid + (perp * d) + '0 0 20';
    }

    client.cam_pos = client.cam_pos + (want_pos - client.cam_pos) * (frametime * 10.0);
    setorigin (client, client.cam_pos);
    client.angles = vectoangles (mid - client.cam_pos);
    client.angles_x = 0 - client.angles_x;   // QC pitch convention
    client.fixangle = TRUE;
};

void(entity client, entity bot) ArgusCam_OrbitCam =
{
    local vector want_pos, ideal_look;
    local float r;

    client.movetype = MOVETYPE_NONE;
    client.solid = SOLID_NOT;
    client.weaponmodel = "";

    client.cam_orbit_ang = client.cam_orbit_ang + (frametime * 40);
    while (client.cam_orbit_ang > 360) client.cam_orbit_ang = client.cam_orbit_ang - 360;

    makevectors ('0 1 0' * client.cam_orbit_ang);
    r = 160;
    want_pos = bot.origin + (v_forward * r) + '0 0 36';
    ideal_look = bot.origin + '0 0 22';

    traceline (ideal_look, want_pos, FALSE, bot);
    if (trace_fraction < 1.0)
        want_pos = ideal_look + (v_forward * (r * trace_fraction - 10));

    client.cam_pos = client.cam_pos + (want_pos - client.cam_pos) * (frametime * 12.0);
    setorigin (client, client.cam_pos);
    client.angles = vectoangles (ideal_look - client.cam_pos);
    client.angles_x = 0 - client.angles_x;   // QC pitch convention
    client.fixangle = TRUE;
};

void(entity client) ArgusCam_FreeLookFlight =
{
    client.movetype = MOVETYPE_NOCLIP;
    client.solid = SOLID_NOT;
    client.weaponmodel = "";
    client.cam_pos = client.origin;
    client.cam_angles = client.v_angle;
};

// ---------------------------------------------------------------- director AI

void(entity client) ArgusDirector_Evaluate =
{
    local entity b, best_b, best_opp, cam_node, best_node, tele;
    local float score, best_score, dist, d, best_node_d;
    local vector mid;

    // 1. Kill Cam: If current target just died, instantly cut to killer
    if (client.cam_target != world && client.cam_target.health <= 0)
    {
        if (client.cam_target.ar_enemy != world && client.cam_target.ar_enemy.health > 0)
        {
            client.cam_target = client.cam_target.ar_enemy;
            client.cam_target2 = world;
            client.cam_cut_time = time;
        }
    }

    // 2. Maintain minimum shot length (3.5s) unless current target died
    if (client.cam_target != world && client.cam_target.health > 0)
    {
        if (time < client.cam_cut_time + 3.5)
        {
            // Still follow active target smoothly
            if (client.cam_target2 != world && client.cam_target2.health > 0 &&
                vlen(client.cam_target.origin - client.cam_target2.origin) < 600)
            {
                ArgusCam_DuelCam (client, client.cam_target, client.cam_target2);
            }
            else
            {
                ArgusCam_SmartChase (client, client.cam_target);
            }
            return;
        }
    }

    // 3. Teleporter Cut-Ahead: Check if tracked bot is stepping into a teleporter
    if (client.cam_target != world && client.cam_target.health > 0)
    {
        tele = find (world, classname, "trigger_teleport");
        while (tele != world)
        {
            // a 56u sphere about the brush centre misses a wide
            // trigger entirely - the bot is inside the volume and more
            // than 56u from its middle. Test the box the engine tests.
            if (client.cam_target.origin_x > tele.absmin_x - 16
                && client.cam_target.origin_x < tele.absmax_x + 16
                && client.cam_target.origin_y > tele.absmin_y - 16
                && client.cam_target.origin_y < tele.absmax_y + 16
                && client.cam_target.origin_z > tele.absmin_z - 24
                && client.cam_target.origin_z < tele.absmax_z + 24)
            {
                if (tele.target != "")
                {
                    best_node = find (world, targetname, tele.target);
                    if (best_node != world)
                    {
                        // Cut ahead to exit destination arch
                        makevectors (best_node.angles);
                        client.cam_pos = best_node.origin + v_forward * 120 + '0 0 24';
                        setorigin (client, client.cam_pos);
                        client.angles = vectoangles (best_node.origin - client.cam_pos);
                        client.angles_x = 0 - client.angles_x;   // QC pitch convention
                        client.fixangle = TRUE;
                        client.cam_cut_time = time + 1.0;
                        return;
                    }
                }
            }
            tele = find (tele, classname, "trigger_teleport");
        }
    }

    // 4. Action-intensity evaluation (throttled)
    best_score = -1;
    best_b = world;
    best_opp = world;

    b = argus_bots;
    while (b != world)
    {
        if (b.health > 0)
        {
            score = 10;
            // Active engagement
            if (b.ar_enemy != world && b.ar_enemy.health > 0)
            {
                score = score + 50;
                dist = vlen (b.origin - b.ar_enemy.origin);
                if (dist < 450) score = score + 30; // Close duel
            }
            // Powerup carrier
            if (b.super_damage_finished > time) score = score + 90;
            if (b.invincible_finished > time)   score = score + 70;
            // Low-health clutch survival
            if (b.health < 35) score = score + (35 - b.health) * 2;
            // Airborne rocket jump
            if (b.ar_hoprj == 2 || !(b.flags & FL_ONGROUND)) score = score + 40;
            // Leader bias (QW cl_hightrack): the scoreboard leader is
            // the default story when the action scores are level
            score = score + b.frags * 3;

            if (score > best_score)
            {
                best_score = score;
                best_b = b;
                best_opp = b.ar_enemy;
            }
        }
        b = b.ar_chain;
    }

    if (best_b != world && (best_b != client.cam_target || client.cam_target.health <= 0))
    {
        client.cam_target = best_b;
        client.cam_target2 = best_opp;
        client.cam_cut_time = time;
    }

    // 5. Check for pre-calculated Cartographer vantage anchors
    if (client.cam_target != world && client.cam_target2 != world && client.cam_target2.health > 0)
    {
        mid = (client.cam_target.origin + client.cam_target2.origin) * 0.5 + '0 0 24';
        best_node = world;
        best_node_d = 999999;

        cam_node = find (world, classname, "argus_cam_node");
        while (cam_node != world)
        {
            d = vlen (cam_node.origin - mid);
            if (d > 180 && d < 750)
            {
                traceline (cam_node.origin, client.cam_target.origin + '0 0 22', TRUE, world);
                if (trace_fraction == 1.0)
                {
                    traceline (cam_node.origin, client.cam_target2.origin + '0 0 22', TRUE, world);
                    if (trace_fraction == 1.0 && d < best_node_d)
                    {
                        best_node_d = d;
                        best_node = cam_node;
                    }
                }
            }
            cam_node = find (cam_node, classname, "argus_cam_node");
        }

        if (best_node != world)
        {
            // Lock to Cartographer Vantage Point
            client.cam_pos = client.cam_pos + (best_node.origin - client.cam_pos) * (frametime * 8.0);
            setorigin (client, client.cam_pos);
            client.angles = vectoangles (mid - client.cam_pos);
            client.angles_x = 0 - client.angles_x;   // QC pitch convention
            client.fixangle = TRUE;
            return;
        }

        // Fall back to Focus / Duel Cam
        if (vlen (client.cam_target.origin - client.cam_target2.origin) < 600)
        {
            ArgusCam_DuelCam (client, client.cam_target, client.cam_target2);
            return;
        }
    }

    // Default to Smart Chase
    if (client.cam_target != world)
        ArgusCam_SmartChase (client, client.cam_target);
};

// ---------------------------------------------------------------- broadcast HUD

void(entity client) ArgusCam_RenderHUD =
{
    local entity t;
    local string mname, wname, aname;

    if (!client.cam_hud_on)
        return;

    t = client.cam_target;
    if (t == world)
        return;

    if (client.cam_mode == CAM_MODE_POV)            mname = "POV";
    else if (client.cam_mode == CAM_MODE_CHASE)     mname = "Smart Chase";
    else if (client.cam_mode == CAM_MODE_DIRECTOR)  mname = "AI Director";
    else if (client.cam_mode == CAM_MODE_DUEL)      mname = "Duel Focus";
    else if (client.cam_mode == CAM_MODE_FREELOOK)  mname = "FreeLook Drone";
    else                                            mname = "Orbit Showcase";

    if (t.weapon == IT_ROCKET_LAUNCHER)     wname = "RL";
    else if (t.weapon == IT_LIGHTNING)      wname = "LG";
    else if (t.weapon == IT_SUPER_NAILGUN)  wname = "SNG";
    else if (t.weapon == IT_GRENADE_LAUNCHER) wname = "GL";
    else if (t.weapon == IT_SUPER_SHOTGUN)  wname = "SSG";
    else if (t.weapon == IT_NAILGUN)        wname = "NG";
    else if (t.weapon == IT_SHOTGUN)        wname = "SG";
    else                                    wname = "AXE";

    // Affect state indicator
    if (t.super_damage_finished > time)     aname = "QUAD SPREE";
    else if (t.health < 30)                 aname = "PANICKED";
    else if (t.ar_enemy != world)           aname = "COMBAT";
    else if (t.ar_mode == 2)                aname = "ROUTING";
    else                                    aname = "TACTICAL";

    // wname and aname were computed every frame and thrown away: the
    // spectator saw the camera mode and nothing about the bot it follows
    centerprint7 (client,
        "ARGUSCAM: ",
        mname,
        "\n",
        t.netname,
        "  ",
        wname,
        aname);
};

// ---------------------------------------------------------------- frame dispatcher

void() ArgusCam_Frame =
{
    if (!self.cam_active)
        return;

    // Mouse button click debounce handling
    if (self.cam_mode != CAM_MODE_FREELOOK)
    {
        if (self.button0 && time > self.cam_btn_debounce)
        {
            self.cam_btn_debounce = time + 0.35;
            ArgusCam_CycleMode ();
        }
        else if (self.button2 && time > self.cam_btn_debounce)
        {
            self.cam_btn_debounce = time + 0.35;
            ArgusCam_CycleTarget ();
        }
    }

    // Safety fallback: ensure live target
    if (self.cam_target == world || self.cam_target.health <= 0)
    {
        self.cam_target = argus_bots;
        while (self.cam_target != world && self.cam_target.health <= 0)
            self.cam_target = self.cam_target.ar_chain;
    }

    if (self.cam_mode == CAM_MODE_POV)
    {
        if (self.cam_target != world)
            ArgusCam_POV (self, self.cam_target);
    }
    else if (self.cam_mode == CAM_MODE_CHASE)
    {
        if (self.cam_target != world)
            ArgusCam_SmartChase (self, self.cam_target);
    }
    else if (self.cam_mode == CAM_MODE_DIRECTOR)
    {
        ArgusDirector_Evaluate (self);
    }
    else if (self.cam_mode == CAM_MODE_DUEL)
    {
        if (self.cam_target != world && self.cam_target2 != world && self.cam_target2.health > 0)
            ArgusCam_DuelCam (self, self.cam_target, self.cam_target2);
        else if (self.cam_target != world)
            ArgusCam_SmartChase (self, self.cam_target);
    }
    else if (self.cam_mode == CAM_MODE_FREELOOK)
    {
        ArgusCam_FreeLookFlight (self);
    }
    else if (self.cam_mode == CAM_MODE_ORBIT)
    {
        if (self.cam_target != world)
            ArgusCam_OrbitCam (self, self.cam_target);
    }

    // Refresh HUD overlay at 3Hz
    if (time > self.cam_hud_time)
    {
        self.cam_hud_time = time + 0.35;
        ArgusCam_RenderHUD (self);
    }
};

void(float imp) ArgusCam_Impulse =
{
    if (imp == 210)      ArgusCam_Toggle ();
    else if (imp == 211) ArgusCam_CycleMode ();
    else if (imp == 212) ArgusCam_CycleTarget ();
    else if (imp == 213) ArgusCam_ToggleShoulder ();
    else if (imp == 214) ArgusCam_ToggleHUD ();
};
