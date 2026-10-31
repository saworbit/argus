// An acknowledged observer contract around the existing independent TACFIX
// engine fixture. This is destructive and for disposable lab matches only.
// developer + scratch1 590 + real-client impulse 218; scratch2 case 0..14,
// scratch3 positive integer trial ID; scratch4 590 enables diagnostics.
float ar_bf_active, ar_bf_id, ar_bf_case, ar_bf_frames, ar_bf_begin;
float ar_bf_ended, ar_bf_next, ar_bf_launches, ar_bf_guardok;
float ar_bf_checks, ar_bf_emits;
entity ar_bf_bot, ar_bf_target;
.float ar_bf_rocket_seen;

// A roster edit invalidates diagnostic identities, not gameplay targets.
void() Argus_BehaviourRosterReset =
{
    local entity b, saved;
    saved = self; b = argus_bots;
    while (b != world)
    {
        self = b; Argus_BehaviourReset ();
        b = b.ar_chain;
    }
    self = saved;
};

void() Argus_BehaviourFixture =
{
    local float id, trialcase;
    if (!cvar ("developer") || cvar ("scratch1") != 590
        || !(self.flags & FL_CLIENT) || self.ar_isbot) return;
    id = cvar ("scratch3"); trialcase = cvar ("scratch2");
    if (ar_bf_active || ar_tacfixture_until)
    {
        dprint ("BHVFIX busy id "); dprint (ftos (ar_bf_id));
        dprint (" requested "); dprint (ftos (id)); dprint ("\n");
        return;
    }
    if (id < 1 || id != floor (id) || trialcase < 0 || trialcase > 14
        || trialcase != floor (trialcase) || (mapname != "dm4" && mapname != "dm2"))
    { dprint ("BHVFIX refused invalid_trial\n"); return; }
    Argus_TacticFixture ();
    if (!ar_tacfixture_until) { dprint ("BHVFIX refused setup\n"); return; }
    ar_bf_active = 1; ar_bf_id = id; ar_bf_case = trialcase;
    ar_bf_frames = 0; ar_bf_begin = time; ar_bf_ended = 0;
    ar_bf_next = 0; ar_bf_launches = 0; ar_bf_guardok = 1;
    ar_bf_checks = 0; ar_bf_emits = 0;
    ar_bf_bot = ar_tacfixture_bot; ar_bf_target = ar_tf_target;
    dprint ("BHVFIX begin "); dprint (mapname);
    dprint (" case "); dprint (ftos (trialcase)); dprint ("\n");
    dprint ("BHVFIX trial "); dprint (ftos (id));
    dprint (" case "); dprint (ftos (trialcase)); dprint ("\n");
};

// Guard generated from the explicit field list in check_behaviour_fixture.py.
// Snapshot values are locals, never an entity's engine fields.
// BEGIN observer guard
void() Argus_BehaviourFixtureGuard =
{
    local vector ar_bgs_origin;
    local vector ar_bgs_velocity;
    local vector ar_bgs_angles;
    local vector ar_bgs_v_angle;
    local float ar_bgs_health;
    local float ar_bgs_armorvalue;
    local float ar_bgs_armortype;
    local float ar_bgs_items;
    local float ar_bgs_weapon;
    local float ar_bgs_ammo_shells;
    local float ar_bgs_ammo_nails;
    local float ar_bgs_ammo_rockets;
    local float ar_bgs_ammo_cells;
    local float ar_bgs_flags;
    local float ar_bgs_solid;
    local float ar_bgs_movetype;
    local float ar_bgs_takedamage;
    local float ar_bgs_button0;
    local float ar_bgs_button1;
    local float ar_bgs_button2;
    local float ar_bgs_attack_finished;
    local float ar_bgs_nextthink;
    local void() ar_bgs_think;
    local void() ar_bgs_touch;
    local void(entity attacker, float damage) ar_bgs_th_pain;
    local entity ar_bgs_ar_enemy;
    local float ar_bgs_ar_seen;
    local vector ar_bgs_ar_lastseen;
    local entity ar_bgs_ar_lastfoe;
    local entity ar_bgs_ar_goal;
    local entity ar_bgs_ar_node;
    local float ar_bgs_ar_pending;
    local float ar_bgs_ar_shopping;
    local float ar_bgs_ar_routegen;
    local float ar_bgs_ar_mode;
    local float ar_bgs_ar_moveyaw;
    local float ar_bgs_ar_nextai;
    local float ar_bgs_ar_nextlog;
    local float ar_bgs_ar_nextstall;
    local float ar_bgs_ar_react;
    local float ar_bgs_ar_track;
    local entity ar_bgs_ar_plan_goal;
    local entity ar_bgs_ar_plan_leg;
    local float ar_bgs_ar_plan_best;
    local float ar_bgs_ar_plan_stamp;
    local entity ar_bgs_ar_fetchfailed;
    local float ar_bgs_ar_fetchcool;
    local entity ar_bgs_ar_actionnode;
    local entity ar_bgs_ar_actiongoal;
    local float ar_bgs_ar_actionbest;
    local float ar_bgs_ar_actiontime;
    local float ar_bgs_ar_plan_visit0;
    local float ar_bgs_ar_plan_visit1;
    local float ar_bgs_ar_plan_visit2;
    local float ar_bgs_ar_plan_visit3;
    local float ar_bgs_ar_aimvel;
    local vector ar_bgs_ar_aimoff;
    local vector ar_bgs_ar_aimprev;
    local float ar_bgs_ar_errtime;
    local float ar_bgs_ar_aimblend;
    local entity ar_bgs_ar_mottarget;
    local vector ar_bgs_ar_motpos;
    local float ar_bgs_ar_mottime;
    local vector ar_bgs_ar_motoff;
    local vector ar_bgs_ar_motprev;
    local float ar_bgs_ar_motblend;
    local float ar_bgs_ar_retreating;
    local float ar_bgs_ar_dodgetime;
    local float ar_bgs_ar_tactic;
    local float ar_bgs_ar_tactic_until;
    local float ar_bgs_ar_tactic_check;
    local float ar_bgs_ar_tactic_cool;
    local entity ar_bgs_ar_tactic_hop;
    local entity ar_bgs_ar_tactic_cover;
    local entity ar_bgs_ar_tactic_exit;
    local float ar_bgs_ar_tactic_speed;
    local float ar_bgs_ar_hopjump;
    local float ar_bgs_ar_hoprj;
    local float ar_bgs_ar_hoplift;
    local float ar_bgs_ar_hopswim;
    local float ar_bgs_ar_hoptrain;
    local float ar_bgs_ar_hopdoor;
    local float ar_bgs_ar_sprintstate;
    local float ar_bgs_ar_jump;
    local float ar_bgs_ar_fireready;
    local float ar_bgs_ar_fireburst;
    local float ar_bgs_ar_fireweapon;
    local vector ar_bgs_ar_sndpos;
    local float ar_bgs_ar_sndtime;
    local entity ar_bgs_ar_huntitem;
    local float ar_bgs_ar_hunttime;
    local entity ar_bgs_ar_obsenemy;
    local vector ar_bgs_ar_obsvelocity;
    local float ar_bgs_ar_obspower;
    local float ar_bgs_ar_obsground;
    local float ar_bgs_ar_obsair;
    local vector ar_bgs_ar_secondarypos;
    local float ar_bgs_ar_threatclass;
    local float ar_bgs_ar_threatlog;
    local entity ar_bgs_ar_secondary;
    local float ar_bgs_ar_secondaryscan;
    local entity b, oldother, oldtrace;
    local vector f, r, u, endpoint, normal;
    local float fraction, allsolid, startsolid, plane, next;
    b = self; oldother = other; oldtrace = trace_ent;
    f = v_forward; r = v_right; u = v_up;
    endpoint = trace_endpos; normal = trace_plane_normal;
    fraction = trace_fraction; allsolid = trace_allsolid;
    startsolid = trace_startsolid; plane = trace_plane_dist;
    next = self.ar_bd_next;
    ar_bgs_origin = self.origin;
    ar_bgs_velocity = self.velocity;
    ar_bgs_angles = self.angles;
    ar_bgs_v_angle = self.v_angle;
    ar_bgs_health = self.health;
    ar_bgs_armorvalue = self.armorvalue;
    ar_bgs_armortype = self.armortype;
    ar_bgs_items = self.items;
    ar_bgs_weapon = self.weapon;
    ar_bgs_ammo_shells = self.ammo_shells;
    ar_bgs_ammo_nails = self.ammo_nails;
    ar_bgs_ammo_rockets = self.ammo_rockets;
    ar_bgs_ammo_cells = self.ammo_cells;
    ar_bgs_flags = self.flags;
    ar_bgs_solid = self.solid;
    ar_bgs_movetype = self.movetype;
    ar_bgs_takedamage = self.takedamage;
    ar_bgs_button0 = self.button0;
    ar_bgs_button1 = self.button1;
    ar_bgs_button2 = self.button2;
    ar_bgs_attack_finished = self.attack_finished;
    ar_bgs_nextthink = self.nextthink;
    ar_bgs_think = self.think;
    ar_bgs_touch = self.touch;
    ar_bgs_th_pain = self.th_pain;
    ar_bgs_ar_enemy = self.ar_enemy;
    ar_bgs_ar_seen = self.ar_seen;
    ar_bgs_ar_lastseen = self.ar_lastseen;
    ar_bgs_ar_lastfoe = self.ar_lastfoe;
    ar_bgs_ar_goal = self.ar_goal;
    ar_bgs_ar_node = self.ar_node;
    ar_bgs_ar_pending = self.ar_pending;
    ar_bgs_ar_shopping = self.ar_shopping;
    ar_bgs_ar_routegen = self.ar_routegen;
    ar_bgs_ar_mode = self.ar_mode;
    ar_bgs_ar_moveyaw = self.ar_moveyaw;
    ar_bgs_ar_nextai = self.ar_nextai;
    ar_bgs_ar_nextlog = self.ar_nextlog;
    ar_bgs_ar_nextstall = self.ar_nextstall;
    ar_bgs_ar_react = self.ar_react;
    ar_bgs_ar_track = self.ar_track;
    ar_bgs_ar_plan_goal = self.ar_plan_goal;
    ar_bgs_ar_plan_leg = self.ar_plan_leg;
    ar_bgs_ar_plan_best = self.ar_plan_best;
    ar_bgs_ar_plan_stamp = self.ar_plan_stamp;
    ar_bgs_ar_fetchfailed = self.ar_fetchfailed;
    ar_bgs_ar_fetchcool = self.ar_fetchcool;
    ar_bgs_ar_actionnode = self.ar_actionnode;
    ar_bgs_ar_actiongoal = self.ar_actiongoal;
    ar_bgs_ar_actionbest = self.ar_actionbest;
    ar_bgs_ar_actiontime = self.ar_actiontime;
    ar_bgs_ar_plan_visit0 = self.ar_plan_visit0;
    ar_bgs_ar_plan_visit1 = self.ar_plan_visit1;
    ar_bgs_ar_plan_visit2 = self.ar_plan_visit2;
    ar_bgs_ar_plan_visit3 = self.ar_plan_visit3;
    ar_bgs_ar_aimvel = self.ar_aimvel;
    ar_bgs_ar_aimoff = self.ar_aimoff;
    ar_bgs_ar_aimprev = self.ar_aimprev;
    ar_bgs_ar_errtime = self.ar_errtime;
    ar_bgs_ar_aimblend = self.ar_aimblend;
    ar_bgs_ar_mottarget = self.ar_mottarget;
    ar_bgs_ar_motpos = self.ar_motpos;
    ar_bgs_ar_mottime = self.ar_mottime;
    ar_bgs_ar_motoff = self.ar_motoff;
    ar_bgs_ar_motprev = self.ar_motprev;
    ar_bgs_ar_motblend = self.ar_motblend;
    ar_bgs_ar_retreating = self.ar_retreating;
    ar_bgs_ar_dodgetime = self.ar_dodgetime;
    ar_bgs_ar_tactic = self.ar_tactic;
    ar_bgs_ar_tactic_until = self.ar_tactic_until;
    ar_bgs_ar_tactic_check = self.ar_tactic_check;
    ar_bgs_ar_tactic_cool = self.ar_tactic_cool;
    ar_bgs_ar_tactic_hop = self.ar_tactic_hop;
    ar_bgs_ar_tactic_cover = self.ar_tactic_cover;
    ar_bgs_ar_tactic_exit = self.ar_tactic_exit;
    ar_bgs_ar_tactic_speed = self.ar_tactic_speed;
    ar_bgs_ar_hopjump = self.ar_hopjump;
    ar_bgs_ar_hoprj = self.ar_hoprj;
    ar_bgs_ar_hoplift = self.ar_hoplift;
    ar_bgs_ar_hopswim = self.ar_hopswim;
    ar_bgs_ar_hoptrain = self.ar_hoptrain;
    ar_bgs_ar_hopdoor = self.ar_hopdoor;
    ar_bgs_ar_sprintstate = self.ar_sprintstate;
    ar_bgs_ar_jump = self.ar_jump;
    ar_bgs_ar_fireready = self.ar_fireready;
    ar_bgs_ar_fireburst = self.ar_fireburst;
    ar_bgs_ar_fireweapon = self.ar_fireweapon;
    ar_bgs_ar_sndpos = self.ar_sndpos;
    ar_bgs_ar_sndtime = self.ar_sndtime;
    ar_bgs_ar_huntitem = self.ar_huntitem;
    ar_bgs_ar_hunttime = self.ar_hunttime;
    ar_bgs_ar_obsenemy = self.ar_obsenemy;
    ar_bgs_ar_obsvelocity = self.ar_obsvelocity;
    ar_bgs_ar_obspower = self.ar_obspower;
    ar_bgs_ar_obsground = self.ar_obsground;
    ar_bgs_ar_obsair = self.ar_obsair;
    ar_bgs_ar_secondarypos = self.ar_secondarypos;
    ar_bgs_ar_threatclass = self.ar_threatclass;
    ar_bgs_ar_threatlog = self.ar_threatlog;
    ar_bgs_ar_secondary = self.ar_secondary;
    ar_bgs_ar_secondaryscan = self.ar_secondaryscan;
    Argus_BehaviourObserve ();
    ar_bf_checks = ar_bf_checks + 1;
    if (self.ar_bd_next != next) ar_bf_emits = ar_bf_emits + 1;
    if (self != b || other != oldother || trace_ent != oldtrace
        || v_forward != f || v_right != r || v_up != u
        || trace_endpos != endpoint || trace_plane_normal != normal
        || trace_fraction != fraction || trace_allsolid != allsolid
        || trace_startsolid != startsolid || trace_plane_dist != plane)
        ar_bf_guardok = 0;
    if (b.origin != ar_bgs_origin) ar_bf_guardok = 0;
    if (b.velocity != ar_bgs_velocity) ar_bf_guardok = 0;
    if (b.angles != ar_bgs_angles) ar_bf_guardok = 0;
    if (b.v_angle != ar_bgs_v_angle) ar_bf_guardok = 0;
    if (b.health != ar_bgs_health) ar_bf_guardok = 0;
    if (b.armorvalue != ar_bgs_armorvalue) ar_bf_guardok = 0;
    if (b.armortype != ar_bgs_armortype) ar_bf_guardok = 0;
    if (b.items != ar_bgs_items) ar_bf_guardok = 0;
    if (b.weapon != ar_bgs_weapon) ar_bf_guardok = 0;
    if (b.ammo_shells != ar_bgs_ammo_shells) ar_bf_guardok = 0;
    if (b.ammo_nails != ar_bgs_ammo_nails) ar_bf_guardok = 0;
    if (b.ammo_rockets != ar_bgs_ammo_rockets) ar_bf_guardok = 0;
    if (b.ammo_cells != ar_bgs_ammo_cells) ar_bf_guardok = 0;
    if (b.flags != ar_bgs_flags) ar_bf_guardok = 0;
    if (b.solid != ar_bgs_solid) ar_bf_guardok = 0;
    if (b.movetype != ar_bgs_movetype) ar_bf_guardok = 0;
    if (b.takedamage != ar_bgs_takedamage) ar_bf_guardok = 0;
    if (b.button0 != ar_bgs_button0) ar_bf_guardok = 0;
    if (b.button1 != ar_bgs_button1) ar_bf_guardok = 0;
    if (b.button2 != ar_bgs_button2) ar_bf_guardok = 0;
    if (b.attack_finished != ar_bgs_attack_finished) ar_bf_guardok = 0;
    if (b.nextthink != ar_bgs_nextthink) ar_bf_guardok = 0;
    if (b.think != ar_bgs_think) ar_bf_guardok = 0;
    if (b.touch != ar_bgs_touch) ar_bf_guardok = 0;
    if (b.th_pain != ar_bgs_th_pain) ar_bf_guardok = 0;
    if (b.ar_enemy != ar_bgs_ar_enemy) ar_bf_guardok = 0;
    if (b.ar_seen != ar_bgs_ar_seen) ar_bf_guardok = 0;
    if (b.ar_lastseen != ar_bgs_ar_lastseen) ar_bf_guardok = 0;
    if (b.ar_lastfoe != ar_bgs_ar_lastfoe) ar_bf_guardok = 0;
    if (b.ar_goal != ar_bgs_ar_goal) ar_bf_guardok = 0;
    if (b.ar_node != ar_bgs_ar_node) ar_bf_guardok = 0;
    if (b.ar_pending != ar_bgs_ar_pending) ar_bf_guardok = 0;
    if (b.ar_shopping != ar_bgs_ar_shopping) ar_bf_guardok = 0;
    if (b.ar_routegen != ar_bgs_ar_routegen) ar_bf_guardok = 0;
    if (b.ar_mode != ar_bgs_ar_mode) ar_bf_guardok = 0;
    if (b.ar_moveyaw != ar_bgs_ar_moveyaw) ar_bf_guardok = 0;
    if (b.ar_nextai != ar_bgs_ar_nextai) ar_bf_guardok = 0;
    if (b.ar_nextlog != ar_bgs_ar_nextlog) ar_bf_guardok = 0;
    if (b.ar_nextstall != ar_bgs_ar_nextstall) ar_bf_guardok = 0;
    if (b.ar_react != ar_bgs_ar_react) ar_bf_guardok = 0;
    if (b.ar_track != ar_bgs_ar_track) ar_bf_guardok = 0;
    if (b.ar_plan_goal != ar_bgs_ar_plan_goal) ar_bf_guardok = 0;
    if (b.ar_plan_leg != ar_bgs_ar_plan_leg) ar_bf_guardok = 0;
    if (b.ar_plan_best != ar_bgs_ar_plan_best) ar_bf_guardok = 0;
    if (b.ar_plan_stamp != ar_bgs_ar_plan_stamp) ar_bf_guardok = 0;
    if (b.ar_fetchfailed != ar_bgs_ar_fetchfailed) ar_bf_guardok = 0;
    if (b.ar_fetchcool != ar_bgs_ar_fetchcool) ar_bf_guardok = 0;
    if (b.ar_actionnode != ar_bgs_ar_actionnode) ar_bf_guardok = 0;
    if (b.ar_actiongoal != ar_bgs_ar_actiongoal) ar_bf_guardok = 0;
    if (b.ar_actionbest != ar_bgs_ar_actionbest) ar_bf_guardok = 0;
    if (b.ar_actiontime != ar_bgs_ar_actiontime) ar_bf_guardok = 0;
    if (b.ar_plan_visit0 != ar_bgs_ar_plan_visit0) ar_bf_guardok = 0;
    if (b.ar_plan_visit1 != ar_bgs_ar_plan_visit1) ar_bf_guardok = 0;
    if (b.ar_plan_visit2 != ar_bgs_ar_plan_visit2) ar_bf_guardok = 0;
    if (b.ar_plan_visit3 != ar_bgs_ar_plan_visit3) ar_bf_guardok = 0;
    if (b.ar_aimvel != ar_bgs_ar_aimvel) ar_bf_guardok = 0;
    if (b.ar_aimoff != ar_bgs_ar_aimoff) ar_bf_guardok = 0;
    if (b.ar_aimprev != ar_bgs_ar_aimprev) ar_bf_guardok = 0;
    if (b.ar_errtime != ar_bgs_ar_errtime) ar_bf_guardok = 0;
    if (b.ar_aimblend != ar_bgs_ar_aimblend) ar_bf_guardok = 0;
    if (b.ar_mottarget != ar_bgs_ar_mottarget) ar_bf_guardok = 0;
    if (b.ar_motpos != ar_bgs_ar_motpos) ar_bf_guardok = 0;
    if (b.ar_mottime != ar_bgs_ar_mottime) ar_bf_guardok = 0;
    if (b.ar_motoff != ar_bgs_ar_motoff) ar_bf_guardok = 0;
    if (b.ar_motprev != ar_bgs_ar_motprev) ar_bf_guardok = 0;
    if (b.ar_motblend != ar_bgs_ar_motblend) ar_bf_guardok = 0;
    if (b.ar_retreating != ar_bgs_ar_retreating) ar_bf_guardok = 0;
    if (b.ar_dodgetime != ar_bgs_ar_dodgetime) ar_bf_guardok = 0;
    if (b.ar_tactic != ar_bgs_ar_tactic) ar_bf_guardok = 0;
    if (b.ar_tactic_until != ar_bgs_ar_tactic_until) ar_bf_guardok = 0;
    if (b.ar_tactic_check != ar_bgs_ar_tactic_check) ar_bf_guardok = 0;
    if (b.ar_tactic_cool != ar_bgs_ar_tactic_cool) ar_bf_guardok = 0;
    if (b.ar_tactic_hop != ar_bgs_ar_tactic_hop) ar_bf_guardok = 0;
    if (b.ar_tactic_cover != ar_bgs_ar_tactic_cover) ar_bf_guardok = 0;
    if (b.ar_tactic_exit != ar_bgs_ar_tactic_exit) ar_bf_guardok = 0;
    if (b.ar_tactic_speed != ar_bgs_ar_tactic_speed) ar_bf_guardok = 0;
    if (b.ar_hopjump != ar_bgs_ar_hopjump) ar_bf_guardok = 0;
    if (b.ar_hoprj != ar_bgs_ar_hoprj) ar_bf_guardok = 0;
    if (b.ar_hoplift != ar_bgs_ar_hoplift) ar_bf_guardok = 0;
    if (b.ar_hopswim != ar_bgs_ar_hopswim) ar_bf_guardok = 0;
    if (b.ar_hoptrain != ar_bgs_ar_hoptrain) ar_bf_guardok = 0;
    if (b.ar_hopdoor != ar_bgs_ar_hopdoor) ar_bf_guardok = 0;
    if (b.ar_sprintstate != ar_bgs_ar_sprintstate) ar_bf_guardok = 0;
    if (b.ar_jump != ar_bgs_ar_jump) ar_bf_guardok = 0;
    if (b.ar_fireready != ar_bgs_ar_fireready) ar_bf_guardok = 0;
    if (b.ar_fireburst != ar_bgs_ar_fireburst) ar_bf_guardok = 0;
    if (b.ar_fireweapon != ar_bgs_ar_fireweapon) ar_bf_guardok = 0;
    if (b.ar_sndpos != ar_bgs_ar_sndpos) ar_bf_guardok = 0;
    if (b.ar_sndtime != ar_bgs_ar_sndtime) ar_bf_guardok = 0;
    if (b.ar_huntitem != ar_bgs_ar_huntitem) ar_bf_guardok = 0;
    if (b.ar_hunttime != ar_bgs_ar_hunttime) ar_bf_guardok = 0;
    if (b.ar_obsenemy != ar_bgs_ar_obsenemy) ar_bf_guardok = 0;
    if (b.ar_obsvelocity != ar_bgs_ar_obsvelocity) ar_bf_guardok = 0;
    if (b.ar_obspower != ar_bgs_ar_obspower) ar_bf_guardok = 0;
    if (b.ar_obsground != ar_bgs_ar_obsground) ar_bf_guardok = 0;
    if (b.ar_obsair != ar_bgs_ar_obsair) ar_bf_guardok = 0;
    if (b.ar_secondarypos != ar_bgs_ar_secondarypos) ar_bf_guardok = 0;
    if (b.ar_threatclass != ar_bgs_ar_threatclass) ar_bf_guardok = 0;
    if (b.ar_threatlog != ar_bgs_ar_threatlog) ar_bf_guardok = 0;
    if (b.ar_secondary != ar_bgs_ar_secondary) ar_bf_guardok = 0;
    if (b.ar_secondaryscan != ar_bgs_ar_secondaryscan) ar_bf_guardok = 0;
};
// END observer guard

void() Argus_BehaviourCheckedObserve =
{
    if (ar_bf_active && self == ar_bf_bot) Argus_BehaviourFixtureGuard ();
    else Argus_BehaviourObserve ();
};

// Independent ordinary-match cadence probe. No encounter setup, traces,
// RNG or gameplay writes. The same five-second record runs in every arm.
// Milliseconds avoid vanilla ftos rounding played-rate frametime to zero.
float ar_bt_frames, ar_bt_seconds, ar_bt_max, ar_bt_over20, ar_bt_over50;
void() Argus_BehaviourTiming =
{
    if (!cvar ("developer") || cvar ("scratch1") != 591)
    {
        ar_bt_frames = 0; ar_bt_seconds = 0; ar_bt_max = 0;
        ar_bt_over20 = 0; ar_bt_over50 = 0;
        return;
    }
    ar_bt_frames = ar_bt_frames + 1;
    ar_bt_seconds = ar_bt_seconds + frametime;
    if (frametime > ar_bt_max) ar_bt_max = frametime;
    if (frametime > 0.020) ar_bt_over20 = ar_bt_over20 + 1;
    if (frametime > 0.050) ar_bt_over50 = ar_bt_over50 + 1;
    if (ar_bt_seconds < 5) return;
    Argus_BehaviourPrint ("BHVTIME t ", ftos (time), " frames ");
    Argus_BehaviourPrint (ftos (ar_bt_frames), " seconds ", "");
    Argus_BehaviourPrint (ftos (ar_bt_seconds), " mean_ms ", "");
    Argus_BehaviourPrint (ftos (1000 * ar_bt_seconds / ar_bt_frames), " max_ms ", "");
    Argus_BehaviourPrint (ftos (1000 * ar_bt_max), " over20 ", "");
    Argus_BehaviourPrint (ftos (ar_bt_over20), " over50 ", "");
    Argus_BehaviourPrint (ftos (ar_bt_over50), "\n", "");
    ar_bt_frames = 0; ar_bt_seconds = 0; ar_bt_max = 0;
    ar_bt_over20 = 0; ar_bt_over50 = 0;
};

void() Argus_BehaviourFixturePre =
{
    local entity missile;
    local float visible;
    Argus_BehaviourTiming ();
    Argus_PerceptionFixtureTick ();
    if (!ar_bf_active) return;
    ar_bf_frames = ar_bf_frames + 1;
    missile = find (world, classname, "rocket");
    while (missile != world)
    {
        if (missile.owner == ar_bf_bot && !missile.ar_bf_rocket_seen)
        { missile.ar_bf_rocket_seen = 1; ar_bf_launches = ar_bf_launches + 1; }
        missile = find (missile, classname, "rocket");
    }
    if (time >= ar_tacfixture_until)
    {
        ar_bf_ended = 1;
        dprint ("BHVFIX end frames "); dprint (ftos (ar_bf_frames));
        dprint (" seconds "); dprint (ftos (time - ar_bf_begin)); dprint ("\n");
        return;
    }
    if (time < ar_bf_next) return;
    ar_bf_next = time + 0.1;
    // Independent geometric visibility, never calls the bot's perception.
    traceline (ar_bf_bot.origin + '0 0 22', ar_bf_target.origin + '0 0 22', TRUE, ar_bf_bot);
    visible = trace_fraction == 1;
    dprint ("BHVFIX sample "); dprint (ftos (time - ar_bf_begin));
    dprint (" pos "); dprint (vtos (ar_bf_bot.origin));
    dprint (" visible "); dprint (ftos (visible));
    dprint (" launches "); dprint (ftos (ar_bf_launches));
    dprint (" targethp "); dprint (ftos (ar_bf_target.health));
    dprint (" hp "); dprint (ftos (ar_bf_bot.health));
    dprint (" invariant "); dprint (ftos (ar_bf_guardok)); dprint ("\n");
    dprint ("BHVFIX guard checks "); dprint (ftos (ar_bf_checks));
    dprint (" emits "); dprint (ftos (ar_bf_emits)); dprint ("\n");
};

void() Argus_BehaviourFixturePost =
{
    local entity b, saved;
    local float clean;
    if (!ar_bf_active || ar_tacfixture_until) return;
    clean = ar_bf_ended && ar_tf_target == world && ar_tf_secondary == world
            && ar_tacfixture_bot == world;
    b = argus_bots;
    while (b != world)
    {
        if (b != ar_bf_bot && (b.solid != b.ar_tf_solid || b.cam_active != b.ar_tf_camera)) clean = 0;
        if (b.ar_enemy == ar_bf_target || b.ar_lastfoe == ar_bf_target
            || b.ar_secondary == ar_bf_target || b.ar_mottarget == ar_bf_target) clean = 0;
        saved = self; self = b; Argus_BehaviourReset (); self = saved;
        b = b.ar_chain;
    }
    b = argus_itemchain;
    while (b != world)
    { if (b.ar_tf_weapon) clean = 0; b = b.ar_nextitem; }
    ar_bf_bot = world; ar_bf_target = world; ar_bf_active = 0;
    dprint ("BHVFIX cleanup "); dprint (ftos (ar_bf_id));
    dprint (" restored "); dprint (ftos (clean));
    dprint (" invariant "); dprint (ftos (ar_bf_guardok)); dprint ("\n");
    dprint ("BHVFIX done "); dprint (ftos (ar_bf_id)); dprint ("\n");
};

// Directed observation tests use a PRIVATE constant-input build. Production
// random() stays builtin 7 and this flag stays zero. A normal game refuses
// this destructive fixture even when the developer impulse is armed.
float ar_pf_inputfixed, ar_pf_active, ar_pf_id, ar_pf_begin, ar_pf_frames;
float ar_pf_checks, ar_pf_ok, ar_pf_ring;
entity ar_pf_a, ar_pf_b, ar_pf_target;
vector ar_pf_seat, ar_pf_visible, ar_pf_hide, ar_pf_hide2;
.float ar_pf_solid, ar_pf_camera, ar_pf_button, ar_pf_damage;

void(string label, float ok) Argus_PerceptionCheck =
{
    ar_pf_checks = ar_pf_checks + 1;
    if (!ok) ar_pf_ok = 0;
    dprint ("PERFIX check "); dprint (ftos (ar_pf_id));
    dprint (" "); dprint (label); dprint (" "); dprint (ftos (ok)); dprint ("\n");
};

// Reset decision inputs, not the observation sample. Neither observer runs
// through FrameAll: both are disposable nonsolid edicts at the same seat.
void(entity b, float gun, float hp) Argus_PerceptionProbe =
{
    b.classname = "perceptionprobe"; b.netname = "perceptionprobe";
    b.ar_isbot = 1; b.solid = SOLID_NOT; b.movetype = MOVETYPE_NONE;
    b.health = hp; b.armorvalue = 0; b.armortype = 0;
    b.items = IT_AXE | gun; b.weapon = gun;
    b.ammo_shells = 100; b.ammo_nails = 100;
    b.ammo_rockets = 100; b.ammo_cells = 100; b.currentammo = 100;
    b.flags = FL_ONGROUND; b.velocity = '0 0 0';
    b.ar_slot = 0; b.ar_skill = 1; b.ar_aimerr = 0;
    b.ar_spring_k = 400; b.ar_damping_c = 40;
    b.ar_aimvel = 0; b.ar_aimoff = '0 0 0'; b.ar_aimprev = '0 0 0';
    b.ar_mottarget = world; b.ar_motoff = '0 0 0'; b.ar_motprev = '0 0 0';
    b.ar_track = time - 1; b.ar_react = time - 1;
    b.ar_errtime = time + 10; b.ar_tremtime = time + 10;
    b.ar_strafetime = time + 10; b.ar_strafedir = 1;
    b.ar_dodgecheck = time + 10; b.ar_dodgetime = 0;
    b.ar_secondaryscan = time + 10; b.ar_secondary = world;
    b.ar_bitemscan = time + 10; b.ar_bitem = world;
    b.ar_retreating = 0; b.ar_retreatclass = AR_THREAT_UNKNOWN;
    b.ar_covertime = 0; b.ar_tactic = 0; b.ar_tactic_check = time + 10;
    b.ar_tactic_settle = 0; b.ar_tactic_cool = time + 10;
    b.ar_fireweapon = gun; b.ar_fireburst = 0; b.ar_fireready = 0;
    b.attack_finished = time + 10; b.button0 = 0; b.button2 = 0;
    b.ar_glimpse = time + 10; b.ar_wetlevel = 0;
    setorigin (b, ar_pf_seat);
    b.angles = vectoangles (ar_pf_visible - ar_pf_seat); b.angles_x = 0;
    b.v_angle = '0 0 0'; b.ar_moveyaw = b.angles_y;
};

float() Argus_PerceptionPairEqual =
{
    return ar_pf_a.angles == ar_pf_b.angles
        && ar_pf_a.v_angle == ar_pf_b.v_angle
        && ar_pf_a.ar_aimvel == ar_pf_b.ar_aimvel
        && ar_pf_a.ar_moveyaw == ar_pf_b.ar_moveyaw
        && ar_pf_a.ar_retreating == ar_pf_b.ar_retreating
        && ar_pf_a.ar_retreatclass == ar_pf_b.ar_retreatclass
        && ar_pf_a.weapon == ar_pf_b.weapon
        && ar_pf_a.button0 == ar_pf_b.button0
        && ar_pf_a.ar_lastseen == ar_pf_b.ar_lastseen
        && ar_pf_a.ar_obsvelocity == ar_pf_b.ar_obsvelocity
        && ar_pf_a.ar_obspower == ar_pf_b.ar_obspower
        && ar_pf_a.ar_obsground == ar_pf_b.ar_obsground
        && ar_pf_a.ar_obsair == ar_pf_b.ar_obsair
        && ar_pf_a.ar_glimpse == ar_pf_b.ar_glimpse;
};

void() Argus_PerceptionFixture =
{
    local entity b, saved;
    local vector delta;
    local float i, id, ring;
    if (!cvar ("developer") || cvar ("scratch1") != 593
        || !(self.flags & FL_CLIENT) || self.ar_isbot) return;
    if (!ar_pf_inputfixed)
    { dprint ("PERFIX refused controlled_inputs_required\n"); return; }
    if (ar_pf_active || ar_bf_active || ar_tacfixture_until)
    { dprint ("PERFIX busy\n"); return; }
    id = cvar ("scratch3"); ring = cvar ("scratch2");
    if (id < 1 || id != floor (id) || (ring != 0 && ring != 1))
    { dprint ("PERFIX refused invalid_trial\n"); return; }
    // Swap the independently proven tactical opening/enemy seats: the
    // tactical cover is then a hidden target position from this observer.
    if (mapname == "dm2")
    { ar_pf_seat = '2433 -183 24'; ar_pf_visible = '2209 -279 24'; ar_pf_hide = '2177 -23 24'; }
    else if (mapname == "dm4")
    { ar_pf_seat = '337 -247 -296'; ar_pf_visible = '465 -279 -104'; ar_pf_hide = '561 -183 -104'; }
    else { dprint ("PERFIX refused unsupported_map\n"); return; }
    // Two distinct hidden positions, proved with world traces rather than
    // the bot's perception result. Refuse if the geometry premise fails.
    traceline (ar_pf_seat + '0 0 22', ar_pf_visible + '0 0 22', TRUE, self);
    if (trace_fraction != 1) { dprint ("PERFIX refused visible_geometry\n"); return; }
    traceline (ar_pf_seat + '0 0 22', ar_pf_hide + '0 0 22', TRUE, self);
    if (trace_fraction == 1) { dprint ("PERFIX refused hidden_geometry\n"); return; }
    ar_pf_hide2 = ar_pf_hide;
    i = 0;
    while (i < 4 && ar_pf_hide2 == ar_pf_hide)
    {
        delta = '16 0 0';
        if (i == 1) delta = '-16 0 0';
        if (i == 2) delta = '0 16 0';
        if (i == 3) delta = '0 -16 0';
        traceline (ar_pf_seat + '0 0 22', ar_pf_hide + delta + '0 0 22', TRUE, self);
        if (trace_fraction < 1 && pointcontents (ar_pf_hide + delta) != CONTENT_SOLID)
            ar_pf_hide2 = ar_pf_hide + delta;
        i = i + 1;
    }
    if (ar_pf_hide2 == ar_pf_hide) { dprint ("PERFIX refused second_hidden_geometry\n"); return; }
    ar_pf_id = id; ar_pf_ring = ring; ar_pf_begin = time;
    ar_pf_frames = 0; ar_pf_checks = 0; ar_pf_ok = 1;
    // Quarantine before any live state is frozen or disposable edict spawned.
    dprint ("BHVFIX begin perception\n");
    b = argus_bots;
    while (b != world)
    {
        b.ar_pf_solid = b.solid; b.ar_pf_camera = b.cam_active; b.ar_pf_button = b.button0;
        b.ar_pf_damage = b.takedamage; b.takedamage = DAMAGE_NO;
        b.solid = SOLID_NOT; b.cam_active = 1; b.button0 = 0;
        b = b.ar_chain;
    }
    ar_pf_target = spawn (); ar_pf_a = spawn (); ar_pf_b = spawn ();
    ar_pf_target.classname = "player"; ar_pf_target.netname = "perceptiontarget";
    ar_pf_target.ar_isbot = 1; ar_pf_target.health = 100;
    ar_pf_target.movetype = MOVETYPE_NONE; ar_pf_target.solid = SOLID_NOT;
    ar_pf_target.takedamage = DAMAGE_NO; ar_pf_target.flags = FL_ONGROUND;
    ar_pf_target.weapon = IT_SHOTGUN; ar_pf_target.velocity = '100 30 40';
    ar_pf_target.invisible_finished = 0;
    if (ring) ar_pf_target.invisible_finished = time + 20;
    setorigin (ar_pf_target, ar_pf_visible);
    saved = self; self = ar_pf_a;
    Argus_PerceptionProbe (self, IT_ROCKET_LAUNCHER, 100);
    self.ar_enemy = ar_pf_target;
    if (Argus_CanSee (ar_pf_target)) Argus_ObserveEnemy (ar_pf_target);
    self = ar_pf_b;
    Argus_PerceptionProbe (self, IT_ROCKET_LAUNCHER, 100);
    self.ar_enemy = ar_pf_target;
    if (Argus_CanSee (ar_pf_target)) Argus_ObserveEnemy (ar_pf_target);
    self = saved; ar_pf_active = 1;
    dprint ("PERFIX begin "); dprint (mapname); dprint (" id "); dprint (ftos (id));
    dprint (" ring "); dprint (ftos (ring)); dprint ("\n");
};

void() Argus_PerceptionFixtureTick =
{
    local entity saved, b, extra, oldroster;
    local float i, gun, hp, owned, frameage, ok, clean, calls, draws;
    local vector predicted;
    local float fraction, allsolid, startsolid, plane, inopen, inwater;
    local vector endpoint, normal;
    local entity hit;
    if (!ar_pf_active) return;
    ar_pf_frames = ar_pf_frames + 1;
    if (time < ar_pf_begin + 0.2) return;
    saved = self;
    frameage = time - ar_pf_begin;
    Argus_PerceptionCheck ("clock", frameage >= 0.19 && frameage < 0.4);
    Argus_PerceptionCheck ("initial_observation", ar_pf_a.ar_obsenemy == ar_pf_target
        && ar_pf_b.ar_obsenemy == ar_pf_target && ar_pf_a.ar_lastseen == ar_pf_visible
        && ar_pf_a.ar_obspower == ar_pf_ring * 4);
    if (cvar ("scratch4") == 594) Argus_HealthFixtureChecks ();
    i = 0;
    while (i < 6)
    {
        gun = IT_ROCKET_LAUNCHER; hp = 100;
        if (i == 1) gun = IT_NAILGUN;
        if (i == 2) gun = IT_GRENADE_LAUNCHER;
        if (i == 3) gun = IT_SHOTGUN;
        if (i == 4) gun = IT_LIGHTNING;
        if (i == 5) hp = 60;
        self = ar_pf_a; Argus_PerceptionProbe (self, gun, hp);
        setorigin (ar_pf_target, ar_pf_hide);
        ar_pf_target.velocity = '-300 100 0'; ar_pf_target.flags = FL_ONGROUND;
        ar_pf_target.weapon = IT_AXE; ar_pf_target.waterlevel = 0;
        ar_pf_target.super_damage_finished = 0; ar_pf_target.invincible_finished = 0;
        ar_pf_target.invisible_finished = 0;
        calls = ar_pf_rngcalls;
        owned = Argus_Combat ();
        draws = ar_pf_rngcalls - calls;
        self = ar_pf_b; Argus_PerceptionProbe (self, gun, hp);
        setorigin (ar_pf_target, ar_pf_hide2);
        ar_pf_target.velocity = '500 -300 250'; ar_pf_target.flags = 0;
        ar_pf_target.weapon = IT_LIGHTNING; ar_pf_target.waterlevel = 2;
        ar_pf_target.super_damage_finished = time + 20;
        ar_pf_target.invincible_finished = time + 20;
        ar_pf_target.invisible_finished = time + 20;
        calls = ar_pf_rngcalls;
        ok = Argus_Combat ();
        Argus_PerceptionCheck ("hidden_pair", owned && ok && Argus_PerceptionPairEqual ()
            && ar_pf_rngcalls - calls == draws);
        i = i + 1;
    }
    // Reacquisition must actually replace the stale sample, including cues
    // that changed while hidden. This calls the real perception entry point.
    setorigin (ar_pf_target, ar_pf_visible);
    ar_pf_target.velocity = '20 90 0'; ar_pf_target.flags = 0;
    ar_pf_target.waterlevel = 0; ar_pf_target.invisible_finished = 0;
    ar_pf_target.weapon = IT_ROCKET_LAUNCHER;
    self = ar_pf_a; Argus_Perceive ();
    Argus_PerceptionCheck ("reacquired", self.ar_obsenemy == ar_pf_target && self.ar_seen == time
        && self.ar_lastseen == ar_pf_visible && self.ar_obsvelocity == '20 90 0'
        && self.ar_obspower == 3 && !self.ar_obsground && self.ar_obsair
        && self.ar_threatclass == AR_THREAT_SPLASH);
    self.ar_seen = time - 10;
    self.ar_obsvelocity = '10000 5000 0';
    predicted = Argus_EnemyPosition ();
    Argus_PerceptionCheck ("prediction_bound", vlen (predicted - self.ar_lastseen) <= 128.01
        && vlen (predicted - self.ar_lastseen) > 127);
    // Unseen pain is pressure, never a visual observation. Then visible
    // pain must acquire normally, without a manufactured sight stamp.
    Argus_ObservationReset (); self.ar_enemy = world;
    setorigin (ar_pf_target, ar_pf_hide);
    traceline (self.origin + '0 0 22', self.origin - '0 0 128', TRUE, self);
    fraction = trace_fraction; allsolid = trace_allsolid; startsolid = trace_startsolid;
    plane = trace_plane_dist; endpoint = trace_endpos; normal = trace_plane_normal;
    inopen = trace_inopen; inwater = trace_inwater; hit = trace_ent;
    Argus_Pain (ar_pf_target, 10);
    Argus_PerceptionCheck ("unseen_pain", self.ar_enemy == world && self.ar_seen == 0
        && self.ar_obsenemy == world && self.ar_track == time);
    Argus_PerceptionCheck ("unseen_pain_trace", trace_fraction == fraction
        && trace_allsolid == allsolid && trace_startsolid == startsolid && trace_plane_dist == plane
        && trace_endpos == endpoint && trace_plane_normal == normal && trace_inopen == inopen
        && trace_inwater == inwater && trace_ent == hit);
    setorigin (ar_pf_target, ar_pf_visible); Argus_Pain (ar_pf_target, 10);
    Argus_PerceptionCheck ("visible_pain", self.ar_enemy == ar_pf_target
        && self.ar_obsenemy == ar_pf_target && self.ar_seen == time);
    Argus_PerceptionCheck ("visible_pain_trace", trace_fraction == fraction
        && trace_allsolid == allsolid && trace_startsolid == startsolid && trace_plane_dist == plane
        && trace_endpos == endpoint && trace_plane_normal == normal && trace_inopen == inopen
        && trace_inwater == inwater && trace_ent == hit);
    extra = spawn (); extra.classname = "player"; extra.health = 100;
    extra.netname = "perceptionsecondary"; setorigin (extra, ar_pf_visible);
    self.ar_secondary = Argus_FindSecondaryThreat (ar_pf_target);
    Argus_PerceptionCheck ("secondary_observed", self.ar_secondary == extra
        && self.ar_secondarypos == ar_pf_visible);
    owned = Argus_ThreatCovered (extra, 45);
    setorigin (extra, ar_pf_hide);
    ok = Argus_ThreatCovered (extra, 45);
    setorigin (extra, ar_pf_hide2);
    Argus_PerceptionCheck ("secondary_hidden", ok == owned
        && Argus_ThreatCovered (extra, 45) == owned
        && self.ar_secondarypos == ar_pf_visible);
    // A hidden replacement must not inherit a previous opponent's sample.
    extra.classname = "perceptiontarget";
    setorigin (extra, ar_pf_hide2);
    ar_pf_target.classname = "perceptiontarget";
    self.ar_enemy = extra; Argus_Perceive ();
    Argus_PerceptionCheck ("target_switch", self.ar_obsenemy == world && self.ar_seen == 0
        && self.ar_obsvelocity == '0 0 0' && self.ar_obspower == 0);
    self.ar_enemy = ar_pf_target; ar_pf_target.health = 0; Argus_Perceive ();
    Argus_PerceptionCheck ("target_death", self.ar_enemy == world && self.ar_obsenemy == world);
    ar_pf_target.health = 100;
    self.ar_enemy = ar_pf_target; Argus_ObserveEnemy (ar_pf_target);
    Argus_BaseStats ();
    Argus_PerceptionCheck ("observer_respawn", self.ar_enemy == world && self.ar_obsenemy == world
        && self.ar_seen == 0 && self.ar_obsvelocity == '0 0 0');
    // Exercise removal against a temporary two-observer roster, then restore
    // the actual roster before the engine can run another frame.
    self = ar_pf_a; self.ar_enemy = ar_pf_target; Argus_ObserveEnemy (ar_pf_target);
    self = ar_pf_b; self.ar_enemy = ar_pf_target; Argus_ObserveEnemy (ar_pf_target);
    oldroster = argus_bots;
    ar_pf_a.ar_chain = ar_pf_b; ar_pf_b.ar_chain = world; argus_bots = ar_pf_a;
    Argus_ObservationRemoved (ar_pf_target);
    argus_bots = oldroster; ar_pf_a.ar_chain = world;
    Argus_PerceptionCheck ("roster_removal", ar_pf_a.ar_obsenemy == world && ar_pf_b.ar_obsenemy == world
        && ar_pf_a.ar_enemy == world && ar_pf_b.ar_enemy == world);
    remove (extra);
    self = saved;
    dprint ("PERFIX end "); dprint (ftos (ar_pf_id));
    dprint (" checks "); dprint (ftos (ar_pf_checks));
    dprint (" ok "); dprint (ftos (ar_pf_ok));
    dprint (" frames "); dprint (ftos (ar_pf_frames));
    dprint (" seconds "); dprint (ftos (frameage));
    dprint (" dt_ms "); dprint (ftos (frametime * 1000));
    dprint (" controlled\n");
    remove (ar_pf_a); remove (ar_pf_b); remove (ar_pf_target);
    ar_pf_a = world; ar_pf_b = world; ar_pf_target = world;
    b = argus_bots; clean = 1;
    while (b != world)
    {
        b.solid = b.ar_pf_solid; b.cam_active = b.ar_pf_camera; b.button0 = b.ar_pf_button;
        b.takedamage = b.ar_pf_damage;
        if (b.solid != b.ar_pf_solid || b.cam_active != b.ar_pf_camera) clean = 0;
        b = b.ar_chain;
    }
    ar_pf_active = 0;
    dprint ("PERFIX cleanup "); dprint (ftos (ar_pf_id));
    dprint (" restored "); dprint (ftos (clean)); dprint ("\n");
    dprint ("PERFIX done "); dprint (ftos (ar_pf_id)); dprint ("\n");
};

// Step1b extends the private PERFIX trial, including its independent BSP
// geometry, real observation interval, fixed inputs and whole-tape quarantine.
// scratch4 594 selects these checks; production cannot arm PERFIX at all.
float ar_hi_checks, ar_hi_ok;
.float ar_hi_saved_flags;

void(string label, float ok) Argus_HealthCheck =
{
    ar_hi_checks = ar_hi_checks + 1;
    if (!ok) ar_hi_ok = 0;
    dprint ("HIFIX check "); dprint (ftos (ar_pf_id));
    dprint (" "); dprint (label); dprint (" "); dprint (ftos (ok)); dprint ("\n");
};

void(float full) Argus_HealthTarget =
{
    ar_pf_target.health = 1;
    ar_pf_target.max_health = 100;
    ar_pf_target.armorvalue = 0; ar_pf_target.armortype = 0;
    ar_pf_target.items = IT_AXE | IT_SHOTGUN;
    ar_pf_target.ammo_shells = 0; ar_pf_target.ammo_nails = 0;
    ar_pf_target.ammo_rockets = 0; ar_pf_target.ammo_cells = 0;
    ar_pf_target.currentammo = 0;
    if (full)
    {
        ar_pf_target.health = 250; ar_pf_target.max_health = 200;
        ar_pf_target.armorvalue = 200; ar_pf_target.armortype = 0.8;
        ar_pf_target.items = IT_AXE | IT_SHOTGUN | IT_SUPER_SHOTGUN | IT_NAILGUN
            | IT_SUPER_NAILGUN | IT_GRENADE_LAUNCHER | IT_ROCKET_LAUNCHER | IT_LIGHTNING;
        ar_pf_target.ammo_shells = 100; ar_pf_target.ammo_nails = 200;
        ar_pf_target.ammo_rockets = 100; ar_pf_target.ammo_cells = 100;
        ar_pf_target.currentammo = 100;
    }
};

float() Argus_HealthPairEqual =
{
    return Argus_PerceptionPairEqual ()
        && ar_pf_a.ar_enemy == ar_pf_b.ar_enemy
        && ar_pf_a.ar_threatclass == ar_pf_b.ar_threatclass
        && ar_pf_a.ar_retreatlock == ar_pf_b.ar_retreatlock
        && ar_pf_a.ar_covertime == ar_pf_b.ar_covertime
        && ar_pf_a.ar_fireweapon == ar_pf_b.ar_fireweapon
        && ar_pf_a.ar_fireburst == ar_pf_b.ar_fireburst
        && ar_pf_a.ar_fireready == ar_pf_b.ar_fireready;
};

void() Argus_HealthFixtureChecks =
{
    local entity saved, it, first, second, extra, chosen, roster;
    local float i, state, hp, calls, draws, owned, ok, clean;
    local float seen, power, family, ground, air;
    local float oldcoop, olddm;
    local float isolation, packitems, packrock, packcells;
    local vector last, vel;
    local string label;
    if (!ar_pf_inputfixed || !ar_pf_active) return;
    saved = self; roster = argus_bots;
    seen = ar_pf_a.ar_seen; last = ar_pf_a.ar_lastseen;
    vel = ar_pf_a.ar_obsvelocity; power = ar_pf_a.ar_obspower;
    family = ar_pf_a.ar_threatclass; ground = ar_pf_a.ar_obsground; air = ar_pf_a.ar_obsair;
    ar_hi_checks = 0; ar_hi_ok = 1;
    dprint ("HIFIX begin "); dprint (mapname); dprint (" id "); dprint (ftos (ar_pf_id)); dprint ("\n");
    i = 0;
    while (i < 8)
    {
        state = i - floor (i / 4) * 4;
        hp = 25; if (state >= 2) hp = 60;
        setorigin (ar_pf_target, ar_pf_hide);
        if (i >= 4) setorigin (ar_pf_target, ar_pf_visible);
        ar_pf_target.weapon = IT_SHOTGUN;
        ar_pf_target.invisible_finished = 0;
        ar_pf_target.invincible_finished = 0;
        ar_pf_target.super_damage_finished = 0;
        if (state >= 2) ar_pf_target.super_damage_finished = time + 20;
        self = ar_pf_a; Argus_PerceptionProbe (self, IT_ROCKET_LAUNCHER, hp);
        self.ar_enemy = ar_pf_target; self.ar_retreatlock = time - 1;
        self.ar_retreating = state == 1 || state == 3;
        self.ar_obspower = 0; if (state >= 2) self.ar_obspower = 1;
        Argus_HealthTarget (0); calls = ar_pf_rngcalls; owned = Argus_Combat ();
        draws = ar_pf_rngcalls - calls;
        self = ar_pf_b; Argus_PerceptionProbe (self, IT_ROCKET_LAUNCHER, hp);
        self.ar_enemy = ar_pf_target; self.ar_retreatlock = time - 1;
        self.ar_retreating = state == 1 || state == 3;
        self.ar_obspower = 0; if (state >= 2) self.ar_obspower = 1;
        Argus_HealthTarget (1); calls = ar_pf_rngcalls; ok = Argus_Combat ();
        label = "hidden_enter";
        if (i == 1) label = "hidden_stay";
        if (i == 2) label = "hidden_power_enter";
        if (i == 3) label = "hidden_power_stay";
        if (i == 4) label = "visible_enter";
        if (i == 5) label = "visible_stay";
        if (i == 6) label = "visible_power_enter";
        if (i == 7) label = "visible_power_stay";
        Argus_HealthCheck (label, owned && ok && Argus_HealthPairEqual () && ar_pf_rngcalls - calls == draws);
        i = i + 1;
    }
    // Own stack still controls actual retreat: removing the finishing leak
    // must not disable defensive behaviour altogether.
    ar_pf_target.super_damage_finished = 0; ar_pf_target.health = 100;
    self = ar_pf_a; Argus_PerceptionProbe (self, IT_ROCKET_LAUNCHER, 25);
    self.ar_retreatlock = time - 1; Argus_Combat (); owned = self.ar_retreating;
    self = ar_pf_b; Argus_PerceptionProbe (self, IT_ROCKET_LAUNCHER, 100);
    self.ar_retreatlock = time - 1; Argus_Combat ();
    Argus_HealthCheck ("own_stack", owned && !self.ar_retreating);

    // Co-op's shared-target delay used to bypass itself at exact enemy HP25.
    // Exercise the real trigger branch, with an ally visibly firing nearby.
    oldcoop = coop; olddm = deathmatch; coop = 1; deathmatch = 0;
    extra = spawn (); extra.classname = "player"; extra.health = 100;
    extra.solid = SOLID_NOT; extra.button0 = 1;
    setorigin (extra, ar_pf_visible + (ar_pf_seat - ar_pf_visible) * 0.6);
    ar_pf_target.classname = "monster_ogre"; ar_pf_target.flags = FL_MONSTER;
    setorigin (ar_pf_target, ar_pf_visible);
    self = ar_pf_a; Argus_PerceptionProbe (self, IT_SHOTGUN, 100);
    self.ar_enemy = ar_pf_target; self.ar_teammate = extra; self.ar_killdelay = 0;
    ar_pf_target.health = 1; owned = Argus_Combat ();
    self = ar_pf_b; Argus_PerceptionProbe (self, IT_SHOTGUN, 100);
    self.ar_enemy = ar_pf_target; self.ar_teammate = extra; self.ar_killdelay = 0;
    ar_pf_target.health = 250; ok = Argus_Combat ();
    Argus_HealthCheck ("coop_hold_fire", owned && ok
        && ar_pf_a.ar_killdelay > time && ar_pf_a.ar_killdelay == ar_pf_b.ar_killdelay
        && ar_pf_a.button0 == 0 && ar_pf_b.button0 == 0);
    ar_pf_a.ar_teammate = world; ar_pf_b.ar_teammate = world;
    ar_pf_a.ar_killdelay = 0; ar_pf_b.ar_killdelay = 0;
    coop = oldcoop; deathmatch = olddm;
    ar_pf_target.classname = "player"; ar_pf_target.flags = FL_ONGROUND;
    remove (extra);

    // Two genuinely visible candidates, close enough for no ring glimpse.
    // Health swaps must not reverse the distance-based acquisition choice.
    extra = spawn (); extra.classname = "player"; extra.netname = "healthsecondary";
    extra.health = 100; extra.weapon = IT_SHOTGUN; extra.solid = SOLID_NOT;
    setorigin (extra, ar_pf_visible + (ar_pf_seat - ar_pf_visible) * 0.05);
    traceline (ar_pf_seat + '0 0 22', extra.origin + '0 0 22', TRUE, extra);
    ok = trace_fraction == 1;
    i = 0;
    while (i < 2)
    {
        ar_pf_target.health = 250; extra.health = 1;
        if (i) { ar_pf_target.health = 1; extra.health = 250; }
        ar_pf_target.super_damage_finished = 0; ar_pf_target.invisible_finished = 0;
        setorigin (ar_pf_target, ar_pf_visible);
        self = ar_pf_a; Argus_PerceptionProbe (self, IT_ROCKET_LAUNCHER, 100);
        Argus_ObservationReset (); self.ar_enemy = world; self.ar_lastfoe = world;
        Argus_Perceive ();
        label = "acquire_low_near"; if (i) label = "acquire_low_far";
        Argus_HealthCheck (label, ok && self.ar_enemy == extra && self.ar_obsenemy == extra);
        i = i + 1;
    }
    extra.classname = "healthsecondary";
    // Isolate the actual hunch choice from unrelated live map items. Restore
    // every saved flag before returning; no generated graph or item chain edit.
    it = nextent (world);
    while (it != world)
    {
        if (it.flags & FL_ITEM)
        { it.ar_hi_saved_flags = it.flags; it.flags = it.flags - FL_ITEM; }
        it = nextent (it);
    }
    first = spawn (); second = spawn ();
    first.flags = FL_ITEM; first.solid = SOLID_TRIGGER;
    second.flags = FL_ITEM; second.solid = SOLID_TRIGGER;
    setorigin (first, ar_pf_visible + '16 0 0'); setsize (first, '-8 -8 -8', '8 8 8');
    setorigin (second, ar_pf_visible + '64 0 0'); setsize (second, '-8 -8 -8', '8 8 8');
    self = ar_pf_a; self.ar_enemy = ar_pf_target; self.ar_obsenemy = ar_pf_target;
    self.ar_lastseen = ar_pf_visible; self.ar_threatclass = AR_THREAT_DIRECT;
    setorigin (ar_pf_target, ar_pf_hide); calls = ar_pf_rngcalls;
    i = 0; isolation = 1;
    while (i < 5)
    {
        first.classname = "item_health"; first.healamount = 25; first.touch = SUB_Null;
        second.classname = "weapon_rocketlauncher";
        Argus_HealthTarget (1); ar_pf_target.health = 100; ar_pf_target.max_health = 100;
        if (i == 0) ar_pf_target.health = 1;
        if (i == 1) ar_pf_target.items = IT_SHOTGUN;
        if (i == 2) ar_pf_target.ammo_rockets = 0;
        if (i == 3) { first.classname = "item_armorInv"; ar_pf_target.armorvalue = 0; ar_pf_target.armortype = 0; }
        if (i == 4) { first.classname = "backpack"; first.touch = BackpackTouch; first.items = 0; first.ammo_rockets = 0; first.ammo_cells = 0; }
        // Snapshot every private input before changing just this case's
        // intended field group. The spare disposable entity is not a player.
        extra.health = ar_pf_target.health; extra.max_health = ar_pf_target.max_health;
        extra.items = ar_pf_target.items; extra.weapon = ar_pf_target.weapon;
        extra.armorvalue = ar_pf_target.armorvalue; extra.armortype = ar_pf_target.armortype;
        extra.ammo_shells = ar_pf_target.ammo_shells; extra.ammo_nails = ar_pf_target.ammo_nails;
        extra.ammo_rockets = ar_pf_target.ammo_rockets; extra.ammo_cells = ar_pf_target.ammo_cells;
        extra.currentammo = ar_pf_target.currentammo;
        packitems = first.items; packrock = first.ammo_rockets; packcells = first.ammo_cells;
        self.ar_hunchcool = time - 1; self.ar_huntitem = world; self.ar_goal = world;
        Argus_Hunch (ar_pf_target); chosen = self.ar_huntitem;
        Argus_HealthTarget (1);
        ar_pf_target.max_health = 100;
        if (i != 0) ar_pf_target.health = 100;
        if (i == 4) { first.items = IT_ROCKET_LAUNCHER; first.ammo_rockets = 100; first.ammo_cells = 100; }
        if ((i != 0 && ar_pf_target.health != extra.health)
            || ar_pf_target.max_health != extra.max_health
            || (i != 1 && ar_pf_target.items != extra.items)
            || ar_pf_target.weapon != extra.weapon
            || (i != 2 && ar_pf_target.ammo_rockets != extra.ammo_rockets)
            || ar_pf_target.ammo_shells != extra.ammo_shells
            || ar_pf_target.ammo_nails != extra.ammo_nails
            || ar_pf_target.ammo_cells != extra.ammo_cells
            || ar_pf_target.currentammo != extra.currentammo
            || (i != 3 && (ar_pf_target.armorvalue != extra.armorvalue || ar_pf_target.armortype != extra.armortype))) isolation = 0;
        if ((i == 0 && ar_pf_target.health == extra.health)
            || (i == 1 && ar_pf_target.items == extra.items)
            || (i == 2 && ar_pf_target.ammo_rockets == extra.ammo_rockets)
            || (i == 3 && ar_pf_target.armorvalue == extra.armorvalue)
            || (i == 4 && (first.items == packitems || first.ammo_rockets == packrock || first.ammo_cells == packcells))) isolation = 0;
        self.ar_hunchcool = time - 1; self.ar_huntitem = world; self.ar_goal = world;
        Argus_Hunch (ar_pf_target);
        label = "hunch_health";
        if (i == 1) label = "hunch_weapons";
        if (i == 2) label = "hunch_ammo";
        if (i == 3) label = "hunch_armor";
        if (i == 4) label = "hunch_pack";
        Argus_HealthCheck (label, chosen != world && self.ar_huntitem == chosen);
        i = i + 1;
    }
    Argus_HealthCheck ("hunch_inputs_isolated", isolation);
    first.classname = "item_rockets"; first.touch = SUB_Null;
    second.classname = "item_cells";
    setorigin (first, ar_pf_visible + '16 0 0'); setorigin (second, ar_pf_visible - '16 0 0');
    ar_pf_target.invisible_finished = 0; ar_pf_target.super_damage_finished = 0;
    ar_pf_target.weapon = IT_ROCKET_LAUNCHER; setorigin (ar_pf_target, ar_pf_visible);
    self.ar_enemy = ar_pf_target; Argus_Perceive ();
    setorigin (ar_pf_target, ar_pf_hide);
    self.ar_hunchcool = time - 1; self.ar_huntitem = world; Argus_Hunch (ar_pf_target);
    chosen = self.ar_huntitem;
    ar_pf_target.weapon = IT_LIGHTNING;
    self.ar_hunchcool = time - 1; self.ar_huntitem = world; Argus_Hunch (ar_pf_target);
    Argus_HealthCheck ("hidden_weapon_family", chosen == first && self.ar_huntitem == first);
    setorigin (ar_pf_target, ar_pf_visible); Argus_Perceive ();
    setorigin (ar_pf_target, ar_pf_hide);
    self.ar_hunchcool = time - 1; self.ar_huntitem = world; Argus_Hunch (ar_pf_target);
    Argus_HealthCheck ("visible_weapon_family", self.ar_threatclass == AR_THREAT_BEAM && self.ar_huntitem == second);
    owned = self.ar_hunchcool; hp = self.ar_hunttime;
    self.ar_threatclass = AR_THREAT_SPLASH; Argus_Hunch (ar_pf_target);
    Argus_HealthCheck ("hunch_cooldown", self.ar_huntitem == second && self.ar_hunchcool == owned && self.ar_hunttime == hp);
    Argus_HealthCheck ("identity_and_rng", self == ar_pf_a && argus_bots == roster && ar_pf_rngcalls == calls);
    remove (first); remove (second); remove (extra);
    clean = 1; it = nextent (world);
    while (it != world)
    {
        if (it.ar_hi_saved_flags)
        { it.flags = it.ar_hi_saved_flags; it.ar_hi_saved_flags = 0; if (!(it.flags & FL_ITEM)) clean = 0; }
        it = nextent (it);
    }
    // Restore the actual earlier sample, including its original timestamp,
    // so the enclosing PERFIX still tests its genuine sight-loss interval.
    ar_pf_target.health = 100; ar_pf_target.max_health = 0;
    ar_pf_target.items = 0; ar_pf_target.armorvalue = 0; ar_pf_target.armortype = 0;
    ar_pf_target.ammo_shells = 0; ar_pf_target.ammo_nails = 0;
    ar_pf_target.ammo_rockets = 0; ar_pf_target.ammo_cells = 0; ar_pf_target.currentammo = 0;
    ar_pf_target.weapon = IT_SHOTGUN; ar_pf_target.velocity = '100 30 40'; ar_pf_target.flags = FL_ONGROUND;
    ar_pf_target.invisible_finished = 0; ar_pf_target.super_damage_finished = 0; ar_pf_target.invincible_finished = 0;
    if (ar_pf_ring) ar_pf_target.invisible_finished = ar_pf_begin + 20;
    setorigin (ar_pf_target, ar_pf_visible);
    i = 0;
    while (i < 2)
    {
        self = ar_pf_a; if (i) self = ar_pf_b;
        Argus_PerceptionProbe (self, IT_ROCKET_LAUNCHER, 100);
        self.ar_enemy = ar_pf_target; self.ar_obsenemy = ar_pf_target;
        self.ar_seen = seen; self.ar_lastseen = last; self.ar_obsvelocity = vel;
        self.ar_obspower = power; self.ar_threatclass = family;
        self.ar_obsground = ground; self.ar_obsair = air;
        self.ar_lastfoe = world; self.ar_foetime = 0;
        self.ar_huntitem = world; self.ar_hunttime = 0; self.ar_hunchcool = 0; self.ar_goal = world;
        self.ar_retreatlock = 0;
        i = i + 1;
    }
    self = saved;
    dprint ("HIFIX end "); dprint (ftos (ar_pf_id)); dprint (" checks "); dprint (ftos (ar_hi_checks));
    dprint (" ok "); dprint (ftos (ar_hi_ok)); dprint ("\n");
    dprint ("HIFIX cleanup "); dprint (ftos (ar_pf_id)); dprint (" restored "); dprint (ftos (clean)); dprint ("\n");
    dprint ("HIFIX done "); dprint (ftos (ar_pf_id)); dprint ("\n");
};
