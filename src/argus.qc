/*  argus.qc â€” v3: combat. Movement and navigation from v1/v2, plus:

    * bots are classname "player": items, obituaries, frags and doors all
      treat them as players through the stock 1.06 machinery, untouched
    * firing drives the real weapon code (W_Attack), so ammo, refire
      timing and projectiles are the game's own
    * a human aim model: reaction delay on new targets, rate-limited
      tracking, distance-scaled error that shrinks while tracking
    * strafing: movement direction is decoupled from facing, so bots
      circle-strafe while shooting
    * death and respawn through th_die, frags via stock ClientObituary
    * lava and slime damage (the client-prethink hazard code never runs
      for non-clients, so bots supply their own)
    * scoreboard illusion: svc_updatename / colors / frags written into
      spare client slots so connected humans see bots on TAB

    Telemetry:
      ARGLOG <name> t <t> pos <'x y z'> spd <u/s> yaw <deg> mode <m>
             st <stalls> gl <goals> hp <health> frg <frags>
      ARGEVT <name> spawned|respawn|goal <class>|route <n>|routefail|
             trapped|train|
             abandon|stall|jump|rjump|lift|swim|hazard|engage <name>|
             pursue|retreat|grab <class>|board|
             weapon <axe|sg|ssg|ng|sng|gl|rl|lg>|
             plan <class> via <class>|
             death <killer> pos <'x y z'>
      (hazard = the brink guard deflected a walk into lava/slime/void,
       weapon = Argus_SelectWeapon changed the held weapon,
       plan = the goal planner inserted a prerequisite step: the first
       class is the end state, the second the pickup happening first)
*/

float AR_MAXSPEED    = 320;
float AR_STOPSPEED   = 100;
float AR_FRICTION    = 4;
float AR_ACCEL       = 10;
float AR_AIRWISH     = 30;
float AR_JUMPVEL     = 270;
float AR_TURNRATE    = 320;     // deg/s body turn
float AR_AIMRATE     = 260;     // deg/s aim tracking
float AR_AIMERR      = 34;      // aim error in units at 500u, fresh target

// goal planner: item classes the utility scorer ranks, and the
// world-state atoms the GOAP layer plans over
float AR_C_ANY     = 0;         // backpacks and oddments
float AR_C_WEAPON  = 1;
float AR_C_AMMO    = 2;
float AR_C_HEALTH  = 3;
float AR_C_ARMOR   = 4;
float AR_C_POWER   = 5;

float AR_WS_ARMED   = 1;        // a real gun with ammo in it
float AR_WS_STOCKED = 2;        // comfortable ammo for that gun
float AR_WS_HEALTHY = 4;        // health >= 75
float AR_WS_ARMORED = 8;        // >= 25 protection points

float SVC_UPDATENAME   = 13;
float SVC_UPDATEFRAGS  = 14;
float SVC_UPDATECOLORS = 17;

// player.qc, client.qc and triggers.qc compile after argus.qc;
// prototypes so bots can use the stock death sequence, locomotion
// animation, spawn fog/telefrag, and level changing
void() PlayerDie;
void() player_run;
void(vector org) spawn_tfog;
void(vector org, entity death_owner) spawn_tdeath;
void() NextLevel;

float argus_spawncount;
entity argus_bots;              // chain of all bots
entity argus_lastspot;          // spawn point rotation
float argus_maxclients;         // reserved client slots, counted at worldspawn
float argus_nextnames;          // next periodic scoreboard rebroadcast

.entity ar_chain;
.float  ar_clientno;            // fake scoreboard slot
.float  ar_lastfrags;

.entity ar_goal;
.float  ar_goalstart;
.float  ar_stallrun;
.float  ar_mode;                // 0 wander, 1 direct, 2 routed
.float  ar_nextai;
.float  ar_nextlog;
.float  ar_nextstall;
.vector ar_lastpos;
.float  ar_stalls;
.float  ar_goals;
.float  ar_jump;
.float  ar_wanderturn;
.float  ar_swim;
.float  ar_nextjump;
.float  ar_nexthazlog;          // throttle for hazard telemetry events
.float  ar_hazardyaw;           // last safe deflection heading
.float  ar_hazhold;             // 1 = ar_hazardyaw is live (0 is a legal yaw)
.float  ar_moveyaw;             // movement heading (may differ from facing)

.entity ar_claimer;             // on items
.float  ar_claimtime;           // on items
.float  ar_failtime;            // on items: last routefail at this goal.
                                // Global, unlike the claim: a routefail
                                // is a topology verdict and holds for
                                // every bot, and the single-owner claim
                                // slot thrashed once utility scoring
                                // made the quad everyone's favourite

// ar_laststart / ar_lastfailnode / ar_failstreak are declared in
// argus_nav.qc (compile order): a repeat routefail from one start node
// is a verdict about the BOT (knocked into a pit), not the goal â€”
// without the streak check, one trapped bot routefails through the
// whole goal menu and the global shelf starves every other bot for
// minutes (the bimodal lava matches, 2026-08-18)

.float  ar_nextchat;            // chat throttle
.float  ar_greeted;             // said hello yet
.float  ar_h2otime;             // water enter/exit sound throttle (the
                                // swim bob skims the surface; see
                                // Argus_WaterMove)
.float  ar_feettype;            // liquid contents at the FEET (QC's
                                // own bookkeeping; self.watertype
                                // belongs to the engine, see
                                // Argus_Waterlevel)

.vector ar_sndpos;              // OPM: last heard sound position
.float  ar_sndtime;             // OPM: when it was heard
.entity ar_sndent;              // OPM: who made it
.entity ar_nemesis;             // OPM: who keeps killing this bot
.float  ar_nemkills;            // OPM: consecutive deaths to them;
                                // 3+ is a vendetta, any kill vents it
.entity ar_lastfoe;             // combat memory: last engaged enemy
.float  ar_foetime;             // when we last had them in a fight
.entity ar_door;                // door slice: closed slab being handled
.entity ar_doorbtn;             // door slice: its touch button
.float  ar_doortime;            // door slice: give-up deadline
float ar_opm_ears;              // OPM slice B ladder switch: hearing
                                // consumers (FOV gate + glance) are
                                // inert until slice B's own A/B;
                                // remove after slice B ships

.float  ar_aimerr;              // skill: aim error multiplier
.float  ar_reactbase;           // skill: base reaction delay
.float  ar_aimrate;             // skill: aim tracking deg/s (kept for
                                // pursuit turns; combat yaw uses the
                                // spring below since v3.27)
.float  ar_spring_k;            // OPM: aim spring stiffness
.float  ar_damping_c;           // OPM: aim spring damping (precomputed
                                // per tier; vanilla QC has no sqrt)
.float  ar_aimvel;              // OPM: yaw angular velocity, deg/s

.entity ar_enemy;
.float  ar_seen;                // last time enemy was visible
.vector ar_lastseen;            // where the enemy was last visible
.float  ar_pursuing;            // chasing the vanish point right now
.float  ar_react;               // may not fire before this
.float  ar_track;               // when tracking of this target began
.float  ar_strafedir;
.float  ar_strafetime;
.float  ar_dodgecheck;          // missile dodge: next scan time
.float  ar_dodgeyaw;            // missile dodge: committed sidestep
.float  ar_dodgetime;           // missile dodge: sidestep active until
.float  ar_sndweap;             // hearing: weapon bits of the last shot heard
.float  ar_retreating;          // retreat: low-stack disengage active
.float  ar_coveryaw;            // retreat: committed cover heading
.float  ar_covertime;           // retreat: re-evaluate cover after this
.entity ar_bitem;               // battle item: mid-fight grab target
.float  ar_bitemscan;           // battle item: next scan time
.float  ar_bitemend;            // battle item: commit expires
.entity ar_bitemlast;           // battle item: last failed grab
.float  ar_bitemcool;           // battle item: failed grab cools until
.float  ar_gapjump;             // predictive gap jump: next attempt
.float  ar_respawntime;

.float  ar_wweap;               // utility appetites: how loudly each
.float  ar_wheal;               // item class calls to this personality
.float  ar_warmor;              // (multipliers on the goal scorer, set
.float  ar_wpow;                // with the personality in SetSkill)
.float  ar_planfinal;           // GOAP: class code the plan ends at
.float  ar_planwant;            // GOAP: class code the current goal serves

// ---------------------------------------------------------------- telemetry

void() Argus_Telemetry =
{
    local vector vh;

    vh = self.velocity;
    vh_z = 0;
    dprint ("ARGLOG ");
    dprint (self.netname);
    dprint (" t ");
    dprint (ftos(time));
    dprint (" pos ");
    dprint (vtos(self.origin));
    dprint (" spd ");
    dprint (ftos(vlen(vh)));
    dprint (" yaw ");
    dprint (ftos(self.angles_y));
    dprint (" mode ");
    dprint (ftos(self.ar_mode));
    dprint (" st ");
    dprint (ftos(self.ar_stalls));
    dprint (" gl ");
    dprint (ftos(self.ar_goals));
    dprint (" hp ");
    dprint (ftos(self.health));
    dprint (" frg ");
    dprint (ftos(self.frags));
    dprint ("\n");
};

void(string ev) Argus_Event =
{
    dprint ("ARGEVT ");
    dprint (self.netname);
    dprint (" ");
    dprint (ev);
    dprint ("\n");
};

// ---------------------------------------------------------------- chat

// The homage bot soul speaks. what: 0 greeting, 1 kill, 2 death, 3 revenge, 4 powerup.
// Lines are bprint broadcasts built sequentially, throttled per bot, and
// skipped often enough to stay charming.
void(float what) Argus_Chat =
{
    local float r;

    if (what == 1 && random () < 0.25)
        return;
    if (what == 2 && random () < 0.5)
        return;
    if (time < self.ar_nextchat)
        return;
    self.ar_nextchat = time + 5 + random () * 4;

    r = random ();
    if (self.netname == "Carmack")
    {
        if (what == 0)
        {
            if (r < 0.5) bprint (PRINT_CHAT, "\x01Carmack: In the information age, the barriers just aren't there.\n");
            else         bprint (PRINT_CHAT, "\x01Carmack: Compiling level geometry. Latency target: 0 ms.\n");
        }
        else if (what == 1)
        {
            if (r < 0.25)      bprint (PRINT_CHAT, "\x01Carmack: Fast inverse square root: calculated directly.\n");
            else if (r < 0.50) bprint (PRINT_CHAT, "\x01Carmack: Rocket splash radius is O(1).\n");
            else if (r < 0.75) bprint (PRINT_CHAT, "\x01Carmack: Cache line flushed. Next.\n");
            else               bprint (PRINT_CHAT, "\x01Carmack: Your frame budget has expired.\n");
        }
        else if (what == 3)
        {
            if (r < 0.5) bprint (PRINT_CHAT, "\x01Carmack: Garbage collection complete.\n");
            else         bprint (PRINT_CHAT, "\x01Carmack: Refreshed at 144 Hz.\n");
        }
        else if (what == 4)
        {
            bprint (PRINT_CHAT, "\x01Carmack: 4x damage multiplier unlocked.\n");
        }
        else
        {
            if (r < 0.5) bprint (PRINT_CHAT, "\x01Carmack: Frame budget exceeded. Refactoring.\n");
            else         bprint (PRINT_CHAT, "\x01Carmack: Profiling execution path. Sub-optimal.\n");
        }
    }
    else if (self.netname == "Romero")
    {
        if (what == 0)
        {
            if (r < 0.5) bprint (PRINT_CHAT, "\x01Romero: To win the game you must kill me, John Romero!\n");
            else         bprint (PRINT_CHAT, "\x01Romero: Time for some pure deathmatch!\n");
        }
        else if (what == 1)
        {
            if (r < 0.25)      bprint (PRINT_CHAT, "\x01Romero: You're about to become my bitch!\n");
            else if (r < 0.50) bprint (PRINT_CHAT, "\x01Romero: Suck it down!\n");
            else if (r < 0.75) bprint (PRINT_CHAT, "\x01Romero: Pure unadulterated gibs!\n");
            else               bprint (PRINT_CHAT, "\x01Romero: The rocket launcher is a musical instrument!\n");
        }
        else if (what == 3)
        {
            if (r < 0.5) bprint (PRINT_CHAT, "\x01Romero: Head on a stick!\n");
            else         bprint (PRINT_CHAT, "\x01Romero: I am the master of deathmatch!\n");
        }
        else if (what == 4)
        {
            bprint (PRINT_CHAT, "\x01Romero: QUAD DAMAGE! Let the slaughter begin!\n");
        }
        else
        {
            if (r < 0.5) bprint (PRINT_CHAT, "\x01Romero: You got lucky! Nobody frags Romero twice!\n");
            else         bprint (PRINT_CHAT, "\x01Romero: That was a cheap shot!\n");
        }
    }
    else if (self.netname == "Mr Elusive")
    {
        if (what == 0)
        {
            if (r < 0.5) bprint (PRINT_CHAT, "\x01Mr Elusive: AAS navigation mesh loaded. Area awareness active.\n");
            else         bprint (PRINT_CHAT, "\x01Mr Elusive: Omicron lineage online.\n");
        }
        else if (what == 1)
        {
            if (r < 0.25)      bprint (PRINT_CHAT, "\x01Mr Elusive: Fuzzy logic evaluation: Target eliminated.\n");
            else if (r < 0.50) bprint (PRINT_CHAT, "\x01Mr Elusive: Your path traversal had a 0% survival probability.\n");
            else if (r < 0.75) bprint (PRINT_CHAT, "\x01Mr Elusive: Omicron lineage strikes again.\n");
            else               bprint (PRINT_CHAT, "\x01Mr Elusive: AAS reachability calculated: You had no exit.\n");
        }
        else if (what == 3)
        {
            if (r < 0.5) bprint (PRINT_CHAT, "\x01Mr Elusive: Target state transition: Extinct.\n");
            else         bprint (PRINT_CHAT, "\x01Mr Elusive: Optimal trajectory confirmed.\n");
        }
        else if (what == 4)
        {
            bprint (PRINT_CHAT, "\x01Mr Elusive: High-priority item secured: Combat multiplier active.\n");
        }
        else
        {
            if (r < 0.5) bprint (PRINT_CHAT, "\x01Mr Elusive: Recalculating node reachability weights.\n");
            else         bprint (PRINT_CHAT, "\x01Mr Elusive: Edge cost penalty applied.\n");
        }
    }
    else if (self.netname == "Joe Rogan")
    {
        if (what == 0)
        {
            if (r < 0.5) bprint (PRINT_CHAT, "\x01Joe Rogan: I had a T1 line installed in my house in 1999 just to play Quake.\n");
            else         bprint (PRINT_CHAT, "\x01Joe Rogan: Look at the size of this arena... absolute savagery.\n");
        }
        else if (what == 1)
        {
            if (r < 0.25)      bprint (PRINT_CHAT, "\x01Joe Rogan: We are giving birth to the electron butterfly!\n");
            else if (r < 0.50) bprint (PRINT_CHAT, "\x01Joe Rogan: Have you ever done DMT while rocket jumping?\n");
            else if (r < 0.75) bprint (PRINT_CHAT, "\x01Joe Rogan: Jamie, pull that frag up!\n");
            else               bprint (PRINT_CHAT, "\x01Joe Rogan: That was pure ape violence!\n");
        }
        else if (what == 3)
        {
            if (r < 0.5) bprint (PRINT_CHAT, "\x01Joe Rogan: Straight carnivore diet energy, man!\n");
            else         bprint (PRINT_CHAT, "\x01Joe Rogan: Chimps with rocket launchers!\n");
        }
        else if (what == 4)
        {
            bprint (PRINT_CHAT, "\x01Joe Rogan: QUAD! Look at that blue glow... that's wild!\n");
        }
        else
        {
            if (r < 0.5) bprint (PRINT_CHAT, "\x01Joe Rogan: That guy is a savage. An absolute monster.\n");
            else         bprint (PRINT_CHAT, "\x01Joe Rogan: I felt that direct rocket in my nervous system.\n");
        }
    }
    else if (self.netname == "Thresh")
    {
        if (what == 0)
        {
            if (r < 0.5) bprint (PRINT_CHAT, "\x01Thresh: Controlling red armor. 30 seconds to Quad.\n");
            else         bprint (PRINT_CHAT, "\x01Thresh: Welcome to the arena.\n");
        }
        else if (what == 1)
        {
            if (r < 0.25)      bprint (PRINT_CHAT, "\x01Thresh: Timing is everything.\n");
            else if (r < 0.50) bprint (PRINT_CHAT, "\x01Thresh: You overcommitted on that lower ledge.\n");
            else if (r < 0.75) bprint (PRINT_CHAT, "\x01Thresh: Keys to the Ferrari 328 secured.\n");
            else               bprint (PRINT_CHAT, "\x01Thresh: Map control wins games.\n");
        }
        else if (what == 3)
        {
            if (r < 0.5) bprint (PRINT_CHAT, "\x01Thresh: Calculated and executed.\n");
            else         bprint (PRINT_CHAT, "\x01Thresh: Check the clock.\n");
        }
        else if (what == 4)
        {
            bprint (PRINT_CHAT, "\x01Thresh: Quad secured right on spawn time.\n");
        }
        else
        {
            if (r < 0.5) bprint (PRINT_CHAT, "\x01Thresh: Good shot. Resetting my stack.\n");
            else         bprint (PRINT_CHAT, "\x01Thresh: Armor timing was off by 2 seconds.\n");
        }
    }
    else if (self.netname == "Crash")
    {
        if (what == 0)
            bprint (PRINT_CHAT, "\x01Crash: Listen up recruits! Time for live combat drill!\n");
        else if (what == 1)
        {
            if (r < 0.33)      bprint (PRINT_CHAT, "\x01Crash: Back to the respawn queue, rookie!\n");
            else if (r < 0.66) bprint (PRINT_CHAT, "\x01Crash: Keep your crosshair up!\n");
            else               bprint (PRINT_CHAT, "\x01Crash: Standard issue elimination!\n");
        }
        else if (what == 3)
            bprint (PRINT_CHAT, "\x01Crash: That is how it is done, soldier!\n");
        else if (what == 4)
            bprint (PRINT_CHAT, "\x01Crash: Heavy weapons authorization confirmed!\n");
        else
            bprint (PRINT_CHAT, "\x01Crash: Keep drilling! Again!\n");
    }
    else if (self.netname == "Trent Reznor")
    {
        if (what == 0)
        {
            if (r < 0.5) bprint (PRINT_CHAT, "\x01Trent Reznor: Head like a hole, black as your soul. Welcome to the machine.\n");
            else         bprint (PRINT_CHAT, "\x01Trent Reznor: The downward spiral begins.\n");
        }
        else if (what == 1)
        {
            if (r < 0.25)      bprint (PRINT_CHAT, "\x01Trent Reznor: I want to feel you from the inside out.\n");
            else if (r < 0.50) bprint (PRINT_CHAT, "\x01Trent Reznor: Terrible lie... you thought you could dodge.\n");
            else if (r < 0.75) bprint (PRINT_CHAT, "\x01Trent Reznor: March of the pigs!\n");
            else               bprint (PRINT_CHAT, "\x01Trent Reznor: Nine Inch Nails straight through the chest.\n");
        }
        else if (what == 3)
        {
            if (r < 0.5) bprint (PRINT_CHAT, "\x01Trent Reznor: Closer to God.\n");
            else         bprint (PRINT_CHAT, "\x01Trent Reznor: Down in it.\n");
        }
        else if (what == 4)
            bprint (PRINT_CHAT, "\x01Trent Reznor: Nothing can stop me now! QUAD ACTIVE!\n");
        else
        {
            if (r < 0.5) bprint (PRINT_CHAT, "\x01Trent Reznor: I hurt myself today... to see if I still feel.\n");
            else         bprint (PRINT_CHAT, "\x01Trent Reznor: Somewhat damaged.\n");
        }
    }
    else if (self.netname == "American McGee")
    {
        if (what == 0)
        {
            if (r < 0.5) bprint (PRINT_CHAT, "\x01American McGee: Welcome to my labyrinth. Mind the drop.\n");
            else         bprint (PRINT_CHAT, "\x01American McGee: Curiouser and curiouser...\n");
        }
        else if (what == 1)
        {
            if (r < 0.25)      bprint (PRINT_CHAT, "\x01American McGee: Designed this room specifically for your execution.\n");
            else if (r < 0.50) bprint (PRINT_CHAT, "\x01American McGee: Off with your head!\n");
            else if (r < 0.75) bprint (PRINT_CHAT, "\x01American McGee: You fell right into my brushwork.\n");
            else               bprint (PRINT_CHAT, "\x01American McGee: A masterpiece in spatial disorientation.\n");
        }
        else if (what == 3)
            bprint (PRINT_CHAT, "\x01American McGee: The architect always wins in the end.\n");
        else if (what == 4)
            bprint (PRINT_CHAT, "\x01American McGee: Mad as a hatter! QUAD ACTIVE!\n");
        else
        {
            if (r < 0.5) bprint (PRINT_CHAT, "\x01American McGee: A flaw in the level layout... impossible.\n");
            else         bprint (PRINT_CHAT, "\x01American McGee: Back down the rabbit hole.\n");
        }
    }
    else if (self.netname == "Sarge")
    {
        if (what == 0)
        {
            if (r < 0.5) bprint (PRINT_CHAT, "\x01Sarge: Lock and load, maggots! Sarge is in the house.\n");
            else         bprint (PRINT_CHAT, "\x01Sarge: I love the smell of burning rockets in the morning.\n");
        }
        else if (what == 1)
        {
            if (r < 0.25)      bprint (PRINT_CHAT, "\x01Sarge: Target neutralized. Next maggot!\n");
            else if (r < 0.50) bprint (PRINT_CHAT, "\x01Sarge: Eat buckshot, boy!\n");
            else if (r < 0.75) bprint (PRINT_CHAT, "\x01Sarge: You call that dodging? My grandmother moves faster!\n");
            else               bprint (PRINT_CHAT, "\x01Sarge: Ashes to ashes, dust to gibs!\n");
        }
        else if (what == 3)
            bprint (PRINT_CHAT, "\x01Sarge: Payback is a bitch and so are you!\n");
        else if (what == 4)
            bprint (PRINT_CHAT, "\x01Sarge: QUAD DAMAGE! Time to clean house!\n");
        else
        {
            if (r < 0.5) bprint (PRINT_CHAT, "\x01Sarge: Pain is just weakness leaving the body!\n");
            else         bprint (PRINT_CHAT, "\x01Sarge: Gonna need a fresh cigar for this one.\n");
        }
    }
    else if (self.netname == "Sandy Petersen")
    {
        if (what == 0)
        {
            if (r < 0.5) bprint (PRINT_CHAT, "\x01Sandy Petersen: Ph'nglui mglw'nafh Cthulhu R'lyeh wgah'nagl fhtagn.\n");
            else         bprint (PRINT_CHAT, "\x01Sandy Petersen: The Elder Gods demand tribute.\n");
        }
        else if (what == 1)
        {
            if (r < 0.33)      bprint (PRINT_CHAT, "\x01Sandy Petersen: Sacrificed to Shub-Niggurath!\n");
            else if (r < 0.66) bprint (PRINT_CHAT, "\x01Sandy Petersen: Your mind shattered before the rocket hit.\n");
            else               bprint (PRINT_CHAT, "\x01Sandy Petersen: Consumed by ancient horrors!\n");
        }
        else if (what == 3)
            bprint (PRINT_CHAT, "\x01Sandy Petersen: The Old Ones awaken!\n");
        else if (what == 4)
            bprint (PRINT_CHAT, "\x01Sandy Petersen: Eldritch power courses through my veins!\n");
        else
            bprint (PRINT_CHAT, "\x01Sandy Petersen: That is not dead which can eternal lie...\n");
    }
    else if (self.netname == "Killcreek")
    {
        if (what == 0)
            bprint (PRINT_CHAT, "\x01Killcreek: Ready to show the boys how Quake is played.\n");
        else if (what == 1)
        {
            if (r < 0.33)      bprint (PRINT_CHAT, "\x01Killcreek: Fried by the shaft!\n");
            else if (r < 0.66) bprint (PRINT_CHAT, "\x01Killcreek: You just got schooled.\n");
            else               bprint (PRINT_CHAT, "\x01Killcreek: Another trophy on the shelf.\n");
        }
        else if (what == 3)
            bprint (PRINT_CHAT, "\x01Killcreek: Nobody beats Killcreek in the rematch!\n");
        else if (what == 4)
            bprint (PRINT_CHAT, "\x01Killcreek: Shaft + Quad = Total meltdown!\n");
        else
            bprint (PRINT_CHAT, "\x01Killcreek: Nice shot. Let's see you do it twice.\n");
    }
    else if (self.netname == "Gabe Newell")
    {
        if (what == 0)
            bprint (PRINT_CHAT, "\x01Gabe Newell: Welcome to the Steam tournament. Worth the weight.\n");
        else if (what == 1)
        {
            if (r < 0.25)      bprint (PRINT_CHAT, "\x01Gabe Newell: Your life has been discounted by 75%!\n");
            else if (r < 0.50) bprint (PRINT_CHAT, "\x01Gabe Newell: These things, they take time.\n");
            else if (r < 0.75) bprint (PRINT_CHAT, "\x01Gabe Newell: Early Access terminated!\n");
            else               bprint (PRINT_CHAT, "\x01Gabe Newell: No third chance for you.\n");
        }
        else if (what == 3)
            bprint (PRINT_CHAT, "\x01Gabe Newell: The Summer Sale is now live!\n");
        else if (what == 4)
            bprint (PRINT_CHAT, "\x01Gabe Newell: Praise Lord Gaben! QUAD POWER!\n");
        else
        {
            if (r < 0.5) bprint (PRINT_CHAT, "\x01Gabe Newell: Postponing my respawn to Q3.\n");
            else         bprint (PRINT_CHAT, "\x01Gabe Newell: Unforeseen consequences.\n");
        }
    }
    else if (self.netname == "Ranger")
    {
        if (what == 0)
            bprint (PRINT_CHAT, "\x01Ranger: Through the Slipgate once more.\n");
        else if (what == 1)
        {
            if (r < 0.33)      bprint (PRINT_CHAT, "\x01Ranger: Telefragged across four dimensions!\n");
            else if (r < 0.66) bprint (PRINT_CHAT, "\x01Ranger: For the Earth Slipgate Command!\n");
            else               bprint (PRINT_CHAT, "\x01Ranger: Axe to the face!\n");
        }
        else if (what == 3)
            bprint (PRINT_CHAT, "\x01Ranger: Ranger never misses twice.\n");
        else if (what == 4)
            bprint (PRINT_CHAT, "\x01Ranger: Quad Damage empowered!\n");
        else
            bprint (PRINT_CHAT, "\x01Ranger: Respawning at the nearest gateway.\n");
    }
    else if (self.netname == "Tim Willits")
    {
        if (what == 0)
            bprint (PRINT_CHAT, "\x01Tim Willits: Flow is everything. Keep moving.\n");
        else if (what == 1)
        {
            if (r < 0.33)      bprint (PRINT_CHAT, "\x01Tim Willits: Read you like an open corridor.\n");
            else if (r < 0.66) bprint (PRINT_CHAT, "\x01Tim Willits: Speed, flow, and verticality.\n");
            else               bprint (PRINT_CHAT, "\x01Tim Willits: Check the sightline. Clean hit.\n");
        }
        else if (what == 3)
            bprint (PRINT_CHAT, "\x01Tim Willits: Controlling the high ground.\n");
        else
            bprint (PRINT_CHAT, "\x01Tim Willits: Re-routing flanking vector.\n");
    }
    else if (self.netname == "Reap")
    {
        if (what == 0)
            bprint (PRINT_CHAT, "\x01Reap: reap is here. start running.\n");
        else if (what == 1)
        {
            if (r < 0.33)      bprint (PRINT_CHAT, "\x01Reap: too slow.\n");
            else if (r < 0.66) bprint (PRINT_CHAT, "\x01Reap: stay down.\n");
            else               bprint (PRINT_CHAT, "\x01Reap: next.\n");
        }
        else if (what == 3)
        {
            if (r < 0.5)       bprint (PRINT_CHAT, "\x01Reap: finally.\n");
            else               bprint (PRINT_CHAT, "\x01Reap: streak over.\n");
        }
        else
        {
            if (r < 0.5)       bprint (PRINT_CHAT, "\x01Reap: lucky.\n");
            else               bprint (PRINT_CHAT, "\x01Reap: won't happen twice.\n");
        }
    }
    else if (self.netname == "Omi")
    {
        if (what == 0)
            bprint (PRINT_CHAT, "\x01Omi: omi online. calculating.\n");
        else if (what == 1)
        {
            if (r < 0.33)      bprint (PRINT_CHAT, "\x01Omi: as computed.\n");
            else if (r < 0.66) bprint (PRINT_CHAT, "\x01Omi: clean.\n");
            else               bprint (PRINT_CHAT, "\x01Omi: you were 34 units off optimal.\n");
        }
        else if (what == 3)
        {
            if (r < 0.5)       bprint (PRINT_CHAT, "\x01Omi: anomaly corrected.\n");
            else               bprint (PRINT_CHAT, "\x01Omi: regression to the mean.\n");
        }
        else
        {
            if (r < 0.5)       bprint (PRINT_CHAT, "\x01Omi: recalibrating.\n");
            else               bprint (PRINT_CHAT, "\x01Omi: variance. noted.\n");
        }
    }
    else if (self.netname == "Zeus")
    {
        if (what == 0)
            bprint (PRINT_CHAT, "\x01Zeus: ZEUS BRINGS THE STORM!\n");
        else if (what == 1)
        {
            if (r < 0.33)      bprint (PRINT_CHAT, "\x01Zeus: BOOM!\n");
            else if (r < 0.66) bprint (PRINT_CHAT, "\x01Zeus: feel the thunder!\n");
            else               bprint (PRINT_CHAT, "\x01Zeus: HAHA! again!\n");
        }
        else if (what == 3)
        {
            if (r < 0.5)       bprint (PRINT_CHAT, "\x01Zeus: REVENGE!\n");
            else               bprint (PRINT_CHAT, "\x01Zeus: THE STORM REMEMBERS!\n");
        }
        else
        {
            if (r < 0.5)       bprint (PRINT_CHAT, "\x01Zeus: IMPOSSIBLE!\n");
            else               bprint (PRINT_CHAT, "\x01Zeus: the storm returns!\n");
        }
    }
    else
    {
        if (what == 0)
            bprint (PRINT_CHAT, "\x01Ares: ares joins the war.\n");
        else if (what == 1)
        {
            if (r < 0.5)       bprint (PRINT_CHAT, "\x01Ares: down you go.\n");
            else               bprint (PRINT_CHAT, "\x01Ares: war takes all.\n");
        }
        else if (what == 3)
        {
            if (r < 0.5)       bprint (PRINT_CHAT, "\x01Ares: debt settled.\n");
            else               bprint (PRINT_CHAT, "\x01Ares: vengeance is mine.\n");
        }
        else
        {
            if (r < 0.5)       bprint (PRINT_CHAT, "\x01Ares: a scratch.\n");
            else               bprint (PRINT_CHAT, "\x01Ares: regroup.\n");
        }
    }
};

// ---------------------------------------------------------------- player easter egg chat

void(float topic) Argus_PlayerChat =
{
    local float r;
    r = random ();

    if (topic == 220) // Ask Carmack
    {
        bprint (PRINT_CHAT, "\x01Player: Hey Carmack, what's your take on this engine?\n");
        if (r < 0.5)
            bprint (PRINT_CHAT, "\x01Carmack: The Quake engine architecture remains a pinnacle of spatial partitioning and BSP PVS precomputation.\n");
        else
            bprint (PRINT_CHAT, "\x01Carmack: If you optimize your movement vectors and frame budget, you can hit sub-millisecond response times.\n");
    }
    else if (topic == 221) // Ask Romero
    {
        bprint (PRINT_CHAT, "\x01Player: Hey Romero, show me some deathmatch!\n");
        if (r < 0.5)
            bprint (PRINT_CHAT, "\x01Romero: Deathmatch isn't just a game mode, it's a way of life! Grab that rocket launcher and let's rock!\n");
        else
            bprint (PRINT_CHAT, "\x01Romero: You're in my arena now! Don't let your guard down for a single millisecond!\n");
    }
    else if (topic == 222) // Ask Joe Rogan
    {
        bprint (PRINT_CHAT, "\x01Player: Hey Joe, have you tried DMT while rocket jumping?\n");
        if (r < 0.5)
            bprint (PRINT_CHAT, "\x01Joe Rogan: 100%! It's like your consciousness detaches from the server and you become the electron butterfly. Jamie, pull that up!\n");
        else
            bprint (PRINT_CHAT, "\x01Joe Rogan: Back in '99 on my T1 line, I had a 15 ping and was surviving purely on elk meat and adrenaline!\n");
    }
    else if (topic == 223) // Ask Mr Elusive
    {
        bprint (PRINT_CHAT, "\x01Player: Hey Mr Elusive, what's the optimal route?\n");
        if (r < 0.5)
            bprint (PRINT_CHAT, "\x01Mr Elusive: According to my AAS reachability tables, the shortest path to victory requires continuous area dominance.\n");
        else
            bprint (PRINT_CHAT, "\x01Mr Elusive: Evaluating fuzzy logic matrices... your best move is taking the high ground.\n");
    }
    else if (topic == 224) // Ask Thresh
    {
        bprint (PRINT_CHAT, "\x01Player: Hey Thresh, what's the item timing?\n");
        if (r < 0.5)
            bprint (PRINT_CHAT, "\x01Thresh: MegaHealth is 20s, Red Armor is 20s, Quad is 60s. Control the clock and you control the match.\n");
        else
            bprint (PRINT_CHAT, "\x01Thresh: Watch the respawn pads. Never fight without at least 100/100 stack.\n");
    }
    else if (topic == 226) // Ask Trent Reznor
    {
        bprint (PRINT_CHAT, "\x01Player: Hey Trent, how's the soundtrack sounding?\n");
        if (r < 0.5)
            bprint (PRINT_CHAT, "\x01Trent Reznor: Dark, distorted, and unrelenting. Just the way deathmatch should feel.\n");
        else
            bprint (PRINT_CHAT, "\x01Trent Reznor: Turn up the feedback loops and fire that Super Nailgun.\n");
    }
    else if (topic == 227) // Ask American McGee
    {
        bprint (PRINT_CHAT, "\x01Player: Hey American, how did you design this map?\n");
        if (r < 0.5)
            bprint (PRINT_CHAT, "\x01American McGee: Every corner is an ambush; every ledge is a gamble with gravity.\n");
        else
            bprint (PRINT_CHAT, "\x01American McGee: Gothic arches, lethal drops, and no safe spaces.\n");
    }
    else if (topic == 228) // Ask Sarge
    {
        bprint (PRINT_CHAT, "\x01Player: Sarge, what's our combat strategy?\n");
        if (r < 0.5)
            bprint (PRINT_CHAT, "\x01Sarge: Strategy? Lock and load, aim for the chest, and keep firing until nothing moves!\n");
        else
            bprint (PRINT_CHAT, "\x01Sarge: Move fast, hit hard, and never leave your back uncovered, soldier!\n");
    }
    else if (topic == 229) // Ask Gabe Newell
    {
        bprint (PRINT_CHAT, "\x01Player: Lord Gaben, when is the next release?\n");
        if (r < 0.5)
            bprint (PRINT_CHAT, "\x01Gabe Newell: These things, they take time. But the Summer Sale is always on time.\n");
        else
            bprint (PRINT_CHAT, "\x01Gabe Newell: We're polishing the engine. Worth the weight!\n");
    }
    else if (topic == 230) // Ask Killcreek
    {
        bprint (PRINT_CHAT, "\x01Player: Killcreek, what's the secret to the Lightning Gun?\n");
        if (r < 0.5)
            bprint (PRINT_CHAT, "\x01Killcreek: Lock the beam onto their torso and match their strafe step for step. 100% melt.\n");
        else
            bprint (PRINT_CHAT, "\x01Killcreek: Smooth tracking and zero hesitation. That's how you win duels.\n");
    }
    else if (topic == 225) // General Arena Shout
    {
        bprint (PRINT_CHAT, "\x01Player: Good game everyone!\n");
        if (r < 0.15)      bprint (PRINT_CHAT, "\x01Carmack: Concur. Good execution efficiency.\n");
        else if (r < 0.30) bprint (PRINT_CHAT, "\x01Romero: Pure deathmatch energy! Let's go again!\n");
        else if (r < 0.45) bprint (PRINT_CHAT, "\x01Joe Rogan: Absolute savagery in the arena today, man. Beautiful!\n");
        else if (r < 0.60) bprint (PRINT_CHAT, "\x01Sarge: Outstanding work, maggots!\n");
        else if (r < 0.75) bprint (PRINT_CHAT, "\x01Trent Reznor: The noise never stops.\n");
        else if (r < 0.90) bprint (PRINT_CHAT, "\x01Gabe Newell: Thanks, and have fun!\n");
        else               bprint (PRINT_CHAT, "\x01Thresh: GG. Good map control.\n");
    }
};

// ---------------------------------------------------------------- scoreboard

// Count the reserved client edicts. Called from the worldspawn hook,
// when they are the only allocated edicts after world (ED_Alloc never
// hands them out), so the count equals maxclients on any engine.
void() Argus_CountSlots =
{
    local entity e;

    argus_maxclients = 0;
    e = nextent (world);
    while (e != world && e.classname == "")
    {
        argus_maxclients = argus_maxclients + 1;
        e = nextent (e);
    }
    dprint ("ARGUS slots ");
    dprint (ftos(argus_maxclients));
    dprint ("\n");
};

// how many real clients are connected right now. NQ hands out the
// lowest free slot, so humans occupy 0..n-1: any fake slot below the
// count belongs to a person, and writing to it would clobber their
// TAB row every rebroadcast (Shane's review, fix 4). FL_CLIENT is
// engine-set on real clients only, so the count needs no QW builtins
// and the masquerade cannot fool it.
float() Argus_HumanCount =
{
    local entity p;
    local float n;

    n = 0;
    p = find (world, classname, "player");
    while (p != world)
    {
        if (p.flags & FL_CLIENT)
            n = n + 1;
        p = find (p, classname, "player");
    }
    return n;
};

void() Argus_ScoreName =
{
    if (self.ar_clientno < 0)
        return;                 // no spare slot on this server
    if (self.ar_clientno < Argus_HumanCount ())
        return;                 // a human owns this slot now
    WriteByte (MSG_ALL, SVC_UPDATENAME);
    WriteByte (MSG_ALL, self.ar_clientno);
    WriteString (MSG_ALL, self.netname);
    WriteByte (MSG_ALL, SVC_UPDATECOLORS);
    WriteByte (MSG_ALL, self.ar_clientno);
    WriteByte (MSG_ALL, 4 + self.ar_slot * 17);
};

void() Argus_ScoreFrags =
{
    self.ar_lastfrags = self.frags;
    if (self.ar_clientno < 0)
        return;
    if (self.ar_clientno < Argus_HumanCount ())
        return;                 // a human owns this slot now
    WriteByte (MSG_ALL, SVC_UPDATEFRAGS);
    WriteByte (MSG_ALL, self.ar_clientno);
    WriteShort (MSG_ALL, self.frags);
};

// ---------------------------------------------------------------- physics

void() Argus_Friction =
{
    local vector vh;
    local float spd, control, newspeed;

    vh = self.velocity;
    vh_z = 0;
    spd = vlen (vh);
    if (spd < 1)
    {
        self.velocity_x = 0;
        self.velocity_y = 0;
        return;
    }
    control = spd;
    if (control < AR_STOPSPEED)
        control = AR_STOPSPEED;
    newspeed = spd - frametime * control * AR_FRICTION;
    if (newspeed < 0)
        newspeed = 0;
    newspeed = newspeed / spd;
    self.velocity_x = self.velocity_x * newspeed;
    self.velocity_y = self.velocity_y * newspeed;
};

void(vector wishdir, float wishspeed) Argus_Accelerate =
{
    local float current, addspeed, accelspeed;

    current = self.velocity * wishdir;
    addspeed = wishspeed - current;
    if (addspeed <= 0)
        return;
    accelspeed = AR_ACCEL * frametime * wishspeed;
    if (accelspeed > addspeed)
        accelspeed = addspeed;
    self.velocity = self.velocity + accelspeed * wishdir;
};

void(vector wishdir, float wishspeed) Argus_AirAccelerate =
{
    local float current, addspeed, accelspeed, wishspd;

    wishspd = wishspeed;
    if (wishspd > AR_AIRWISH)
        wishspd = AR_AIRWISH;
    current = self.velocity * wishdir;
    addspeed = wishspd - current;
    if (addspeed <= 0)
        return;
    accelspeed = AR_ACCEL * frametime * wishspeed;
    if (accelspeed > addspeed)
        accelspeed = addspeed;
    self.velocity = self.velocity + accelspeed * wishdir;
};

float() Argus_Waterlevel =
{
    local vector point;
    local float c;

    point = self.origin;
    point_z = self.origin_z + self.mins_z + 1;
    c = pointcontents (point);
    // NEVER write self.watertype here: the engine runs
    // SV_CheckWaterTransition on STEP entities every frame, judging
    // transitions by watertype vs the contents at the ORIGIN â€” a QC
    // write from the FEET made it see a fresh crossing every frame
    // while a bot waded, restarting the splash sound 72 times a
    // second (Shane's fourth sound playtest: "the start of the
    // splash in quick succession"). The engine owns watertype for
    // bots; QC keeps its feet-level verdict in ar_feettype.
    self.ar_feettype = c;
    if (c > CONTENT_WATER)
        return 0;
    point_z = self.origin_z;
    if (pointcontents (point) > CONTENT_WATER)
        return 1;
    point_z = self.origin_z + 22;
    if (pointcontents (point) > CONTENT_WATER)
        return 2;
    return 3;
};

// TRUE when there is solid floor at walking level under 'p': the
// shallow 48u trace means any hit IS at walking level, and the surface
// check rejects a floor carrying a liquid film.
float(vector p) Argus_BridgeSolid =
{
    local float c;

    traceline (p + '0 0 4', p - '0 0 48', TRUE, self);
    if (trace_fraction == 1)
        return FALSE;
    c = pointcontents (trace_endpos + '0 0 2');
    if (c == CONTENT_LAVA || c == CONTENT_SLIME)
        return FALSE;
    return TRUE;
};

// TRUE when the 32x32 hull would still be carried at 'ahead' despite a
// lava/slime floor under the probe POINT. Decorative grate floors (dm2
// south-east room: 16u lava channels recessed 28u between 16u solid
// strips) are narrower than the player bbox, so hull collision bridges
// them and neither walkmove nor a walking player can ever touch the
// liquid - but a point probe lands in a channel half the time and read
// the whole room as a lava field (bots deflected to a dead stop there;
// Shane shot one standing frozen). The test is OPPOSED SUPPORT: banks
// on both sides of the point within a bridgeable span, along either
// axis. A first version accepted any-corner support, which is merely
// "a hull could hang here" - true at every pool RIM, so bots strolled
// to the very lip before the veto fired and dm4 lava deaths spiked
// (ab_dm4_grate: 6 world deaths, several walked in unengaged). A pool
// edge has support on one side only and stays vetoed at the old
// conservative distance.
float(vector ahead) Argus_HazardBridge =
{
    if (Argus_BridgeSolid (ahead + '17 0 0') && Argus_BridgeSolid (ahead - '17 0 0'))
        return TRUE;
    if (Argus_BridgeSolid (ahead + '0 17 0') && Argus_BridgeSolid (ahead - '0 17 0'))
        return TRUE;
    return FALSE;
};

// TRUE when walking pdist units along myaw would end in lava, slime,
// or a bottomless drop. Traces down 280u at the probe point: a
// legitimate one-way drop link (<= 200u onto solid) passes, a lava pit
// does not. Liquids never block tracelines, so trace_endpos is the
// solid floor and pointcontents just above it tells us what covers it.
// Probe short (32) for the per-frame physics guard, long (48) for
// steering choices: a long physics probe fires all along dm4's
// lava-side walkways and stalls bots that were walking safely.
// A liquid floor point is only a verdict on the POINT: the bbox-corner
// bridge test above decides whether the hull would actually stand in
// it. The bottomless branch stays point-based on purpose - a probe
// inside a wall or over a true void must keep vetoing, that deflection
// is what turns walls into slides.
float(float myaw, float pdist) Argus_MoveHazard =
{
    local vector ahead;
    local float c;

    if (self.ar_feettype == CONTENT_LAVA || self.ar_feettype == CONTENT_SLIME)
        return FALSE;               // already in it: any move is an escape

    makevectors ('0 0 0' + myaw * '0 1 0');
    ahead = self.origin + v_forward * pdist;

    traceline (ahead + '0 0 4', ahead - '0 0 280', TRUE, self);
    if (trace_fraction == 1)
    {
        // "no floor" can also mean the probe START is buried in
        // rising geometry: a stair steeper than ~16u per 32u of run
        // swallows the probe point and reads as a void. The dm2
        // rockets pocket's only escape is a 45 degree strip stair
        // (node 85 east, -160 to -112) - bots were deflected back
        // into the pocket by this very guard and jittered at its
        // floor for whole matches. If a knee-plus recheck clears
        // and lands on a tread at climbable height this is a
        // STAIRCASE: walkmove takes the risers one at a time. A
        // wall is still solid at the higher start and keeps its
        // deflection; a true pit finds nothing in the shallow
        // window and stays vetoed.
        if (pointcontents (ahead + '0 0 4') == CONTENT_SOLID)
        {
            traceline (ahead + '0 0 26', ahead - '0 0 8', TRUE, self);
            if (trace_fraction < 1)
            {
                c = pointcontents (trace_endpos + '0 0 2');
                if (c != CONTENT_LAVA && c != CONTENT_SLIME)
                    return FALSE;
            }
        }
        return TRUE;                // no floor within a survivable drop
    }
    c = pointcontents (trace_endpos + '0 0 2');
    if (c == CONTENT_LAVA || c == CONTENT_SLIME)
    {
        if (Argus_HazardBridge (ahead))
            return FALSE;
        return TRUE;
    }
    return FALSE;
};

// Pick a heading that stays off lava/slime/void. Prefers the last
// successful deflection so +50/-50 does not dither at walkway corners
// (dm4 200 -900 24 and 700 -800 -200). Returns a heading; if the
// result is still hazardous the caller is boxed in.
float(float want, float pdist) Argus_HazardSteer =
{
    local float hdiff;

    if (!Argus_MoveHazard (want, pdist))
    {
        self.ar_hazhold = 0;
        return want;
    }
    if (self.ar_hazhold)
    {
        hdiff = self.ar_hazardyaw - want;
        while (hdiff > 180)
            hdiff = hdiff - 360;
        while (hdiff < -180)
            hdiff = hdiff + 360;
        if (hdiff < 0)
            hdiff = 0 - hdiff;
        // revalidate the held heading with a LONGER probe than the
        // caller's: a held yaw steers long arcs along curving lips,
        // and at 32u it saw the pit too late (2026-08-18 forensics:
        // lava 5-11 across the draft's four matches)
        if (hdiff <= 110 && !Argus_MoveHazard (self.ar_hazardyaw, 48))
            return self.ar_hazardyaw;
    }
    if (!Argus_MoveHazard (want + 50, pdist))
        want = want + 50;
    else if (!Argus_MoveHazard (want - 50, pdist))
        want = want - 50;
    else if (!Argus_MoveHazard (want + 100, pdist))
        want = want + 100;
    else if (!Argus_MoveHazard (want - 100, pdist))
        want = want - 100;
    else
    {
        // boxed in: reverse out, but never HOLD the reverse â€” it is
        // an escape, not a steer, and a held reverse marches the bot
        // back the way it came at the next corner
        self.ar_hazhold = 0;
        return want + 180;
    }
    self.ar_hazardyaw = want;
    self.ar_hazhold = 1;
    return want;
};

// TRUE when the straight walk from here to 'to' keeps survivable floor
// underfoot the whole way. The mode-1 eligibility check alone is a
// SIGHT check, and a traceline to a visible item passes clean through
// the air over a lava pit; the utility goal layer made that acute,
// because dm4's prize items all sit by the pit and bots suddenly had
// reasons to beeline at them (stall, swim and lava metrics tripled on
// unrouted approaches). Same floor rules as Argus_MoveHazard, sampled
// every 48u along the line, following the line's slope so a descent
// toward a low goal is judged from the line rather than the start.
float(vector to) Argus_SafeLine =
{
    local vector dir, p;
    local float total, i, c;

    dir = to - self.origin;
    dir_z = 0;
    total = vlen (dir);
    if (total < 48)
        return TRUE;
    dir = normalize (dir);
    i = 48;
    while (i < total)
    {
        p = self.origin + dir * i;
        p_z = self.origin_z + (to_z - self.origin_z) * (i / total) + 24;
        traceline (p, p - '0 0 304', TRUE, self);
        if (trace_fraction == 1)
            return FALSE;
        c = pointcontents (trace_endpos + '0 0 2');
        if (c == CONTENT_LAVA || c == CONTENT_SLIME)
        {
            // same hull-bridge rescue as Argus_MoveHazard: p rides 48
            // above the floor here, the helper expects origin height
            if (!Argus_HazardBridge (p - '0 0 24'))
                return FALSE;
        }
        i = i + 48;
    }
    return TRUE;
};

// Faithful mirror of the client-only WaterMove: drowning with air and
// escalating damage, radsuit rules, stock lava/slime damage rates
// (the old ad-hoc bot version dealt about a third of the human lava
// rate), FL_INWATER upkeep, and the enter/exit/gasp sounds. The stock
// water drag line is deliberately omitted: bot swim physics is its
// own tuned model in Argus_Physics.
void() Argus_WaterMove =
{
    if (self.health < 0)
        return;

    if (self.waterlevel != 3)
    {
        if (self.air_finished < time)
            sound (self, CHAN_VOICE, "player/gasp2.wav", 1, ATTN_NORM);
        else if (self.air_finished < time + 9)
            sound (self, CHAN_VOICE, "player/gasp1.wav", 1, ATTN_NORM);
        self.air_finished = time + 12;
        self.dmg = 2;
    }
    else if (self.air_finished < time)
    {   // drown
        if (self.pain_finished < time)
        {
            self.dmg = self.dmg + 2;
            if (self.dmg > 15)
                self.dmg = 10;
            self.deathtype = "drowning";
            T_Damage (self, world, world, self.dmg);
            self.pain_finished = time + 1;
        }
    }

    if (!self.waterlevel)
    {
        if (self.flags & FL_INWATER)
        {
            // surface-skim throttle: the bot swim bob (velocity_z 120,
            // not stock water physics) can flicker waterlevel across 0
            // several times a second in a shallow pool, and a faithful
            // enter/exit sound pair per flicker is a machine-gun splash
            // (Shane's first with-sound playtest, the dm2 pool). Flags
            // update every transition; only the sounds rate-limit.
            if (time > self.ar_h2otime)
            {
                sound (self, CHAN_BODY, "misc/outwater.wav", 1, ATTN_NORM);
                self.ar_h2otime = time + 2;
            }
            self.flags = self.flags - FL_INWATER;
        }
        return;
    }

    if (self.ar_feettype == CONTENT_LAVA)
    {
        if (self.dmgtime < time)
        {
            if (self.radsuit_finished > time)
                self.dmgtime = time + 1;
            else
                self.dmgtime = time + 0.2;
            self.deathtype = "lava";
            T_Damage (self, world, world, 10 * self.waterlevel);
        }
    }
    else if (self.ar_feettype == CONTENT_SLIME)
    {
        if (self.dmgtime < time && self.radsuit_finished < time)
        {
            self.dmgtime = time + 1;
            self.deathtype = "slime";
            T_Damage (self, world, world, 4 * self.waterlevel);
        }
    }

    if (!(self.flags & FL_INWATER))
    {
        if (time > self.ar_h2otime)     // see the surface-skim throttle
        {
            if (self.ar_feettype == CONTENT_LAVA)
                sound (self, CHAN_BODY, "player/inlava.wav", 1, ATTN_NORM);
            if (self.ar_feettype == CONTENT_WATER)
                sound (self, CHAN_BODY, "player/inh2o.wav", 1, ATTN_NORM);
            if (self.ar_feettype == CONTENT_SLIME)
                sound (self, CHAN_BODY, "player/slimbrn2.wav", 1, ATTN_NORM);
            self.ar_h2otime = time + 2;
        }
        self.flags = self.flags + FL_INWATER;
        self.dmgtime = 0;
    }
};

// predictive gap jump (2026-08-20, the Omicron review, sampling
// 10.3: at a non-walkable area their bot predicts the jump in 0.1 s
// steps, collisions included, and jumps only "if it is satisfied
// with the result"). Argus unrouted modes could only deflect at a
// brink - the walkway corner tax. This simulates the launch the bot
// could make RIGHT NOW (its own speed along the blocked heading,
// jump 270, gravity 800): each 0.1 s segment is traced at chest
// height; a hit while still rising is a wall and refuses, a hit
// while falling is the landing and must be a floor-ish plane, above
// the survivable-drop line, with air (not lava or slime) sitting on
// it, and far enough out that a hop would not have done. No landing
// inside 1.2 s refuses too - never jump into the unknown.
float(float myaw, float spd) Argus_GapJumpOK =
{
    local vector dir, p0, p1;
    local float t, pz;

    if (spd > 330)
        return FALSE;           // beyond the model; do not extrapolate
    makevectors ('0 0 0' + myaw * '0 1 0');
    dir = v_forward;
    p0 = self.origin;
    t = 0.1;
    while (t < 1.25)
    {
        p1 = self.origin + dir * (spd * t);
        p1_z = self.origin_z + 270 * t - 400 * t * t;
        traceline (p0 + '0 0 24', p1 + '0 0 24', TRUE, self);
        if (trace_fraction < 1)
        {
            if (270 - 800 * t > 0)
                return FALSE;   // hit while rising: a wall
            if (trace_plane_normal_z < 0.7)
                return FALSE;   // steep face, not a landing
            if (trace_endpos_z < self.origin_z + 24 - 220)
                return FALSE;   // deeper than a survivable drop
            pz = pointcontents (trace_endpos + '0 0 12');
            if (pz == CONTENT_LAVA || pz == CONTENT_SLIME)
                return FALSE;   // the pool the gap guard saw
            p1 = trace_endpos - self.origin;
            p1_z = 0;
            if (vlen (p1) < 64)
                return FALSE;   // not a gap, a lip - deflect instead
            return TRUE;
        }
        p0 = p1;
        t = t + 0.1;
    }
    return FALSE;
};

void() Argus_Physics =
{
    local vector wishdir, vh, rto;
    local float wl, spd, moveok, myaw, rhoriz;

    makevectors ('0 0 0' + self.ar_moveyaw * '0 1 0');
    wishdir = v_forward;

    wl = Argus_Waterlevel ();
    // keep the engine field honest: stock code reads it directly, and
    // for bots nothing else maintains it. A stale 3 from an old swim
    // would make the first lightning shot discharge all cells into
    // the bot's own feet (W_FireLightning checks waterlevel > 1).
    self.waterlevel = wl;

    Argus_WaterMove ();
    if (self.health <= 0)
        return;

    // landing thump and falling damage, as PlayerPostThink does it
    if (self.jump_flag < -300 && (self.flags & FL_ONGROUND) && self.health > 0)
    {
        if (self.ar_feettype == CONTENT_WATER)
            sound (self, CHAN_BODY, "player/h2ojump.wav", 1, ATTN_NORM);
        else if (self.jump_flag < -650)
        {
            self.deathtype = "falling";
            T_Damage (self, world, world, 5);
            sound (self, CHAN_VOICE, "player/land2.wav", 1, ATTN_NORM);
        }
        else
            sound (self, CHAN_VOICE, "player/land.wav", 1, ATTN_NORM);
        self.jump_flag = 0;
    }
    if (!(self.flags & FL_ONGROUND))
        self.jump_flag = self.velocity_z;
    if (self.health <= 0)
        return;

    // waterjump note (2026-08-17): a CheckWaterJump mirror was tried
    // here for the FrikBot-review slice and REVERTED â€” across five
    // dm4 matches it correlated with off-band lava deaths and stalls
    // (its 2 s ballistic latch suspends steering at the worst edges).
    // Its real target is dm2's pools; re-attempt it inside the dm2
    // campaign with map-specific bars instead of on dm4's lava.

    if (wl >= 2 && (wl == 3 || !(self.flags & FL_ONGROUND)))
    {
        // swim only when actually swimming: a bot STANDING chest-deep
        // in a wadeable pool walks like anyone else. The tread-with-
        // floor case was the residual splash cycle in Shane's third
        // sound playtest â€” lift, break surface, fall, splash, again.
        if (wl == 3)
            self.velocity_z = 120;  // eyes under: drive for air
        else
            self.velocity_z = 50;   // treading: hold the surface
                                    // without vaulting clear of it â€”
                                    // the 120 bob at waist depth
                                    // skimmed in and out of the
                                    // water and fired the enter/exit
                                    // sound pair at 2 Hz (Shane's
                                    // second with-sound playtest)
        self.velocity_x = self.velocity_x * 0.8 + wishdir_x * 60;
        self.velocity_y = self.velocity_y * 0.8 + wishdir_y * 60;
        self.flags = self.flags - (self.flags & FL_ONGROUND);
        // waterjump, gated to swim-link hops ONLY: waist blocked,
        // eye clear, vault the lip toward the exit node. No timed
        // latch â€” the latch suspending steering was the mechanism
        // that drowned bots in lava on dm4 the first time. The gate
        // means this code cannot run there at all: swim links are
        // only generated for CONTENTS_WATER.
        if (self.ar_mode == 2 && self.ar_hopswim && self.ar_node != world)
        {
            vh = self.origin;
            vh_z = vh_z + 8;
            traceline (vh, vh + wishdir * 24, TRUE, self);
            if (trace_fraction < 1)
            {
                vh_z = self.origin_z + self.maxs_z - 8;
                traceline (vh, vh + wishdir * 24, TRUE, self);
                if (trace_fraction == 1)
                    self.velocity_z = 225;
            }
        }
        if (!self.ar_swim)
        {
            self.ar_swim = 1;
            Argus_Event ("swim");
        }
        return;
    }
    self.ar_swim = 0;

    if (self.flags & FL_ONGROUND)
    {
        if (self.ar_hoprj == 2)
            self.ar_hoprj = 0;          // landed: the blast ride is over

        if (self.ar_mode == 2 && self.ar_hoprj == 1)
        {
            // face the landing and pitch by range: 85-down only works
            // for pads almost under the ledge. dm4 quad pads sit
            // ~180u out and need a shallower blast so the knockback
            // carries inward.
            if (Argus_BotCanRJ (self) && self.ar_node != world)
            {
                rto = self.ar_node.origin - self.origin;
                rto_z = 0;
                rhoriz = vlen (rto);
                if (rhoriz > 8)
                    self.angles_y = vectoyaw (rto);
                self.weapon = IT_ROCKET_LAUNCHER;
                W_SetCurrentAmmo ();
                if (rhoriz < 80)
                    self.v_angle_x = 85;
                else if (rhoriz < 140)
                    self.v_angle_x = 75;
                else
                    self.v_angle_x = 65;
                self.v_angle_y = self.angles_y;
                self.v_angle_z = 0;
                self.velocity_z = AR_JUMPVEL;
                self.flags = self.flags - (self.flags & FL_ONGROUND);
                self.attack_finished = time;
                self.button0 = 0;
                W_Attack ();
                self.ar_hoprj = 2;
                Argus_Event ("rjump");
                return;
            }
            // cannot pay any more: replan without the shortcut
            self.ar_hoprj = 0;
            self.ar_node = world;
            self.ar_pending = 1;
            self.ar_mode = 0;
        }

        if (self.ar_jump)
        {
            self.ar_jump = 0;
            self.velocity_z = AR_JUMPVEL;
            self.flags = self.flags - (self.flags & FL_ONGROUND);
            Argus_Event ("jump");
            return;
        }

        if (self.ar_liftwait)
        {
            // parked on a plat: friction only. No wish, no brink
            // guard - mid-ride every slab edge reads as a void and
            // the guard would deflect the bot straight off the lift
            Argus_Friction ();
            return;
        }

        Argus_Friction ();
        Argus_Accelerate (wishdir, AR_MAXSPEED);

        vh = self.velocity;
        vh_z = 0;
        spd = vlen (vh);
        if (spd > 1)
        {
            myaw = vectoyaw (vh);

            // router-promised jump: on a jump hop, launch the moment
            // the ledge runs out one step ahead. Checked before the
            // brink guard, which would otherwise deflect away from
            // exactly the gap we mean to cross.
            if (self.ar_mode == 2 && self.ar_hopjump && spd >= 250)
            {
                traceline (self.origin + vh * (32 / spd) + '0 0 4',
                           self.origin + vh * (32 / spd) - '0 0 40',
                           TRUE, self);
                if (trace_fraction == 1)
                {
                    self.ar_hopjump = 0;
                    self.velocity_z = AR_JUMPVEL;
                    self.flags = self.flags - (self.flags & FL_ONGROUND);
                    Argus_Event ("jump");
                    return;
                }
            }

            // router-promised DROP (the '2640 -50 120' pin, v366 human
            // tape: Carmack lost 92 s of one session teetering on this
            // lip). The steering target sits far BELOW on a legal
            // sub-200u drop, but a bot arriving at walking pace dies
            // at the edge: CheckBottom refuses the step, speed never
            // builds, and the stall recovery jump-cycles in place.
            // A human just steps off. Commit: when routed at a node
            // 120u+ below within hop range, the heading passes the
            // hazard gate, and speed is dead, take one firm step off
            // the lip and let gravity run the hop.
            if (self.ar_mode == 2 && self.ar_node != world
                && spd < 80 && time > self.ar_gapjump
                && self.ar_node.origin_z < self.origin_z - 120
                && !self.ar_hoplift && !self.ar_hoptrain
                && !self.ar_liftwait)
            {
                rto = self.ar_node.origin - self.origin;
                rto_z = 0;
                if (vlen (rto) < 340
                    && !Argus_MoveHazard (vectoyaw (rto), 48))
                {
                    self.ar_gapjump = time + 1;
                    makevectors ('0 0 0' + vectoyaw (rto) * '0 1 0');
                    self.velocity_x = v_forward_x * 240;
                    self.velocity_y = v_forward_y * 240;
                    self.flags = self.flags - (self.flags & FL_ONGROUND);
                    return;
                }
            }

            // speed-scaled probe distance (the dm4 lava-band session):
            // a fixed 32u at 320+ u/s is a tenth of a second of
            // reaction, and the pit-floor boundary ate full-sprint
            // crossers for six straight builds. Scale with speed up
            // to 52 - inside the 48u envelope the steering fan
            // already probes safely, and the guard has since gained
            // the bridge test, the stair rescue and the HazardSteer
            // hold that the 2026-08-14 long-probe walkway storms
            // predate.
            rhoriz = 32;
            if (spd > 250)
                rhoriz = 32 + (spd - 250) * 0.11;
            if (rhoriz > 52)
                rhoriz = 52;
            if (Argus_MoveHazard (myaw, rhoriz))
            {
                // predictive gap jump: before surrendering the
                // heading to the deflection, see if the jump we
                // could make right now lands dry on the far side.
                // Unrouted modes only - routed hops have their own
                // verified links - and never during a typed hop or
                // door detour. Rate-limited: the arc costs traces.
                if (self.ar_mode != 2 && spd >= 250
                    && time > self.ar_gapjump
                    && !self.ar_hoplift && !self.ar_hoptrain
                    && !self.ar_hopdoor && !self.ar_hoprj)
                {
                    self.ar_gapjump = time + 1;
                    if (Argus_GapJumpOK (myaw, spd))
                    {
                        self.velocity_z = AR_JUMPVEL;
                        self.flags = self.flags
                                   - (self.flags & FL_ONGROUND);
                        Argus_Event ("jump");
                        return;
                    }
                }
                // deflect along the brink, keeping speed: a dead stop
                // here reads as a stall and bleeds all momentum.
                // HazardSteer holds the last safe heading so the
                // +50/-50 fan does not flip every frame at a corner.
                myaw = Argus_HazardSteer (myaw, rhoriz);
                makevectors ('0 0 0' + myaw * '0 1 0');
                self.velocity_x = v_forward_x * spd;
                self.velocity_y = v_forward_y * spd;
                if (time > self.ar_nexthazlog)
                {
                    self.ar_nexthazlog = time + 1;
                    Argus_Event ("hazard");
                }
                // v3.16 slide semantics: a BLOCKED deflection must
                // unground so engine flymove turns the wall into a
                // slide â€” staying grounded pinned bots motionless at
                // brink corners (2026-08-18 forensics: stalls 40-62;
                // the drift-in worry is not in the v3.16 record,
                // which held lava at 1-3 for its whole life)
                moveok = walkmove (myaw, spd * frametime);
                if (!moveok)
                    self.flags = self.flags - (self.flags & FL_ONGROUND);
            }
            else
            {
                moveok = walkmove (myaw, spd * frametime);
                if (!moveok)
                {
                    // Engine SV_CheckBottom point-traces the bbox
                    // quadrants, so a decorative grate floor (dm2
                    // south-east: 16u channels between strips the
                    // hull bridges) reads as walking off an edge and
                    // walkmove refuses every step. The flymove slide
                    // fallback cannot climb the pattern's 4u strip
                    // seams (no stair logic airborne), which pinned
                    // bots at spd 0 on the seam - Shane shot one
                    // standing frozen. FL_PARTIALGROUND is id's own
                    // escape hatch: SV_movestep completes the step,
                    // stairs intact, when CheckBottom dissents. Safe
                    // here because this heading already passed the
                    // bridge-aware hazard gate, which is the real
                    // ledge judge; walls still refuse (allsolid runs
                    // before the flag check) and keep the slide.
                    self.flags = self.flags | FL_PARTIALGROUND;
                    moveok = walkmove (myaw, spd * frametime);
                    self.flags = self.flags - (self.flags & FL_PARTIALGROUND);
                }
                if (!moveok)
                    self.flags = self.flags - (self.flags & FL_ONGROUND);
            }
        }
    }
    else
    {
        self.ar_jump = 0;
        Argus_AirAccelerate (wishdir, AR_MAXSPEED);
    }
};

// ---------------------------------------------------------------- death

void() Argus_Die =
{
    // one death line only: the detailed form below. A bare
    // Argus_Event ("death") used to precede it and every parser that
    // counted the death token saw two events per death (Shane's
    // project review, 2026-08-18) â€” event counts across this
    // boundary halve while analyzer deaths totals are unchanged
    dprint ("ARGEVT ");
    dprint (self.netname);
    dprint (" death ");
    // a nameless killer (crusher door, missile entity â€” anything
    // without a netname) used to print an EMPTY killer field and
    // strict parsers dropped the row (Shane's fix-now list; dm2's
    // crusher was the live case). Nameless killers are "world".
    if (self.enemy != world && self.enemy.netname != "")
        dprint (self.enemy.netname);
    else
        dprint ("world");
    dprint (" pos ");
    dprint (vtos(self.origin));
    dprint ("\n");

    // nemesis ledger (OPM slice C): a third straight death to the
    // same player is a vendetta â€” the affect the source spec wanted,
    // reduced to the one signal deathmatch actually shows
    if (self.enemy != world && self.enemy != self
        && self.enemy.classname == "player")
    {
        if (self.enemy == self.ar_nemesis)
            self.ar_nemkills = self.ar_nemkills + 1;
        else
        {
            self.ar_nemesis = self.enemy;
            self.ar_nemkills = 1;
        }
    }

    self.ar_enemy = world;
    self.ar_goal = world;
    self.ar_node = world;
    self.ar_pending = 0;
    self.ar_mode = 0;
    self.ar_hopjump = 0;
    self.ar_hoprj = 0;
    self.ar_hoptrain = 0;
    self.ar_hopdoor = 0;
    self.ar_hazhold = 0;
    self.ar_aimvel = 0;         // no ghost flick on respawn
    self.ar_door = world;
    self.ar_doorbtn = world;
    self.button0 = 0;
    // invalidate every route trace this bot left behind, and abort an
    // in-flight search whose completion would otherwise hand the
    // respawned bot a start node from its pre-death position
    self.ar_routegen = self.ar_routegen + 1;
    if (an_busy && an_bot == self)
        an_busy = 0;
    Argus_Chat (2);
    self.ar_respawntime = time + 1.5;

    // stock death: backpack drop, death sound, gib below -40 health,
    // else one of the five death animations (think chains run fine on
    // MOVETYPE_TOSS). Longest chain is ~1.1 s, inside the 1.5 s window.
    // Gibbing turns this entity into the bouncing head, and head.mdl
    // has one skin: drop the bot colour first or the renderer warns
    // every frame under developer 1
    if (self.health < -40)
        self.skin = 0;
    PlayerDie ();
    // corpses are not re-killable: a second Killed() would double
    // frags and telemetry (humans avoid this via the body queue)
    self.takedamage = DAMAGE_NO;
};

void(entity attacker, float dmg) Argus_Pain =
{
    // flinch: tracking restarts, aim error widens for a moment
    self.ar_track = time;
    // knockback can launch: the engine only flymoves STEP entities
    // that are off the ground, so a strong vertical impulse has to
    // clear FL_ONGROUND itself or the bot stays glued to the floor
    if (self.velocity_z > 180)
        self.flags = self.flags - (self.flags & FL_ONGROUND);
    // fight back if hit from behind by someone new: any live player,
    // human or bot (world excluded: lava damage is not an attacker)
    if (attacker.classname == "player" && attacker.health > 0
        && attacker != self && self.ar_enemy == world)
    {
        self.ar_enemy = attacker;
        self.ar_seen = time;
        self.ar_react = time + self.ar_reactbase * 0.7 + random () * 0.2;
        self.ar_track = time;
    }
};

// The difficulty dial (first slice of the Omicron soul). Reads the
// stock skill cvar via the skill global at every spawn, so "skill 0"
// through "skill 3" in the console retunes bots from their next
// respawn. Skill 2 is the tuning that dominated the eighth playtest;
// the deathmatch default of skill 1 sits a notch below it. Per-bot
// personality offsets ride on top: Reap hunts (quick), Omi aims
// (precise but deliberate), Zeus storms (fastest trigger, wildest aim).
void() Argus_SetSkill =
{
    local float s;

    s = skill;
    if (s < 0) s = 0;
    if (s > 3) s = 3;

    // spring gains: k = omega^2, c = 2*zeta*omega with zeta ~0.8
    // (slight overshoot). The source spec's k 18-32 confused omega
    // with k and aimed like molasses (springaim1/2 ladder: engages
    // 49-56, deaths 24-25 â€” fights that never ended). omega 9-20
    // rad/s settles in 0.2-0.45 s, a human flick-and-correct.
    if (s == 0)
    { self.ar_aimerr = 2.2; self.ar_reactbase = 0.65; self.ar_aimrate = 170;
      self.ar_spring_k = 110; self.ar_damping_c = 16.8; }
    else if (s == 1)
    { self.ar_aimerr = 1.6; self.ar_reactbase = 0.48; self.ar_aimrate = 210;
      self.ar_spring_k = 200; self.ar_damping_c = 22.6; }
    else if (s == 2)
    { self.ar_aimerr = 1.0; self.ar_reactbase = 0.30; self.ar_aimrate = 260;
      self.ar_spring_k = 360; self.ar_damping_c = 30.4; }
    else
    { self.ar_aimerr = 0.7; self.ar_reactbase = 0.22; self.ar_aimrate = 300;
      self.ar_spring_k = 560; self.ar_damping_c = 37.9; }

    // personalities key on ROSTER SLOT, not netname (v3.37): Shane
    // renamed the roster and every bot silently fell into the
    // wild-aim else branch. Slot 0 = the flick, 1 = the smooth
    // operator, 2 and 3 = the glory hounds. Names are labels only â€”
    // rename freely (one word!), the play styles stay put.
    if (self.ar_slot == 0)
    {
        self.ar_reactbase = self.ar_reactbase - 0.05;
        self.ar_aimerr = self.ar_aimerr * 0.95;
        self.ar_spring_k = self.ar_spring_k * 1.15;    // twitch flick
    }
    else if (self.ar_slot == 1)
    {
        self.ar_aimrate = self.ar_aimrate + 30;
        self.ar_aimerr = self.ar_aimerr * 0.85;
        self.ar_reactbase = self.ar_reactbase + 0.05;
        self.ar_damping_c = self.ar_damping_c * 1.15;  // smooth settle
    }
    else
    {
        self.ar_reactbase = self.ar_reactbase - 0.08;
        self.ar_aimerr = self.ar_aimerr * 1.15;
        self.ar_spring_k = self.ar_spring_k * 1.1;     // wild overshoot
        self.ar_damping_c = self.ar_damping_c * 0.9;
    }
    if (self.ar_reactbase < 0.1)
        self.ar_reactbase = 0.1;

    // utility appetites: personalities want different things from the
    // map, not just different trigger fingers
    self.ar_wweap = 1;
    self.ar_wheal = 1;
    self.ar_warmor = 1;
    self.ar_wpow = 1;
    if (self.ar_slot == 0)
    {
        self.ar_wweap = 1.3;        // armed first, always
        self.ar_warmor = 0.8;
    }
    else if (self.ar_slot == 1)
    {
        self.ar_wheal = 1.2;        // survives the long game
        self.ar_warmor = 1.4;
        self.ar_wpow = 0.8;
    }
    else
    {
        self.ar_wheal = 0.8;        // slots 2 and 3: glory hounds
        self.ar_warmor = 0.7;
        self.ar_wpow = 1.5;
    }
};

void() Argus_BaseStats =
{
    Argus_SetSkill ();
    self.health = 100;
    // spawn-field parity with PutClientInServer: max_health 0 made
    // T_Heal refuse every normal health box (bots were never healed
    // by them) and let megahealth rot drain bots toward zero
    self.max_health = 100;
    self.air_finished = time + 12;
    self.dmg = 2;
    self.pain_finished = 0;
    self.dmgtime = 0;
    self.jump_flag = 0;
    self.ar_hazhold = 0;
    self.deathtype = "";
    self.effects = 0;
    self.super_damage_finished = 0;
    self.super_time = 0;
    self.super_sound = 0;
    self.invisible_finished = 0;
    self.invisible_time = 0;
    self.invincible_finished = 0;
    self.invincible_time = 0;
    self.invincible_sound = 0;
    self.radsuit_finished = 0;
    self.rad_time = 0;
    self.flags = self.flags - (self.flags & FL_INWATER);
    self.takedamage = DAMAGE_AIM;
    self.solid = SOLID_SLIDEBOX;
    self.movetype = MOVETYPE_STEP;
    self.deadflag = DEAD_NO;
    self.velocity = '0 0 0';
    self.items = IT_SHOTGUN | IT_AXE;
    self.ammo_shells = 25;
    self.ammo_nails = 0;
    self.ammo_rockets = 0;
    self.ammo_cells = 0;
    self.armorvalue = 0;
    self.armortype = 0;
    self.weapon = IT_SHOTGUN;
    self.attack_finished = time;
    self.button0 = 0;
    self.th_die = Argus_Die;
    self.th_pain = Argus_Pain;
    W_SetCurrentAmmo ();
};

entity() Argus_SpawnSpot =
{
    local entity spot;

    spot = find (argus_lastspot, classname, "info_player_deathmatch");
    if (spot == world)
        spot = find (world, classname, "info_player_deathmatch");
    argus_lastspot = spot;
    return spot;
};

void() Argus_Respawn =
{
    local entity spot, oself;

    spot = Argus_SpawnSpot ();
    // undo the corpse: GibPlayer left this entity as a bouncing head,
    // and the death anim left it flat on a late frame
    setmodel (self, "progs/player.mdl");
    setsize (self, '-16 -16 -24', '16 16 32');
    self.frame = 0;
    self.skin = self.ar_slot + 1;
    self.view_ofs = '0 0 22';
    setorigin (self, spot.origin + '0 0 1');
    self.angles_y = spot.angles_y;
    self.angles_x = 0;
    self.angles_z = 0;
    self.ar_moveyaw = self.angles_y;
    // the stock spawn rites: fog, and telefrag whoever is standing
    // here (their absence let a bot respawn inside a human and lock
    // both solid â€” found by the fifth playtest)
    spawn_tfog (self.origin);
    spawn_tdeath (self.origin, self);
    Argus_BaseStats ();
    self.ar_lastpos = self.origin;
    self.ar_nextstall = time + 2;
    self.ar_stallrun = 0;

    oself = self;
    droptofloor ();
    self = oself;

    player_run ();
    Argus_Event ("respawn");
};

// ---------------------------------------------------------------- doors
// func_door / func_door_secret both set classname "door" at spawn.
// The first door draft looked for "func_door" and never matched, so
// bots walked the empty hull-1 doorway into the closed slab.

float(entity e) Argus_IsDoor =
{
    if (e == world)
        return FALSE;
    if (e.classname == "door")
        return TRUE;
    if (e.classname == "func_door")
        return TRUE;
    if (e.classname == "func_door_secret")
        return TRUE;
    return FALSE;
};

void(entity d) Argus_TakeDoor =
{
    local entity b, best;
    local float bd, dist;
    local vector p;

    self.ar_door = d;
    self.ar_doortime = time + 8;
    self.ar_doorbtn = world;
    if (d.targetname == "")
        return;                 // touch-open: walk in, masquerade fires it
    best = world;
    bd = 1024;
    b = find (world, target, d.targetname);
    while (b != world)
    {
        if (b.classname == "func_button")
        {
            p = (b.absmin + b.absmax) * 0.5;
            dist = vlen (p - self.origin);
            if (dist < bd)
            {
                // a touch button beats a shoot plate at the same
                // range; slice 3 is the dedicated shoot path
                if (best == world || b.health == 0 || best.health > 0)
                {
                    best = b;
                    bd = dist;
                }
            }
        }
        b = find (b, target, d.targetname);
    }
    self.ar_doorbtn = best;
    if (best != world)
        Argus_Event ("door");
};

// ---------------------------------------------------------------- combat

float(entity e) Argus_CanSee =
{
    if (e == world)
        return FALSE;
    if (e.cam_active)
        return FALSE;   // an ArgusCam spectator is a ghost: bots must
                        // not acquire, track, or shoot the camera
                        // (Shane's review: bots attacked him in cam
                        // mode - the masquerade scan sees classname
                        // "player" and health > 0 either way)
    if (e.health <= 0)
        return FALSE;
    // the ring: an invisible enemy is eyes only, so treat it as unseen
    // beyond close range apart from a rare glimpse (stock monster
    // manners; one glimpse still buys the 3 s sight-loss hold)
    if (e.invisible_finished > time)
    {
        if (vlen (e.origin - self.origin) > 250)
        {
            if (random () > 0.02)
                return FALSE;
        }
    }
    traceline (self.origin + '0 0 22', e.origin + '0 0 22', TRUE, self);
    if (trace_fraction == 1)
        return TRUE;
    return FALSE;
};

// OPM slice B: gunfire is the tactical sound. Every live bot in
// earshot records it in a one-slot audio memory; a wall between damps
// the radius by 1.4x (an eye trace, not real propagation â€” the right
// lie at deathmatch scale). Called from W_Attack for every player,
// human or bot, so bots hear Shane the way he hears them.
void(vector spos, entity who) Argus_HearSound =
{
    local entity b;
    local float d;

    b = argus_bots;
    while (b != world)
    {
        if (b != who && b.health > 0)
        {
            d = vlen (b.origin - spos);
            if (d < 1000)
            {
                traceline (b.origin + '0 0 22', spos, TRUE, b);
                if (trace_fraction < 1)
                    d = d * 1.4;
                if (d < 1000)
                {
                    b.ar_sndpos = spos;
                    b.ar_sndtime = time;
                    b.ar_sndent = who;
                    // weapon-sound classification (mre Predator):
                    // the listener knows WHAT it heard, and the
                    // investigation gate scales its appetite by it
                    b.ar_sndweap = who.weapon;
                }
            }
        }
        b = b.ar_chain;
    }
};

void() Argus_Perceive =
{
    local entity b, best;
    local float d, bd, ok;
    local vector to;

    // current enemy: still valid?
    if (self.ar_enemy != world)
    {
        if (self.ar_enemy.health <= 0)
            self.ar_enemy = world;
        else if (Argus_CanSee (self.ar_enemy))
        {
            self.ar_seen = time;
            self.ar_lastseen = self.ar_enemy.origin;
            self.ar_pursuing = 0;
            // combat memory: whoever we are fighting stays
            // re-acquirable at 360 degrees for 5 s after any drop
            self.ar_lastfoe = self.ar_enemy;
            self.ar_foetime = time;
        }
        else if (time > self.ar_seen + 3)
            self.ar_enemy = world;
        if (self.ar_enemy != world)
            return;
    }

    // acquire the best visible player, bots and humans alike (both
    // carry classname "player"; the masquerade cuts both ways). Target
    // choice is utility, not raw distance: near beats far, wounded
    // beat healthy, and a quad carrier beats everything, because the
    // worst place for a quad is someone else's hands.
    best = world;
    bd = 0;
    makevectors (self.angles);      // v_forward for the FOV gate
    b = find (world, classname, "player");
    while (b != world)
    {
        if (b != self && b.health > 0)
        {
            d = vlen (b.origin - self.origin);
            if (d < 2500)
            {
                // soft FOV (OPM slice B): a NEW target beyond 500u
                // must be roughly in front (about 155 degrees with
                // peripheral) or freshly heard nearby. Close range
                // stays free â€” peripheral vision and footsteps.
                // Tracking of the current enemy is unaffected.
                ok = 1;
                if (ar_opm_ears && d > 500)
                {
                    if (normalize (b.origin - self.origin) * v_forward < 0.2)
                    {
                        ok = 0;
                        if (time < self.ar_sndtime + 2.5
                            && vlen (b.origin - self.ar_sndpos) < 300)
                            ok = 1;
                        // combat memory (the "getting dumber" fix):
                        // a recent foe is re-acquirable at 360
                        // degrees â€” you do not forget who you were
                        // just fighting because they stepped behind
                        // you. 72 pursue events against 15 engages
                        // in the v3.37 human tape was this gate
                        // breaking fights five times each.
                        if (b == self.ar_lastfoe
                            && time < self.ar_foetime + 5)
                            ok = 1;
                    }
                }
                if (ok)
                {
                    d = (2500 - d) + (100 - b.health) * 3;
                    if (b.super_damage_finished > time)
                        d = d + 600;
                    // vendetta (OPM slice C): the one who keeps
                    // killing us outranks the shopping list
                    if (b == self.ar_nemesis && self.ar_nemkills >= 3)
                        d = d + 600;
                    if (d > bd)
                    {
                        if (Argus_CanSee (b))
                        {
                            best = b;
                            bd = d;
                        }
                    }
                }
            }
        }
        b = find (b, classname, "player");
    }

    // glance at a fresh noise when nothing is in sight: facing only,
    // movement untouched (facing is decoupled), so the worst case is
    // looking the wrong way â€” and the FOV gate then admits whoever
    // fired, which closes the hear-turn-see loop
    if (ar_opm_ears && best == world && self.ar_enemy == world
        && self.ar_sndtime > 0 && time < self.ar_sndtime + 2.0)
    {
        to = self.ar_sndpos - self.origin;
        to_z = 0;
        if (vlen (to) > 40)
            self.angles_y = vectoyaw (to);
    }

    if (best != world)
    {
        self.ar_enemy = best;
        self.ar_seen = time;
        self.ar_lastseen = best.origin;
        self.ar_pursuing = 0;
        self.ar_react = time + self.ar_reactbase + random () * 0.25;
        self.ar_track = time;
        self.ar_strafedir = 1;
        if (random () < 0.5)
            self.ar_strafedir = -1;
        self.ar_strafetime = time;
        dprint ("ARGEVT ");
        dprint (self.netname);
        dprint (" engage ");
        dprint (best.netname);
        dprint ("\n");
    }
};

// Bot version of the client-only CheckPowerups: expiry, glow, and the
// eyes model. Without it, picked-up powerups stayed active-flagged
// forever: stale quad drops on death, quad-flavoured obituaries for
// ordinary kills, no glow, and rings that never turned a bot into eyes.
void() Argus_CheckPowerups =
{
    if (self.invisible_finished)
    {
        if (self.invisible_finished < time)
        {
            self.items = self.items - (self.items & IT_INVISIBILITY);
            self.invisible_finished = 0;
            self.invisible_time = 0;
        }
        if (self.invisible_finished > time)
        {
            self.frame = 0;
            self.modelindex = modelindex_eyes;
            self.skin = 0;      // eyes.mdl has one skin
        }
        else
        {
            self.modelindex = modelindex_player;
            self.skin = self.ar_slot + 1;
        }
    }

    if (self.invincible_finished)
    {
        if (self.invincible_finished < time)
        {
            self.items = self.items - (self.items & IT_INVULNERABILITY);
            self.invincible_finished = 0;
            self.invincible_time = 0;
        }
        if (self.invincible_finished > time)
            self.effects = self.effects | EF_DIMLIGHT;
        else
            self.effects = self.effects - (self.effects & EF_DIMLIGHT);
    }

    if (self.super_damage_finished)
    {
        if (self.super_damage_finished < time)
        {
            self.items = self.items - (self.items & IT_QUAD);
            self.super_damage_finished = 0;
            self.super_time = 0;
        }
        if (self.super_damage_finished > time)
            self.effects = self.effects | EF_DIMLIGHT;
        else if (self.invincible_finished < time)
            self.effects = self.effects - (self.effects & EF_DIMLIGHT);
    }

    if (self.radsuit_finished && self.radsuit_finished < time)
    {
        self.items = self.items - (self.items & IT_SUIT);
        self.radsuit_finished = 0;
        self.rad_time = 0;
    }
};

// Best owned weapon with ammo for a fight at distance d. The stock
// W_CheckNoAmmo never runs for bots (it lives in the human input
// path), so ammo gating happens here; W_Attack itself never checks.
void(float d) Argus_SelectWeapon =
{
    local float w;
    local string wn;

    if ((self.items & IT_LIGHTNING) && self.ammo_cells >= 1
        && d < 480 && self.watertype > CONTENT_WATER)
        w = IT_LIGHTNING;
    else if ((self.items & IT_ROCKET_LAUNCHER) && self.ammo_rockets >= 1
             && d > 180)
        w = IT_ROCKET_LAUNCHER;
    else if ((self.items & IT_SUPER_NAILGUN) && self.ammo_nails >= 2)
        w = IT_SUPER_NAILGUN;
    else if ((self.items & IT_GRENADE_LAUNCHER) && self.ammo_rockets >= 1
             && d > 180 && d < 650)
        w = IT_GRENADE_LAUNCHER;
    else if ((self.items & IT_SUPER_SHOTGUN) && self.ammo_shells >= 2)
        w = IT_SUPER_SHOTGUN;
    else if ((self.items & IT_NAILGUN) && self.ammo_nails >= 1)
        w = IT_NAILGUN;
    else if ((self.items & IT_SHOTGUN) && self.ammo_shells >= 1)
        w = IT_SHOTGUN;
    else
        w = IT_AXE;

    if (w == self.weapon)
        return;

    self.weapon = w;
    W_SetCurrentAmmo ();

    if (w == IT_AXE)                    wn = "axe";
    else if (w == IT_SHOTGUN)           wn = "sg";
    else if (w == IT_SUPER_SHOTGUN)     wn = "ssg";
    else if (w == IT_NAILGUN)           wn = "ng";
    else if (w == IT_SUPER_NAILGUN)     wn = "sng";
    else if (w == IT_GRENADE_LAUNCHER)  wn = "gl";
    else if (w == IT_ROCKET_LAUNCHER)   wn = "rl";
    else                                wn = "lg";
    dprint ("ARGEVT ");
    dprint (self.netname);
    dprint (" weapon ");
    dprint (wn);
    dprint ("\n");
};

// Scan for an inbound enemy projectile and commit a perpendicular
// sidestep (cortex's dodge design). LQ rockets are classname
// battle get item (2026-08-20, the Omicron review: their AI tree's
// battle-get-item leaf grabs a useful nearby item MID-FIGHT and
// returns to the fray, shooting throughout). Argus combat suspended
// goals entirely, so a wounded bot strafed past the health box at
// its feet. Every 0.5 s of combat, findradius sweeps 240u for the
// best live item worth grabbing NOW (Argus_ItemValue, so a full-
// health bot ignores health and a shell box only tempts a dry
// shotgunner); the walk to it must pass Argus_SafeLine exactly like
// a mode-1 beeline, because grabbing across a lava lip is how the
// dodge ladder lost bots. The steer commits 1.5 s and sits between
// strafe and dodge in priority: a dodge or retreat overrides it,
// plain circling does not. Aim stays decoupled - the bot shoots
// the whole detour.
float(entity it) Argus_ItemClass;
float(entity it, float cls) Argus_ItemValue;
vector(entity it) Argus_GoalPoint;

void() Argus_BattleItemScan =
{
    local entity it, best;
    local float v, bv;

    best = world;
    bv = 11;        // grab floor: below this the detour is not worth
                    // breaking the circle for
    it = findradius (self.origin, 240);
    while (it != world)
    {
        if ((it.flags & FL_ITEM) && it.solid == SOLID_TRIGGER
            && !(it == self.ar_bitemlast && time < self.ar_bitemcool))
        {
            v = Argus_ItemValue (it, Argus_ItemClass (it));
            if (v > bv && Argus_SafeLine (Argus_GoalPoint (it)))
            {
                best = it;
                bv = v;
            }
        }
        it = it.chain;
    }
    if (best == world || best == self.ar_bitem)
        return;             // never refresh a running commit: a grab
                            // gets ONE 1.5 s window, so an item that
                            // SafeLine likes but walkmove cannot reach
                            // (the '2448 -80 104' perch pin, bitem1)
                            // cannot hold the steer forever
    dprint ("ARGEVT ");
    dprint (self.netname);
    dprint (" grab ");
    dprint (best.classname);
    dprint ("\n");
    self.ar_bitem = best;
    self.ar_bitemend = time + 1.5;
};

// "rocket", not stock's "missile". The 55% commit chance keeps the
// dodge human: serial rockets still land sometimes at every tier.
// Spikes are not scanned - a 1000 u/s nail is not human-reactable.
void() Argus_DodgeScan =
{
    local entity m;
    local vector to;
    local float d, side;

    m = find (world, classname, "rocket");
    while (m != world)
    {
        if (m.owner != self)
        {
            to = self.origin - m.origin;
            d = vlen (to);
            if (d > 60 && d < 520)
            {
                if (normalize (m.velocity) * normalize (to) > 0.92
                    && random () < 0.55)
                {
                    // sidestep across the shot - but a committed
                    // 0.3 s step travels ~96u, so BOTH sides get
                    // probed at 48 and 90, and a bot with lava both
                    // ways holds the line instead (the first ladder
                    // took the unchecked fallback side straight off
                    // the dm4 walkways, lava 5)
                    side = vectoyaw (m.velocity) + 90;
                    if (Argus_MoveHazard (side, 48)
                        || Argus_MoveHazard (side, 90))
                    {
                        side = vectoyaw (m.velocity) - 90;
                        if (Argus_MoveHazard (side, 48)
                            || Argus_MoveHazard (side, 90))
                            return;
                    }
                    self.ar_dodgeyaw = side;
                    self.ar_dodgetime = time + 0.3;
                    return;
                }
            }
        }
        m = find (m, classname, "rocket");
    }
    m = find (world, classname, "grenade");
    while (m != world)
    {
        if (m.owner != self)
        {
            to = self.origin - m.origin;
            d = vlen (to);
            // a grenade threatens where it lands: shorter window,
            // looser cone, always step away from its track
            if (d > 40 && d < 320)
            {
                if (normalize (m.velocity) * normalize (to) > 0.8
                    && random () < 0.55)
                {
                    side = vectoyaw (m.velocity) + 90;
                    if (Argus_MoveHazard (side, 48)
                        || Argus_MoveHazard (side, 90))
                    {
                        side = vectoyaw (m.velocity) - 90;
                        if (Argus_MoveHazard (side, 48)
                            || Argus_MoveHazard (side, 90))
                            return;
                    }
                    self.ar_dodgeyaw = side;
                    self.ar_dodgetime = time + 0.35;
                    return;
                }
            }
        }
        m = find (m, classname, "grenade");
    }
};

// returns TRUE while combat is steering the bot
float() Argus_Combat =
{
    local entity e;
    local vector to, aimpt, err, cvr;
    local float d, want, diff, turn, trackt, errscale, loft;
    local float cy, ck, cfound, ceff;

    Argus_Perceive ();
    e = self.ar_enemy;
    if (e == world)
    {
        self.button0 = 0;
        return FALSE;
    }
    if (time > self.ar_seen + 0.4)
    {
        self.button0 = 0;
        // pursue the corner they vanished behind instead of snapping
        // back to the shopping list â€” goal routes pass teleporter
        // mouths, and resuming them mid-fight read as "fleeing into
        // the teleporter" (ninth playtest: 9 of 17 tele trips were
        // mid-combat)
        to = self.ar_lastseen - self.origin;
        to_z = 0;
        if (time < self.ar_seen + 2.5 && vlen (to) > 80)
        {
            want = vectoyaw (to);
            if (!Argus_MoveHazard (want, 48))
            {
                if (!self.ar_pursuing)
                {
                    self.ar_pursuing = 1;
                    Argus_Event ("pursue");
                }
                diff = want - self.angles_y;
                while (diff > 180)  diff = diff - 360;
                while (diff < -180) diff = diff + 360;
                turn = AR_TURNRATE * frametime;
                if (diff > turn)        diff = turn;
                else if (diff < -turn)  diff = -turn;
                self.angles_y = self.angles_y + diff;
                self.ar_moveyaw = self.angles_y;
                return TRUE;        // combat still owns the steering
            }
        }
        return FALSE;               // gave up: let navigation resume
    }

    to = e.origin - self.origin;
    d = vlen (to);

    Argus_SelectWeapon (d);

    // ---- facing: rate-limited aim tracking with shrinking error ----
    trackt = time - self.ar_track;
    errscale = 1.6 - trackt;
    if (errscale < 0.35)
        errscale = 0.35;
    err_x = (random () - 0.5) * AR_AIMERR * self.ar_aimerr * (d / 500) * errscale * 2;
    err_y = (random () - 0.5) * AR_AIMERR * self.ar_aimerr * (d / 500) * errscale * 2;
    err_z = (random () - 0.5) * AR_AIMERR * self.ar_aimerr * (d / 500) * errscale;
    aimpt = e.origin + '0 0 12' + err;

    // projectile leading (Shane's review): aim where they will be.
    // Time of flight = dist over projectile speed â€” rockets and nails
    // 1000 u/s, grenades a ~600 u/s toss. Hitscan (SG/SSG/LG) and the
    // axe lead nothing. One step, not an iterated solution: close
    // enough at DM ranges, and the error model still rides on top.
    if (self.weapon == IT_ROCKET_LAUNCHER)
        aimpt = aimpt + e.velocity * (d / 1000);
    else if (self.weapon == IT_GRENADE_LAUNCHER)
        aimpt = aimpt + e.velocity * (d / 600);
    else if (self.weapon == IT_NAILGUN || self.weapon == IT_SUPER_NAILGUN)
        aimpt = aimpt + e.velocity * (d / 1000);

    // ballistic loft / lip compensation. Rockets fly straight; when
    // the target is well below (dm4 walkway to pit) aim down a little
    // so the shot does not kiss the walkway edge. Grenades drop under
    // gravity 800 after a ~600 u/s toss, so they need loft, more so
    // when the target is above.
    if (self.weapon == IT_GRENADE_LAUNCHER)
    {
        loft = d * d / 2400;
        if (loft > 96)
            loft = 96;
        if (e.origin_z > self.origin_z + 32)
            loft = loft + (e.origin_z - self.origin_z) * 0.25;
        aimpt_z = aimpt_z + loft;
    }
    else if (self.weapon == IT_ROCKET_LAUNCHER)
    {
        if (e.flags & FL_ONGROUND)
            // foot splash (OPM slice A): a grounded target is aimed
            // at the floor, not centre mass â€” the splash lands even
            // when the dodge works, and the knockback juggles
            aimpt_z = e.origin_z - 16;
        else if (e.origin_z < self.origin_z - 64)
            aimpt_z = aimpt_z + (e.origin_z - self.origin_z) * 0.2;
        else if (e.origin_z > self.origin_z + 64)
            aimpt_z = aimpt_z + 8;
    }

    want = vectoyaw (aimpt - self.origin);
    diff = want - self.angles_y;
    while (diff > 180)  diff = diff - 360;
    while (diff < -180) diff = diff + 360;
    // damped-spring mouse model (OPM slice A): a human aim is a
    // neuromotor spring, not a constant-rate servo â€” fast flick,
    // slight overshoot, settle, micro-tremor. Explicit Euler is
    // stable at these gains (k*dt^2 well under 1 at 20 Hz worst
    // case); velocity clamped to a fast human flick.
    turn = 1 - self.ar_damping_c * frametime;
    if (turn < 0.1)
        turn = 0.1;             // 20 Hz rigs must not ring
    self.ar_aimvel = self.ar_aimvel * turn
                   + diff * self.ar_spring_k * frametime;
    if (self.ar_aimvel > 720)  self.ar_aimvel = 720;
    if (self.ar_aimvel < -720) self.ar_aimvel = -720;
    turn = 0.3;                              // tremor, degrees
    if (self.health < 40)
        turn = 0.8;                          // adrenaline shake
    self.angles_y = self.angles_y + self.ar_aimvel * frametime
                  + (random () - 0.5) * turn;
    // remaining error feeds the trigger gate below (the old limiter
    // reused the clamped step for this; the spring must not)
    diff = want - self.angles_y;
    while (diff > 180)  diff = diff - 360;
    while (diff < -180) diff = diff + 360;

    // ---- movement: circle strafe, close or open range ----
    if (time > self.ar_strafetime)
    {
        self.ar_strafetime = time + 0.8 + random ();
        if (random () < 0.4)
            self.ar_strafedir = 0 - self.ar_strafedir;
    }
    if (d > 550)
        self.ar_moveyaw = vectoyaw (to);
    else if (d < 130)
        self.ar_moveyaw = vectoyaw ('0 0 0' - to);
    else
        self.ar_moveyaw = vectoyaw (to) + 80 * self.ar_strafedir;

    // battle get item (Omicron review): the circle bends toward a
    // worthwhile live item nearby. Dodge, axe charge and retreat all
    // sit later in this chain and override the detour; the lava flip
    // below re-checks whatever heading survives.
    if (!self.ar_retreating)
    {
        if (time > self.ar_bitemscan)
        {
            self.ar_bitemscan = time + 0.5;
            Argus_BattleItemScan ();
        }
        if (self.ar_bitem != world)
        {
            if (self.ar_bitem.solid != SOLID_TRIGGER)
                self.ar_bitem = world;      // eaten - clean success
            else if (time > self.ar_bitemend)
            {
                // commit lapsed with the item still live: the walk
                // is not landing (perch, thin wall, crowd). Cool
                // this item so the scan cannot re-pin us on it.
                self.ar_bitemlast = self.ar_bitem;
                self.ar_bitemcool = time + 8;
                self.ar_bitem = world;
            }
            else
                self.ar_moveyaw =
                    vectoyaw (Argus_GoalPoint (self.ar_bitem)
                              - self.origin);
        }
    }

    // missile dodge (cortex's design, upgraded from the idea bank):
    // an inbound enemy rocket or grenade makes the bot sidestep
    // perpendicular to the shot. Decoupled aim means it keeps
    // shooting while it steps. Runs before the lava flip below, so
    // a dodge heading into a brink is vetoed like any other.
    if (time > self.ar_dodgecheck)
    {
        self.ar_dodgecheck = time + 0.15;
        Argus_DodgeScan ();
    }
    if (time < self.ar_dodgetime)
        self.ar_moveyaw = self.ar_dodgeyaw;

    // the axe has no reach: the band logic above backs a dry bot
    // away from melee forever (Shane's review, fix 3). Charge
    // instead; the hazard check below still vetoes charging a brink
    if (self.weapon == IT_AXE)
        self.ar_moveyaw = vectoyaw (to);

    // ---- retreat by GEOMETRY, not speed (cortex DISENGAGE; third
    // attempt - the two 2026-08-18 backpedal retreats died in the
    // open and their post-mortems are recorded below this block).
    // Low stack: move along a heading that keeps floor under it AND
    // whose destination breaks the enemy's line of sight. Cover is a
    // wall between us, never distance. Aim is decoupled, so the bot
    // shoots the whole way; the missile dodge below still outranks
    // this for a moment, and the lava flip re-checks whatever we
    // choose.
    ceff = self.health + self.armorvalue * self.armortype;
    if (self.ar_retreating)
    {
        // hysteresis: stay out until the stack recovers or the fight
        // is winnable (finish a nearly-dead enemy instead of hiding)
        if (ceff > 55 || e.health <= 30 || self.super_damage_finished > time)
            self.ar_retreating = 0;
    }
    else if (ceff < 35 && e.health > 30
             && self.super_damage_finished < time
             && self.weapon != IT_AXE)
    {
        self.ar_retreating = 1;
        self.ar_covertime = 0;      // pick a cover leg this frame
        Argus_Event ("retreat");
    }

    if (self.ar_retreating)
    {
        if (time > self.ar_covertime)
        {
            // candidate fan away from the enemy, nearest-to-directly-
            // away first. A candidate must keep floor at 48 AND 90
            // (a committed leg travels far - the second dead retreat
            // walked walkway lips), and its 128u destination should
            // be hidden from the enemy's eyes. First cover wins; a
            // floor-safe heading with no cover is kept as fallback,
            // and with neither we stand and fight.
            want = vectoyaw (self.origin - e.origin);
            cfound = 0;
            ck = 0;
            while (ck < 5 && cfound < 2)
            {
                if (ck == 0)        cy = want;
                else if (ck == 1)   cy = want + 55;
                else if (ck == 2)   cy = want - 55;
                else if (ck == 3)   cy = want + 110;
                else                cy = want - 110;
                if (!Argus_MoveHazard (cy, 48) && !Argus_MoveHazard (cy, 90))
                {
                    if (cfound < 1)
                    {
                        self.ar_coveryaw = cy;  // safe fallback
                        cfound = 1;
                    }
                    makevectors ('0 0 0' + cy * '0 1 0');
                    cvr = self.origin + v_forward * 128 + '0 0 22';
                    traceline (cvr, e.origin + '0 0 22', TRUE, self);
                    if (trace_fraction < 1)
                    {
                        self.ar_coveryaw = cy;  // real cover
                        cfound = 2;
                    }
                }
                ck = ck + 1;
            }
            if (cfound == 0)
                self.ar_retreating = 0;         // cornered: fight
            self.ar_covertime = time + 1.2;
        }
        if (self.ar_retreating)
            self.ar_moveyaw = self.ar_coveryaw;
    }

    // A RETREAT state was tried here twice (2026-08-18, "address the
    // new"): back away at 200-550u while shooting when under 30 hp
    // with no armour. Reverted both times: the close-range version
    // put Reap's own rockets in his feet (finished minus two), and
    // the ranged version backed bots blind over walkway lips (lava
    // 3 -> 7; the combat hazard fallback is itself "back off", so a
    // retreating bot on a walkway has no safe answer). A real
    // retreat needs positioning-aware escape headings â€” idea bank,
    // with the fake-retreat/corner-ambush state machine. Tapes:
    // ab_dm4_retreat.log, ab_dm4_retreat2.log.

    // never strafe or chase into lava: flip the strafe first, fall back
    // to backing off; the physics brink guard catches anything left
    if (Argus_MoveHazard (self.ar_moveyaw, 48))
    {
        self.ar_strafedir = 0 - self.ar_strafedir;
        self.ar_strafetime = time + 0.5 + random () * 0.5;
        self.ar_moveyaw = vectoyaw (to) + 80 * self.ar_strafedir;
        if (Argus_MoveHazard (self.ar_moveyaw, 48))
            self.ar_moveyaw = vectoyaw ('0 0 0' - to);
    }

    // ---- trigger ----
    // holding button0 matters as much as calling W_Attack: nailgun,
    // super nailgun and lightning damage live in the attack frame
    // chains, which abort unless the fire button is down. Bots never
    // pressed it, so those three weapons produced muzzle flashes and
    // nothing else (the flashes read as a powerup glow from outside).
    if (time > self.ar_react && diff < 12 && diff > -12)
    {
        self.v_angle = vectoangles (aimpt - (self.origin + '0 0 22'));
        self.v_angle_x = 0 - self.v_angle_x;    // QC pitch convention
        self.v_angle_y = self.angles_y;
        self.button0 = 1;
        if (time > self.attack_finished)
        {
            SuperDamageSound ();
            W_Attack ();
        }
    }
    else
        self.button0 = 0;
    return TRUE;
};

// ---------------------------------------------------------------- goals

float(entity it) Argus_GoalOK =
{
    if (it == world)
        return FALSE;
    if (it.solid == SOLID_TRIGGER)
        return TRUE;
    // item clocks (campaign item 4; triple-converged with mre's
    // timer awareness and cortex's CONTROL_MAJOR "be early, not on
    // time"): a picked-up item is not gone, it is a SUB_regen think
    // whose nextthink IS the respawn clock, readable in pure vanilla
    // QC. A pending respawn stays a valid goal while the clock runs;
    // the 20 s goal-abandon timer is the backstop if the timing run
    // goes wrong.
    if (it.solid == SOLID_NOT && it.think == SUB_regen
        && it.nextthink > time && it.nextthink - time < 20)
        return TRUE;
    return FALSE;
};

vector(entity it) Argus_GoalPoint =
{
    return (it.absmin + it.absmax) * 0.5;
};

// ---- utility and GOAP goal layer ----
//
// Goal selection is two stacked ideas. UTILITY: every live item gets a
// worth-to-me-now score (need times personality appetite, discounted
// by travel distance), and the best per class competes for the goal.
// GOAP: the winner is a desired end STATE, and actions carry
// preconditions over a small world-state bitmask; when a precondition
// is false the planner prepends the providing action. The action
// library is small enough that plans are one prepend deep (powerup
// wants ARMED; ammo folds its precondition into scoring, since ammo
// for a gun we lack is worth nothing), so the "plan" lives in two
// fields: the end class and the step class being fetched right now.
// Plans re-run at every pick rather than persisting, which is the
// honest choice in a deathmatch: the world invalidates any queue
// longer than one errand.

float() Argus_WorldState =
{
    local float ws;

    ws = 0;
    if ((self.items & IT_ROCKET_LAUNCHER) && self.ammo_rockets > 0)
        ws = AR_WS_ARMED;
    else if ((self.items & IT_LIGHTNING) && self.ammo_cells > 0)
        ws = AR_WS_ARMED;
    else if ((self.items & IT_SUPER_NAILGUN) && self.ammo_nails > 0)
        ws = AR_WS_ARMED;
    else if ((self.items & IT_GRENADE_LAUNCHER) && self.ammo_rockets > 0)
        ws = AR_WS_ARMED;
    else if ((self.items & IT_SUPER_SHOTGUN) && self.ammo_shells > 0)
        ws = AR_WS_ARMED;   // a real fighting gun: no 1.6x weapon
                            // hunger, no weapon fetch before a quad run

    if (ws & AR_WS_ARMED)
    {
        if (self.items & IT_ROCKET_LAUNCHER)
        {
            if (self.ammo_rockets >= 10)  ws = ws | AR_WS_STOCKED;
        }
        else if (self.items & IT_LIGHTNING)
        {
            if (self.ammo_cells >= 25)    ws = ws | AR_WS_STOCKED;
        }
        else if (self.items & IT_SUPER_NAILGUN)
        {
            if (self.ammo_nails >= 40)    ws = ws | AR_WS_STOCKED;
        }
        else if (self.items & IT_GRENADE_LAUNCHER)
        {
            if (self.ammo_rockets >= 6)   ws = ws | AR_WS_STOCKED;
        }
        else
        {
            if (self.ammo_shells >= 15)   ws = ws | AR_WS_STOCKED;
        }
    }
    if (self.health >= 75)
        ws = ws | AR_WS_HEALTHY;
    if (self.armortype * self.armorvalue >= 25)
        ws = ws | AR_WS_ARMORED;
    return ws;
};

float(entity it) Argus_ItemClass =
{
    local string c;

    c = it.classname;
    if (c == "weapon_supershotgun" || c == "weapon_nailgun"
        || c == "weapon_supernailgun" || c == "weapon_grenadelauncher"
        || c == "weapon_rocketlauncher" || c == "weapon_lightning")
        return AR_C_WEAPON;
    if (c == "item_shells" || c == "item_spikes"
        || c == "item_rockets" || c == "item_cells")
        return AR_C_AMMO;
    if (c == "item_health")
        return AR_C_HEALTH;
    if (c == "item_armor1" || c == "item_armor2" || c == "item_armorInv")
        return AR_C_ARMOR;
    if (c == "item_artifact_super_damage"
        || c == "item_artifact_invulnerability"
        || c == "item_artifact_invisibility"
        || c == "item_artifact_envirosuit")
        return AR_C_POWER;
    return AR_C_ANY;
};

// raw worth of the item to this bot right now, before distance and
// personality. Zero means "of no use" and drops it from scoring
// entirely: ammo for a gun we lack, armour weaker than what we wear,
// a health box we cannot absorb.
float(entity it, float cls) Argus_ItemValue =
{
    local float v, vf;
    local string c;

    c = it.classname;
    if (cls == AR_C_WEAPON)
    {
        if (c == "weapon_rocketlauncher")
        {
            if (self.items & IT_ROCKET_LAUNCHER)
            {
                // weapon control (Shane's review): an owned RL is
                // still worth a loop â€” the pickup refills rockets
                // and every visit is one the enemy never gets
                v = 10 + (15 - self.ammo_rockets) * 1.5;
                if (v < 10)  v = 10;
                return v;
            }
            return 70;
        }
        if (c == "weapon_lightning")
        {
            if (self.items & IT_LIGHTNING)
            {
                v = 10 + (40 - self.ammo_cells) * 0.5;
                if (v < 10)  v = 10;
                return v;
            }
            return 62;
        }
        if (c == "weapon_supernailgun")
        {
            if (self.items & IT_SUPER_NAILGUN)    return 8;
            return 40;
        }
        if (c == "weapon_grenadelauncher")
        {
            if (self.items & IT_GRENADE_LAUNCHER) return 8;
            return 34;
        }
        if (c == "weapon_supershotgun")
        {
            if (self.items & IT_SUPER_SHOTGUN)    return 8;
            return 24;
        }
        if (self.items & IT_NAILGUN)              return 8;
        return 18;
    }
    if (cls == AR_C_AMMO)
    {
        if (c == "item_rockets")
        {
            if (!(self.items & (IT_ROCKET_LAUNCHER | IT_GRENADE_LAUNCHER)))
                return 0;
            if (self.ammo_rockets >= 15)  return 0;
            return 12 + (15 - self.ammo_rockets) * 2;
        }
        if (c == "item_cells")
        {
            if (!(self.items & IT_LIGHTNING))
                return 0;
            if (self.ammo_cells >= 40)    return 0;
            return 8 + (40 - self.ammo_cells) * 0.8;
        }
        if (c == "item_spikes")
        {
            if (!(self.items & (IT_NAILGUN | IT_SUPER_NAILGUN)))
                return 0;
            if (self.ammo_nails >= 60)    return 0;
            return 6 + (60 - self.ammo_nails) * 0.4;
        }
        if (self.ammo_shells >= 25)       return 0;
        return 4 + (25 - self.ammo_shells) * 0.6;
    }
    if (cls == AR_C_HEALTH)
    {
        if (it.healamount >= 100)
            return 45 + (self.max_health - self.health) * 0.5;
        v = (self.max_health - self.health) * 0.9;
        if (v <= 0)  return 0;
        return v;
    }
    if (cls == AR_C_ARMOR)
    {
        if (c == "item_armorInv")     v = 160;
        else if (c == "item_armor2")  v = 90;
        else                          v = 30;
        v = v - self.armortype * self.armorvalue;
        if (v <= 0)  return 0;
        return v * 0.55;
    }
    if (cls == AR_C_POWER)
    {
        if (c == "item_artifact_super_damage")     return 100;
        if (c == "item_artifact_invulnerability")  return 90;
        if (c == "item_artifact_invisibility")     return 45;
        return 6;
    }
    if (it.touch == BackpackTouch)
    {
        // pack dominance (Shane's review): a dropped pack is worth
        // its contents, not a flat nibble â€” the fat rocket pack by
        // the RL is the map's real prize, and looting your victim
        // is the loop humans run by reflex
        v = 12 + it.ammo_rockets * 0.9 + it.ammo_cells * 0.35
              + it.ammo_nails * 0.08 + it.ammo_shells * 0.12;
        if (it.items & (IT_ROCKET_LAUNCHER | IT_LIGHTNING))
            v = v + 15;
        // a FRESH pack is time-critical loot: the victim is already
        // respawning and running back for it (Shane reclaimed his
        // own rocket pack under the killer's nose while the killer
        // trotted off to a health box). DropBackpack arms SUB_Remove
        // at time + 120, so remaining lifetime is the pack's age
        // with no new fields: +30 tapering to 0 over the first 15 s
        vf = (it.nextthink - time - 105) * 2;
        if (vf > 0)
            v = v + vf;
        if (v > 85)
            v = 85;
        return v;
    }
    return 22;      // oddments: mixed loot, always tempting
};

string(float cls) Argus_ClassWord =
{
    if (cls == AR_C_WEAPON)  return "weapon";
    if (cls == AR_C_AMMO)    return "ammo";
    if (cls == AR_C_HEALTH)  return "health";
    if (cls == AR_C_ARMOR)   return "armor";
    if (cls == AR_C_POWER)   return "powerup";
    return "loot";
};

void() Argus_PickGoal =
{
    local entity e, b, pick, near;
    local entity bw, ba, bh, br, bp, bo;
    local float sw, sa, sh, sr, sp, so;
    local vector gp, d;
    local float dist, neard, shelf, cls, v, sc, ws, u, bu, final;

    bw = world;  ba = world;  bh = world;
    br = world;  bp = world;  bo = world;
    sw = 0;  sa = 0;  sh = 0;  sr = 0;  sp = 0;  so = 0;
    near = world;
    neard = 99999;

    e = nextent (world);
    while (e != world)
    {
        if ((e.flags & FL_ITEM)
            && (e.solid == SOLID_TRIGGER
                || (e.solid == SOLID_NOT && e.think == SUB_regen
                    && e.nextthink > time)))
        {
            cls = Argus_ItemClass (e);
            // failed goals rest on a shelf; powerups rest longer,
            // because their scores pull from across the map and the
            // powerups used to sit on a 20 s shelf that bots tithed
            // three times a minute when the dm4 quad was unroutable;
            // RJ links now exist, but a failed blast still needs rest
            shelf = 20;
            if (cls == AR_C_POWER)
                shelf = 45;
            // ar_failtime is 0 until the first routefail, and 0 + shelf
            // made time < 20 read as "recently failed": EVERY item on
            // the map was shelved for the first 20 s of EVERY match
            // (45 s for powerups), so early bots were goalless
            // wanderers. Latent since the GOAP build; caught when
            // Shane raced a bot to the RL 15 s into a fresh server
            // and it showed no interest (first goal event in every
            // lab tape sits at t 19.8, the shelf expiry, exactly)
            if (e.ar_failtime && time < e.ar_failtime + shelf)
            {
                // routefailed recently, for anyone: leave it shelved
            }
            else if (!(e.ar_claimer == self && time < e.ar_claimtime + shelf))
            {
                gp = Argus_GoalPoint (e);
                d = gp - self.origin;
                d_z = d_z * 2;
                dist = vlen (d);
                if (dist < neard && e.solid == SOLID_TRIGGER)
                {
                    near = e;       // value-blind fallback target
                    neard = dist;   // (live items only: patrolling to
                                    // an empty spawn point looks broken)
                }
                v = Argus_ItemValue (e, cls);
                // the item-clock gate: chase a pending respawn only
                // when we would arrive at most ~3 s before it pops -
                // a timing run, not a camp. dist * 0.0036 is travel
                // time at a conservative 280 u/s. Clocks apply only
                // to items WORTH timing (weapons, armour, powerups,
                // the mega): the first clock ladder had bots orbiting
                // empty SHELL spawns on the dm4 pit floor at the lava
                // boundary - pennies of value for real exposure
                // (hazard x30 at the spawn cells, world deaths above
                // band). Humans do not time shell boxes either.
                if (e.solid == SOLID_NOT)
                {
                    if (cls != AR_C_WEAPON && cls != AR_C_ARMOR
                        && cls != AR_C_POWER
                        && !(cls == AR_C_HEALTH && e.healamount >= 100))
                        v = 0;
                    else if (e.nextthink - time > dist * 0.0036 + 10)
                        v = 0;
                    else if (e.nextthink - time > dist * 0.0036 + 3)
                        // pre-positioning (campaign item 4, cortex
                        // CONTROL_MAJOR "be early, not on time";
                        // Shane's circuits review x2): a major coming
                        // up inside 10 s is worth walking to EARLY -
                        // discounted, so anything live still outranks
                        // a camp - and the mode-1 loiter below orbits
                        // the spawn until it pops
                        v = v * 0.55;
                }
                if (v > 0)
                {
                    // control circuit (2026-08-20, Shane's camera
                    // review: "they stay in the same area they spawn
                    // in... seasoned players run circuits"): the
                    // shared distance curve throttled every major to
                    // irrelevance past ~800u - a quad at 2400u scored
                    // 12, losing to any local health box, so bots
                    // grazed whatever was near. Majors (value 40+:
                    // RL/LG unowned, RA/YA fresh, mega, powerups, fat
                    // packs, big heals for the badly hurt) read
                    // distance at 0.4x so they pull from across the
                    // map; minor items keep the tight curve and stay
                    // local errands. The circuit itself emerges: item
                    // clocks time the arrivals, the claim shelf and
                    // packmate discount spread the roster across
                    // control points, denial pressure and gunfire
                    // investigation turn the commute into contact.
                    if (v >= 40)
                        sc = v * 320 / (dist * 0.4 + 160);
                    else
                        sc = v * 320 / (dist + 160);
                    // spread the pack: an item a packmate is already
                    // running at is worth less to us
                    b = argus_bots;
                    while (b != world)
                    {
                        if (b != self && b.health > 0 && b.ar_goal == e)
                            sc = sc * 0.6;
                        b = b.ar_chain;
                    }
                    // item denial (OPM slice C): an opponent standing
                    // near this item makes taking it sweeter
                    b = find (world, classname, "player");
                    while (b != world)
                    {
                        if (b != self && b.health > 0 && !b.cam_active
                            && vlen (b.origin - e.origin) < 300)
                            sc = sc + 12;
                        b = find (b, classname, "player");
                    }
                    if (cls == AR_C_WEAPON)
                    {
                        if (sc > sw)  { sw = sc;  bw = e; }
                    }
                    else if (cls == AR_C_AMMO)
                    {
                        if (sc > sa)  { sa = sc;  ba = e; }
                    }
                    else if (cls == AR_C_HEALTH)
                    {
                        if (sc > sh)  { sh = sc;  bh = e; }
                    }
                    else if (cls == AR_C_ARMOR)
                    {
                        if (sc > sr)  { sr = sc;  br = e; }
                    }
                    else if (cls == AR_C_POWER)
                    {
                        if (sc > sp)  { sp = sc;  bp = e; }
                    }
                    else
                    {
                        if (sc > so)  { so = sc;  bo = e; }
                    }
                }
            }
        }
        e = nextent (e);
    }

    // ---- utility over end states, personality-weighted, with the
    // unsatisfied world-state atom raising the call of its provider ----
    ws = Argus_WorldState ();
    bu = 0;
    final = 0;
    pick = world;

    u = sw * self.ar_wweap;
    if (!(ws & AR_WS_ARMED))
        u = u * 1.6;
    if (bw != world && u > bu)  { bu = u;  final = AR_C_WEAPON;  pick = bw; }

    u = sa * self.ar_wweap;
    if ((ws & AR_WS_ARMED) && !(ws & AR_WS_STOCKED))
        u = u * 1.3;
    if (ba != world && u > bu)  { bu = u;  final = AR_C_AMMO;    pick = ba; }

    u = sh * self.ar_wheal;
    if (!(ws & AR_WS_HEALTHY))
        u = u * 1.4;
    if (bh != world && u > bu)  { bu = u;  final = AR_C_HEALTH;  pick = bh; }

    u = sr * self.ar_warmor;
    if (!(ws & AR_WS_ARMORED))
        u = u * 1.2;
    if (br != world && u > bu)  { bu = u;  final = AR_C_ARMOR;   pick = br; }

    u = sp * self.ar_wpow;
    if (bp != world && u > bu)  { bu = u;  final = AR_C_POWER;   pick = bp; }

    if (bo != world && so > bu) { bu = so; final = AR_C_ANY;     pick = bo; }

    // nothing scored (stocked, healthy, everything shelved): patrol to
    // the nearest live item anyway; a still bot is a dead bot
    if (pick == world)
    {
        final = AR_C_ANY;
        pick = near;
    }

    // island discipline (2026-08-20, the dm3 corridor ladder): two
    // straight routefails from one spot mean the wide menu is not
    // routable from here - shop the NEAREST live item until a route
    // completes and clears the streak. Without this, the circuit
    // pull kept offering far majors on other islands, every pick
    // failed, and the four-fail trapped rule - written for pits -
    // suicided bots standing on a 93-node island (trapped 39, frags
    // -23 in ab_dm3_corridor1). A bot truly in a pit fails the near
    // item too and still reaches the trapped exit.
    if (self.ar_failstreak >= 2 && near != world)
    {
        final = AR_C_ANY;
        pick = near;
    }

    // ---- GOAP: prepend unmet preconditions ----
    // A powerup run has ARMED as a precondition: nobody walks to the
    // quad holding a shotgun. The plan keeps the powerup as its end
    // state and fetches the gun first.
    self.ar_planfinal = final;
    self.ar_planwant = final;
    if (final == AR_C_POWER && !(ws & AR_WS_ARMED) && bw != world)
    {
        self.ar_planwant = AR_C_WEAPON;
        pick = bw;
    }

    self.ar_goal = pick;
    self.ar_goalstart = time;
    self.ar_node = world;
    self.ar_pending = 0;
    self.ar_mode = 0;

    if (pick != world)
    {
        if (self.ar_planwant != self.ar_planfinal)
        {
            dprint ("ARGEVT ");
            dprint (self.netname);
            dprint (" plan ");
            dprint (Argus_ClassWord (self.ar_planfinal));
            dprint (" via ");
            dprint (Argus_ClassWord (self.ar_planwant));
            dprint ("\n");
        }
        dprint ("ARGEVT ");
        dprint (self.netname);
        dprint (" goal ");
        dprint (pick.classname);
        dprint ("\n");

        gp = Argus_GoalPoint (pick);
        if (vlen (gp - self.origin) < 300)
        {
            traceline (self.origin + '0 0 22', gp, TRUE, self);
            if (trace_fraction == 1 && Argus_SafeLine (gp))
            {
                self.ar_mode = 1;
                return;
            }
        }
        self.ar_pending = 1;
    }
};

void() Argus_AI =
{
    local vector gp, tp, to;
    local float want, diff, turn, havetarget, fighting;
    local entity oldnode, nx, dr;

    self.ar_liftwait = 0;       // re-earned every frame by the ride branch

    if (self.ar_mode == 0 && !self.ar_pending && self.ar_node != world)
        self.ar_mode = 2;

    // every live frame, like PlayerPostThink: on the 0.2 s tick a bot
    // could deal quad damage, drop a quad, and draw quad obituaries
    // for up to 200 ms after expiry
    Argus_CheckPowerups ();

    // ---- periodic goal maintenance ----
    if (time > self.ar_nextai)
    {
        self.ar_nextai = time + 0.2;

        // introductions, once the host has had time to connect
        if (!self.ar_greeted && time > 5)
        {
            self.ar_greeted = 1;
            Argus_Chat (0);
        }

        // patrol stance: hold the best mid-range weapon between fights
        if (self.ar_enemy == world)
            Argus_SelectWeapon (400);

        if (self.ar_routefail)
        {
            self.ar_routefail = 0;
            if (Argus_GoalOK (self.ar_goal))
            {
                self.ar_goal.ar_claimer = self;
                self.ar_goal.ar_claimtime = time;
                // a REPEAT failure from the same AREA is a verdict
                // about this bot's position, not the goal's topology:
                // skip the global shelf, or one pit-trapped bot fails
                // through the whole menu and starves every other bot.
                // Area, not node: the pit floors carry 2-8 nodes and a
                // wandering trapped bot alternates between them, which
                // reset a same-node streak every fail (trapped never
                // fired across a whole stormy ladder match)
                if (self.ar_laststart != world
                    && self.ar_lastfailnode != world
                    && vlen (self.ar_laststart.origin
                             - self.ar_lastfailnode.origin) < 220)
                    self.ar_failstreak = self.ar_failstreak + 1;
                else
                {
                    self.ar_failstreak = 1;
                    self.ar_goal.ar_failtime = time;
                }
                self.ar_lastfailnode = self.ar_laststart;
            }
            self.ar_goal = world;

            // four straight failures from one node with nobody to fight:
            // trapped (the pit floors are survivable but exitless
            // without gear). Take the deathmatch exit and respawn fresh,
            // like any human player stuck in a pit would
            if (self.ar_failstreak >= 4 && self.ar_enemy == world
                && self.super_damage_finished < time)
            {
                self.ar_failstreak = 0;
                Argus_Event ("trapped");
                T_Damage (self, self, self, 400);
                return;
            }
        }

        if (!Argus_GoalOK (self.ar_goal))
        {
            // a goal that stopped being an item under our feet was
            // eaten, almost always by us: the touch beats the arrival
            // radius, so this is where completed errands are counted
            // (utility goals are all consumable; the arrival counter
            // below only ever fires for patrol targets that stay put)
            if (self.ar_goal != world
                && vlen (Argus_GoalPoint (self.ar_goal) - self.origin) < 64)
                self.ar_goals = self.ar_goals + 1;
            Argus_PickGoal ();
        }
        else if (time > self.ar_goalstart + 20)
        {
            self.ar_goal.ar_claimer = self;
            self.ar_goal.ar_claimtime = time;
            self.ar_goal = world;
            Argus_Event ("abandon");
            Argus_PickGoal ();
        }

        if (self.ar_pending && Argus_GoalOK (self.ar_goal))
        {
            gp = Argus_GoalPoint (self.ar_goal);
            nx = Argus_NearestNode (self.origin);
            // shared route cache first (Omicron review): a fresh
            // flood to the same goal node is adopted for free, no
            // an_busy contention, no search frames
            if (Argus_Route_Adopt (self, nx, Argus_NearestNode (gp)))
                self.ar_laststart = nx;
            else if (Argus_Route_Start (self, nx, Argus_NearestNode (gp)))
            {
                self.ar_laststart = nx;
                self.ar_pending = 0;
            }
        }
    }

    // ---- combat overrides steering when an enemy is engaged ----
    fighting = Argus_Combat ();

    // investigation (v3.41, the second half of the hearing slice):
    // fresh gunfire PULLS an unengaged bot toward it instead of just
    // turning its head. The "getting dumber" feel was traffic
    // dilution â€” corridor mode and doors opened the whole map, bots
    // commute far-flung errands, and a human blazing away drew only
    // glances. Bounded 700u, hazard-guarded, route-preserving (the
    // node target survives; steering just borrows the combat
    // override for the moment), and it decays with the sound.
    if (!fighting && ar_opm_ears && self.ar_enemy == world
        && self.ar_sndtime > 0 && time < self.ar_sndtime + 3)
    {
        // weapon-sound classification (mre Predator): how far a bot
        // will go to investigate depends on WHAT it heard and how
        // much it can afford. Heavy gunfire (RL/LG) heard on a thin
        // stack keeps its distance; a healthy bot hunts the big
        // fight harder than small-arms chatter.
        turn = 700;
        if (self.ar_sndweap == IT_ROCKET_LAUNCHER
            || self.ar_sndweap == IT_LIGHTNING)
        {
            if (self.health + self.armorvalue * self.armortype < 60)
                turn = 350;
            else if (self.health > 80)
                turn = 850;
        }
        to = self.ar_sndpos - self.origin;
        to_z = 0;
        if (vlen (to) > 80 && vlen (to) < turn)
        {
            want = vectoyaw (to);
            if (!Argus_MoveHazard (want, 48))
            {
                diff = want - self.ar_moveyaw;
                while (diff > 180)  diff = diff - 360;
                while (diff < -180) diff = diff + 360;
                turn = AR_TURNRATE * frametime;
                if (diff > turn)        diff = turn;
                else if (diff < -turn)  diff = -turn;
                self.ar_moveyaw = self.ar_moveyaw + diff;
                self.angles_y = self.ar_moveyaw;
                fighting = 1;       // borrow the combat override:
                                    // goal steering stands down
            }
        }
    }

    havetarget = 0;
    tp = self.origin;
    if (Argus_GoalOK (self.ar_goal))
    {
        gp = Argus_GoalPoint (self.ar_goal);

        if (self.ar_mode == 2 && vlen (gp - self.origin) < 200)
        {
            traceline (self.origin + '0 0 22', gp, TRUE, self);
            if (trace_fraction == 1 && Argus_SafeLine (gp))
            {
                // the SafeLine gate keeps the routed descent: a goal
                // visible across a brink stays on its drop links
                // instead of diving the lip
                self.ar_mode = 1;
                self.ar_node = world;
            }
        }

        if (self.ar_mode == 2 && self.ar_node != world)
        {
            tp = self.ar_node.origin;
            to = tp - self.origin;
            to_z = 0;

            // train ride (dm2 slice 4): the car patrols on its own
            // clock â€” no trigger to press. This block only decides
            // HOLDING (the liftwait friction-hold); the ordinary
            // steering below does all the walking, so boarding and
            // stepping off are just walks that happen when the hold
            // releases. 12 s give-up covers two patrol legs of dm2's
            // longest shuttle.
            if (self.ar_hoptrain)
            {
                if (time > self.ar_liftstart + 15)
                {
                    self.ar_hoptrain = 0;
                    if (Argus_GoalOK (self.ar_goal))
                    {
                        self.ar_goal.ar_claimer = self;
                        self.ar_goal.ar_claimtime = time;
                        self.ar_goal.ar_failtime = time;
                    }
                    self.ar_goal = world;
                    self.ar_node = world;
                    self.ar_pending = 0;
                    self.ar_mode = 0;
                    // the ride never came: cool THIS PAD, not just
                    // the goal - the next pick otherwise routes back
                    // through the same crossing and chains waits
                    self.ar_padcoolpos = self.origin;
                    self.ar_padcooltime = time + 25;
                    Argus_Event ("abandon");
                }
                else
                {
                    turn = 99999;
                    nx = world;
                    dr = find (world, classname, "train");
                    while (dr != world)
                    {
                        gp = (dr.absmin + dr.absmax) * 0.5;
                        to = gp - self.origin;
                        if (vlen (to) < turn)
                        {
                            turn = vlen (to);
                            nx = dr;
                        }
                        dr = find (dr, classname, "train");
                    }
                    if (nx != world)
                    {
                        if (self.groundentity == nx)
                        {
                            // hop-success accounting (Shane's self-
                            // testing review): the wait storm at the
                            // west pad ran three tapes with a 0%
                            // boarding rate and no metric said so
                            if (!self.ar_boarded)
                            {
                                self.ar_boarded = 1;
                                Argus_Event ("board");
                            }
                            // riding = STANDING ON THE CAR, read
                            // straight off groundentity - the engine
                            // maintains it for STEP bots (proven by
                            // probe: gnd=train/plat/door while
                            // aboard). The old bbox-overlap test
                            // false-positived on a deck-stander with
                            // the car passing beside it. NOTE the
                            // runtime classnames: func_plat renames
                            // to "plat" and func_train to "train" at
                            // spawn (plats.qc 205/360), the same trap
                            // that silenced the v3.33 door handler -
                            // the v3.46/47 finders searched the
                            // func_* names and never matched, so the
                            // ride holds never actually ran.
                            // riding IS progress: the give-up clock
                            // only counts pad-waiting (the first
                            // reland ladder lost riders mid-bridge
                            // to the timeout â€” abandons 23/35 with
                            // zero completed crossings)
                            self.ar_liftstart = time;
                            // ride it STANDING STILL: the friction
                            // hold alone needs half a second the 94u
                            // slab does not give at run speed â€”
                            // Romero sprinted the length of the car
                            // and off its far edge into the bridge
                            // gap 156 times in one tape (shane v345)
                            to = tp - self.origin;
                            to_z = 0;
                            if (vlen (to) > 80)
                            {
                                self.ar_liftwait = 1;
                                self.velocity_x = 0;
                                self.velocity_y = 0;
                            }
                        }
                        else
                        {
                            gp = self.origin;
                            if (gp_x < nx.absmin_x)  gp_x = nx.absmin_x;
                            if (gp_x > nx.absmax_x)  gp_x = nx.absmax_x;
                            if (gp_y < nx.absmin_y)  gp_y = nx.absmin_y;
                            if (gp_y > nx.absmax_y)  gp_y = nx.absmax_y;
                            gp_z = self.origin_z;
                            to = gp - self.origin;
                            to_z = 0;
                            // board within 120, not 96 or 48: the t5
                            // dock parks the car's near edge 71u from
                            // the pad node (the 48 gate never opened,
                            // five 13-17 s statues in the v352 tape),
                            // and the WEST dock parks it at 109u (the
                            // 96 gate never opened there - six 13-19 s
                            // statues in the v363 tape, zero west-east
                            // crossings in 588 s; car min corner sits
                            // AT path_corner t5 '1472 -1064', pad node
                            // at '1363 -1038'). The walk to the slab
                            // stays hazard-guarded, so a missed board
                            // deflects at the deck edge and re-parks
                            if (vlen (to) < 120)
                            {
                                // car edge a step away: BOARD it.
                                // Steer at the slab centre, never at
                                // the far pad â€” free-running at a
                                // target 320u across the void is what
                                // walked riders off the plank
                                // whenever the hold did not bite
                                tp = (nx.absmin + nx.absmax) * 0.5;
                                tp_z = self.origin_z;
                            }
                            else if (self.ar_enemy == world)
                            {
                                // car away: park at the pad and bleed
                                // speed fast; a fresh hold at 340 u/s
                                // slides 40u+ on friction alone.
                                // NEVER park while fighting: the
                                // ar_liftwait hold is physics-level
                                // and overrode even combat movement -
                                // Shane rocketed a bot that stood at
                                // this pad from 81 hp to dead without
                                // it taking a step (v363 tape, 19 s).
                                // With no hold, combat strafe/dodge/
                                // retreat drive; the wait resumes
                                // when the fight ends.
                                self.ar_liftwait = 1;
                                self.velocity_x = self.velocity_x * 0.5;
                                self.velocity_y = self.velocity_y * 0.5;
                            }
                        }
                    }
                    to = tp - self.origin;      // restore for the chain
                    to_z = 0;
                }
            }

            // 200, not 56: the WAIT_NODE pads sit OUTSIDE the swept
            // column now, 100-160u horizontal from the exit node
            // overhead. At 56 the whole wait-and-give-up block never
            // engaged from the new pads, and with the stall detector
            // suppressed for lift hops the result was an unbounded
            // statue (82 s at the *34 base, ab_dm2_waitnode2).
            if (self.ar_hoplift && vlen (to) < 200 && tp_z > self.origin_z + 40)
            {
                // lift hop, standing over the boarding pad with the
                // exit node overhead: park and let the plat do the
                // vertical part (relanded after the 2026-08-18
                // forensics exonerated it â€” bisect1 failed without
                // this code present)
                if (time > self.ar_liftstart + 8)
                {
                    // the lift never came: shelve the errand globally
                    // AND cool this pad (the *34 32 s episode: three
                    // chained give-ups because every re-shop routed
                    // straight back through the same gateway lift)
                    self.ar_hoplift = 0;
                    if (Argus_GoalOK (self.ar_goal))
                    {
                        self.ar_goal.ar_claimer = self;
                        self.ar_goal.ar_claimtime = time;
                        self.ar_goal.ar_failtime = time;
                    }
                    self.ar_goal = world;
                    self.ar_node = world;
                    self.ar_pending = 0;
                    self.ar_mode = 0;
                    self.ar_padcoolpos = self.origin;
                    self.ar_padcooltime = time + 25;
                    Argus_Event ("abandon");
                }
                else
                {
                    // plat-state-aware wait (Shane's report: a bot
                    // stuck UNDER the raised slab, pinning it up).
                    // plat_center_touch postpones the descent on
                    // EVERY touch and touches fire on movement, so a
                    // bot fidgeting in the shaft volume keeps the
                    // plat up forever; one parked INSIDE the
                    // footprint blocks the descent with its head
                    // (crush-reverse loop) instead. Raised slab and
                    // we are beneath it: step out from under. Raised
                    // and clear: stand utterly still so the 1 s
                    // descent delay can expire. Resting: walk ONTO
                    // the slab - the approach itself summons the
                    // ride with us aboard.
                    turn = 99999;
                    nx = world;
                    dr = find (world, classname, "plat");
                    while (dr != world)
                    {
                        gp = (dr.absmin + dr.absmax) * 0.5;
                        gp_z = self.origin_z;
                        if (vlen (gp - self.origin) < turn)
                        {
                            turn = vlen (gp - self.origin);
                            nx = dr;
                        }
                        dr = find (dr, classname, "plat");
                    }
                    if (nx == world || turn > 320)
                    {
                        // no plat near: park - unless fighting (the
                        // hold overrides combat movement; a parked
                        // bot under fire is a free frag, v363 tape)
                        if (self.ar_enemy == world)
                            self.ar_liftwait = 1;
                    }
                    else if (self.groundentity == nx)
                    {
                        if (!self.ar_boarded)
                        {
                            self.ar_boarded = 1;
                            Argus_Event ("board");
                        }
                        if (nx.state != STATE_BOTTOM)
                        {
                            // aboard and moving: ride standing still
                            self.ar_liftwait = 1;
                            self.velocity_x = 0;
                            self.velocity_y = 0;
                        }
                        else
                        {
                            // aboard but the slab is SEATED: keep
                            // walking at its centre. Quake only fires
                            // touch triggers on movement, so a bot
                            // standing utterly still on a resting
                            // plat never summons its own ride - the
                            // 17 s statue ON the *34 slab in the
                            // v352 review tape
                            tp = (nx.absmin + nx.absmax) * 0.5;
                            tp_z = self.origin_z;
                        }
                    }
                    else if (nx.state != STATE_BOTTOM)
                    {
                        // the slab is absent or moving. The danger
                        // zone is the whole SWEPT COLUMN (footprint
                        // xy), not the slab's current z: dm2's *31
                        // rests at TOP and its descending 158u slab
                        // swept through a bot frozen at the pad -
                        // plat_crush reversed it off his head every
                        // cycle and state BOTTOM never came (LIFTDBG
                        // probe: TOP -> DOWN -> reverse at pz ~100 ->
                        // TOP, 95 samples, not one seat). The waiting
                        // bot was the blocker. Clear the column, then
                        // hold utterly still so it can seat.
                        if (self.origin_x > nx.absmin_x - 4
                            && self.origin_x < nx.absmax_x + 4
                            && self.origin_y > nx.absmin_y - 4
                            && self.origin_y < nx.absmax_y + 4)
                        {
                            // clear the column by a WALKABLE heading:
                            // radial, then +-90 off it (the naive
                            // radial wedged bots against the *31
                            // ledge wall, and the stall churn that
                            // followed reset the route every 3 s -
                            // the platseat1 storm). If every way is
                            // blocked, stand still where we are:
                            // stillness fires no touches, and only
                            // the true swept column blocks a seat.
                            gp = (nx.absmin + nx.absmax) * 0.5;
                            to = self.origin - gp;
                            to_z = 0;
                            if (vlen (to) < 8)
                                to = '96 0 0';
                            turn = vectoyaw (to);
                            if (Argus_MoveHazard (turn, 48))
                            {
                                turn = turn + 90;
                                if (Argus_MoveHazard (turn, 48))
                                    turn = turn - 180;
                            }
                            if (Argus_MoveHazard (turn, 48))
                            {
                                if (self.ar_enemy == world)
                                {
                                    self.ar_liftwait = 1;
                                    self.velocity_x = 0;
                                    self.velocity_y = 0;
                                }
                            }
                            else
                            {
                                makevectors ('0 0 0' + turn * '0 1 0');
                                tp = self.origin + v_forward * 96;
                            }
                        }
                        else if (self.ar_enemy == world)
                        {
                            // outside the footprint, slab moving:
                            // hold still so it can seat - but never
                            // while fighting (see the train pad note)
                            self.ar_liftwait = 1;
                            self.velocity_x = 0;
                            self.velocity_y = 0;
                        }
                    }
                    else
                    {
                        // seated: walking into the footprint IS
                        // boarding - steer at the slab centre
                        tp = (nx.absmin + nx.absmax) * 0.5;
                        tp_z = self.origin_z;
                    }
                    to = tp - self.origin;
                    to_z = 0;
                }
            }
            else if (vlen (to) > 340 && !self.ar_hoptrain)
            {
                // displaced beyond any legal hop length â€” a fight (or
                // knockback, or a teleporter) carried us off the
                // route, and resuming the beeline from here marches
                // through whatever wall is in the way. Re-plan.
                // Exempt the train hop: its far pad legitimately sits
                // 320-430u out for the whole wait, and the guard was
                // re-planning every tick of it (the route-2 spam in
                // the v345 tape).
                self.ar_node = world;
                self.ar_pending = 1;
                self.ar_mode = 0;
            }
            else if (vlen (to) < 48
                     && (fabs (tp_z - self.origin_z) < 48
                         || (self.origin_z - tp_z > 0 && self.origin_z - tp_z < 220)))
            {
                // the vertical tolerance also accepts standing on the
                // lip ABOVE a drop-link landing: the z gap can never
                // close from up here, and demanding it left bots
                // dithering on ledge edges over their own next node
                // (the mega-room stair lip and the old walkway spot)
                oldnode = self.ar_node;
                self.ar_node = Argus_GetNext (self.ar_node, self);
                self.ar_hopjump = 0;
                self.ar_hoprj = 0;
                self.ar_hoplift = 0;
                self.ar_hopswim = 0;
                self.ar_hoptrain = 0;
                self.ar_hopdoor = 0;
                if (self.ar_node == world)
                    self.ar_mode = 1;
                else if (Argus_LinkIsJump (oldnode, self.ar_node))
                    self.ar_hopjump = 1;
                else if (Argus_LinkIsRocket (oldnode, self.ar_node))
                    self.ar_hoprj = 1;
                else if (Argus_LinkIsLift (oldnode, self.ar_node))
                {
                    if (time < self.ar_padcooltime
                        && vlen (self.origin - self.ar_padcoolpos) < 250)
                    {
                        // pad cooldown (the *34 32 s episode, v367b
                        // tape): a give-up here moments ago means the
                        // mover is pinned - Shane camping the deck
                        // above kept the slab's descent postponed.
                        // Every re-shop routed back through the same
                        // gateway lift and chained statues. Shelve
                        // this goal from the WALK and shop on.
                        if (Argus_GoalOK (self.ar_goal))
                        {
                            self.ar_goal.ar_claimer = self;
                            self.ar_goal.ar_claimtime = time;
                            self.ar_goal.ar_failtime = time;
                        }
                        self.ar_goal = world;
                        self.ar_node = world;
                        self.ar_pending = 0;
                        self.ar_mode = 0;
                        Argus_Event ("abandon");
                    }
                    else
                    {
                        self.ar_hoplift = 1;
                        self.ar_liftstart = time;
                        self.ar_boarded = 0;
                        Argus_Event ("lift");
                    }
                }
                else if (Argus_LinkIsSwim (oldnode, self.ar_node))
                    self.ar_hopswim = 1;
                else if (Argus_LinkIsTrain (oldnode, self.ar_node))
                {
                    if (time < self.ar_padcooltime
                        && vlen (self.origin - self.ar_padcoolpos) < 250)
                    {
                        // same cooldown for train pads (the west-dock
                        // serial re-queue residual, v363)
                        if (Argus_GoalOK (self.ar_goal))
                        {
                            self.ar_goal.ar_claimer = self;
                            self.ar_goal.ar_claimtime = time;
                            self.ar_goal.ar_failtime = time;
                        }
                        self.ar_goal = world;
                        self.ar_node = world;
                        self.ar_pending = 0;
                        self.ar_mode = 0;
                        Argus_Event ("abandon");
                    }
                    else
                    {
                        self.ar_hoptrain = 1;
                        self.ar_liftstart = time;
                        self.ar_boarded = 0;
                        Argus_Event ("train");
                    }
                }
                else if (Argus_LinkIsDoor (oldnode, self.ar_node))
                    self.ar_hopdoor = 1;
            }
            else if (!self.ar_hopjump && vlen (to) < 112)
            {
                // apex cornering: when the node after this one is
                // visible on the level and the line to it is safe,
                // advance early and cut the corner instead of
                // pivoting on the waypoint (the chronic walkway
                // corner stalls are pivot dithering)
                nx = Argus_GetNext (self.ar_node, self);
                // typed hops must go through the arrival gate, which
                // sets their flags: cutting the corner onto a rocket,
                // lift or swim link left the bot walking at a node it
                // cannot walk to (Shane's correctness list â€” swim
                // lips sit inside the 48u z window)
                if (nx != world
                    && !Argus_LinkIsJump (self.ar_node, nx)
                    && !Argus_LinkIsRocket (self.ar_node, nx)
                    && !Argus_LinkIsLift (self.ar_node, nx)
                    && !Argus_LinkIsSwim (self.ar_node, nx)
                    && !Argus_LinkIsTrain (self.ar_node, nx)
                    && !Argus_LinkIsDoor (self.ar_node, nx)
                    && fabs (nx.origin_z - self.origin_z) < 48)
                {
                    if (!Argus_MoveHazard (vectoyaw (nx.origin - self.origin), 48))
                    {
                        traceline (self.origin + '0 0 22',
                                   nx.origin + '0 0 8', TRUE, self);
                        if (trace_fraction == 1)
                            self.ar_node = nx;
                    }
                }
            }
            if (self.ar_mode == 2 && self.ar_node != world)
            {
                tp = self.ar_node.origin;
                havetarget = 1;
            }
        }

        if (self.ar_mode == 1)
        {
            tp = gp;
            to = tp - self.origin;
            to_z = 0;
            if (self.ar_goal.solid == SOLID_NOT && vlen (to) < 150
                && fabs (gp_z - self.origin_z) < 72)
            {
                // EARLY at a clocked major: loiter, do not complete.
                // The old arrival path counted a pending item as done,
                // claimed it for 20 s and walked away - right before
                // it popped. Orbit the spawn at ~90u instead: speed
                // stays up (no statue for the freeze gate), the lap
                // crosses the spot as it spawns, and the touch counts
                // the real pickup. Combat still overrides the whole
                // block, and the 20 s goal-abandon timer stays the
                // backstop if the clock was a lie.
                if (vlen (to) < 8)
                    to = '90 0 0';
                if (self.ar_strafedir == 0)
                    self.ar_strafedir = 1;  // never orbit radially
                want = vectoyaw (to);
                if (vlen (to) > 110)
                    want = want + 55 * self.ar_strafedir;
                else if (vlen (to) < 60)
                    want = want + 125 * self.ar_strafedir;
                else
                    want = want + 90 * self.ar_strafedir;
                if (Argus_MoveHazard (want, 48))
                {
                    // wall or brink on the lap: run it the other way
                    self.ar_strafedir = 0 - self.ar_strafedir;
                    want = vectoyaw (to) + 90 * self.ar_strafedir;
                    if (Argus_MoveHazard (want, 48))
                        // BOTH lap directions blocked: this spawn sits
                        // on a lip (dm4's majors are pit-adjacent, and
                        // the fall-through here churned the lava
                        // boundary - world 9, preposition1). Back off
                        // the spawn instead; the camp resumes from a
                        // safer stand-off distance next tick.
                        want = vectoyaw ('0 0 0' - to);
                }
                makevectors ('0 0 0' + want * '0 1 0');
                tp = self.origin + v_forward * 96;
                havetarget = 1;
            }
            else if (vlen (to) < 32 && fabs (gp_z - self.origin_z) < 56)
            {
                self.ar_goals = self.ar_goals + 1;
                self.ar_goal.ar_claimer = self;
                self.ar_goal.ar_claimtime = time;
                self.ar_goal = world;
                self.ar_node = world;
                Argus_PickGoal ();
            }
            else
                havetarget = 1;
        }

        if (!havetarget && Argus_GoalOK (self.ar_goal) && self.ar_mode != 2)
        {
            tp = Argus_GoalPoint (self.ar_goal);
            havetarget = 1;
        }
    }

    // a closed door on the current hop beats combat displacement:
    // fighting used to skip this block and walk the slab (t6).
    if (fighting && self.ar_door != world && self.ar_door.state == STATE_BOTTOM)
        fighting = 0;

    if (fighting)
    {
        // facing and moveyaw already set by combat; jumps for reachability only
        if (havetarget && tp_z > self.origin_z + 24)
        {
            to = tp - self.origin;
            to_z = 0;
            if (vlen (to) < 80 && (self.flags & FL_ONGROUND) && time > self.ar_nextjump)
            {
                self.ar_jump = 1;
                self.ar_nextjump = time + 0.8;
            }
        }
    }
    else if (havetarget)
    {
        want = vectoyaw (tp - self.origin);

        // typed door handling (dm2 slice 2). func_door renames itself
        // "door" at spawn â€” matching "func_door" never fired. Touch-
        // open: walk in. Button-only: detour and hold for STATE_TOP.
        // Shoot plate (*30 / t18) is slice 3; we still walk to it.
        if (self.ar_door == world)
        {
            traceline (self.origin + '0 0 22', tp + '0 0 22', FALSE, self);
            if (trace_fraction < 1 && Argus_IsDoor (trace_ent)
                && (self.ar_hopdoor || vlen (trace_endpos - self.origin) < 240))
                Argus_TakeDoor (trace_ent);
        }
        if (self.ar_door != world)
        {
            if (self.ar_door.state != STATE_BOTTOM)
            {
                self.ar_door = world;       // moving or open: walk on
                self.ar_doorbtn = world;
            }
            else if (time > self.ar_doortime)
            {
                if (Argus_GoalOK (self.ar_goal))
                    self.ar_goal.ar_failtime = time;
                self.ar_door = world;
                self.ar_doorbtn = world;
                havetarget = 0;
            }
            else if (self.ar_door.targetname == "")
            {
                // touch-open: keep walking into the slab
            }
            else if (self.ar_doorbtn != world && self.ar_doorbtn.health > 0)
            {
                gp = (self.ar_doorbtn.absmin + self.ar_doorbtn.absmax) * 0.5;
                to = gp - self.origin;
                to_z = 0;
                want = vectoyaw (to);
                traceline (self.origin + '0 0 22', gp, TRUE, self);
                if ((trace_ent == self.ar_doorbtn || trace_fraction == 1)
                    && vlen (to) < 600)
                {
                    self.ar_liftwait = 1;
                    diff = want - self.angles_y;
                    while (diff > 180)  diff = diff - 360;
                    while (diff < -180) diff = diff + 360;
                    if (diff < 10 && diff > -10 && time > self.attack_finished)
                    {
                        self.v_angle = vectoangles (gp - (self.origin + '0 0 22'));
                        self.v_angle_x = 0 - self.v_angle_x;
                        self.v_angle_y = self.angles_y;
                        self.button0 = 1;
                        W_Attack ();
                        self.button0 = 0;
                    }
                }
            }
            else if (self.ar_doorbtn != world)
            {
                to = (self.ar_doorbtn.absmin + self.ar_doorbtn.absmax) * 0.5
                     - self.origin;
                to_z = 0;
                if (vlen (to) > 40)
                    want = vectoyaw (to);
                else
                {
                    // press by contact. Hold for the slab ONLY when
                    // the door is near enough to walk through as it
                    // opens; at a REMOTE button (t6's lives in the
                    // rockets pocket, 490u from its doors) the hold
                    // froze bots 8 s facing nothing - Shane fought
                    // one standing still there twice. Keep pushing
                    // into the plate instead: contact fires it and
                    // the state release above does the rest. (A cap
                    // on the button SEARCH was tried first and
                    // reverted: shelving every t6 goal re-routed the
                    // whole roster into the plat *34 shaft fight,
                    // hazard x35 at '2495 -992' two runs straight.)
                    gp = (self.ar_door.absmin + self.ar_door.absmax) * 0.5
                         - self.origin;
                    if (vlen (gp) < 320)
                        self.ar_liftwait = 1;
                    else
                        want = vectoyaw (to);
                }
            }
            else
            {
                // button-only and no button in range: shelf
                if (Argus_GoalOK (self.ar_goal))
                    self.ar_goal.ar_failtime = time;
                self.ar_door = world;
                havetarget = 0;
            }
        }

        // direct (unrouted) seeking across a hazard: curve around the
        // brink toward the goal first â€” items sitting just past a pit
        // lip (dm4's big-room RL by the mega) were being abandoned
        // from every pit-side approach â€” and give the goal up only
        // when no side is safe. Routed mode 2 is left alone: its
        // links are walk-verified and its drops land on solid.
        if (self.ar_mode != 2 && Argus_MoveHazard (want, 48))
        {
            want = Argus_HazardSteer (want, 48);
            if (Argus_MoveHazard (want, 48))
                havetarget = 0;
        }
        if (!havetarget)
        {
            // boxed in at the brink: shelve the goal and turn away
            if (Argus_GoalOK (self.ar_goal))
            {
                self.ar_goal.ar_claimer = self;
                self.ar_goal.ar_claimtime = time;
            }
            self.ar_goal = world;
            self.ar_node = world;
            self.ar_pending = 0;
            self.ar_mode = 0;
            self.angles_y = self.angles_y + 150;
            self.ar_moveyaw = self.angles_y;
            Argus_Event ("abandon");
        }
        else
        {
            if (tp_z > self.origin_z + 24 && !self.ar_liftwait)
            {
                to = tp - self.origin;
                to_z = 0;
                if (vlen (to) < 80 && (self.flags & FL_ONGROUND) && time > self.ar_nextjump)
                {
                    self.ar_jump = 1;
                    self.ar_nextjump = time + 0.8;
                }
            }
            // integrate the movement heading on ar_moveyaw, not on
            // facing: corner pre-aim below may point the eyes away
            // from the travel line, and the walk must not follow them
            diff = want - self.ar_moveyaw;
            while (diff > 180)  diff = diff - 360;
            while (diff < -180) diff = diff + 360;
            turn = AR_TURNRATE * frametime;
            if (diff > turn)        diff = turn;
            else if (diff < -turn)  diff = -turn;
            self.ar_moveyaw = self.ar_moveyaw + diff;
            self.angles_y = self.ar_moveyaw;

            // corner pre-aim (OPM slice C): while routed with nobody
            // in sight, look at the node AFTER the steering target â€”
            // players look through the corner they are about to
            // round, not down their own velocity. Facing only.
            if (self.ar_mode == 2 && self.ar_enemy == world
                && self.ar_node != world && self.ar_door == world)
            {
                nx = Argus_GetNext (self.ar_node, self);
                if (nx != world)
                {
                    to = nx.origin - self.origin;
                    to_z = 0;
                    if (vlen (to) > 60)
                        self.angles_y = vectoyaw (to);
                }
            }
        }
    }
    else
    {
        // wandering toward a hazard: turn now, not when the wander
        // timer feels like it, or the bot queues at the brink
        if (Argus_MoveHazard (self.angles_y, 48))
        {
            self.ar_wanderturn = time + 1 + random () * 2;
            self.angles_y = self.angles_y + 120 + random () * 120;
        }
        else if (time > self.ar_wanderturn)
        {
            self.ar_wanderturn = time + 1 + random () * 2;
            self.angles_y = self.angles_y + (random () - 0.5) * 120;
        }
        self.ar_moveyaw = self.angles_y;
    }

    while (self.angles_y < 0)   self.angles_y = self.angles_y + 360;
    while (self.angles_y > 360) self.angles_y = self.angles_y - 360;

    // ---- stall detection ----
    if (time > self.ar_nextstall)
    {
        self.ar_nextstall = time + 0.7;
        if (vlen (self.origin - self.ar_lastpos) < 12 && !fighting
            && !self.ar_liftwait && !self.ar_hoplift)
        {
            self.ar_stalls = self.ar_stalls + 1;
            self.ar_stallrun = self.ar_stallrun + 1;
            Argus_Event ("stall");
            // diagnostic: what was the routed steering target?
            if (self.ar_mode == 2 && self.ar_node != world)
            {
                dprint ("ARGEVT ");
                dprint (self.netname);
                dprint (" stallnode ");
                dprint (vtos(self.ar_node.origin));
                dprint ("\n");
            }
            if (self.flags & FL_ONGROUND)
                self.ar_jump = 1;
            self.angles_y = self.angles_y + 120 + random () * 120;
            if (self.ar_stallrun < 2)
            {
                self.ar_node = world;
                self.ar_pending = 1;
                self.ar_mode = 0;
            }
            else
            {
                if (Argus_GoalOK (self.ar_goal))
                {
                    self.ar_goal.ar_claimer = self;
                    self.ar_goal.ar_claimtime = time;
                }
                self.ar_goal = world;
                self.ar_node = world;
                self.ar_pending = 0;
                self.ar_mode = 0;
                self.ar_stallrun = 0;
                // wander for a moment before re-planning: immediate
                // re-goaling kept steering wedged bots straight back
                // into the same corner (the displaced-off-a-hop trap)
                self.ar_nextai = time + 1.5;
            }
        }
        else if (vlen (self.origin - self.ar_lastpos) >= 12)
            self.ar_stallrun = 0;
        self.ar_lastpos = self.origin;
    }

    if (time > self.ar_nextlog)
    {
        self.ar_nextlog = time + 0.5;
        Argus_Telemetry ();
    }
};

// ---------------------------------------------------------------- driver

void() Argus_FrameAll =
{
    local entity b, oself;
    local float refresh;

    // freeze with everyone else at match end; stock CheckRules also
    // only watches human frags, so a bot reaching the fraglimit has
    // to end the game itself (done per bot in the loop below)
    if (intermission_running)
        return;

    // stock CheckRules runs on real client frames only, so a headless
    // botmatch never honours timelimit (StartFrame keeps the global
    // fresh from the cvar; fraglimit is tested per bot below)
    if (timelimit > 0 && time >= timelimit)
        NextLevel ();

    Argus_Nav_Frame ();

    // rebroadcast names and frags every few seconds so clients that
    // connect after bot spawn still get scoreboard entries
    refresh = 0;
    if (time > argus_nextnames)
    {
        argus_nextnames = time + 5;
        refresh = 1;
    }

    b = argus_bots;
    while (b != world)
    {
        oself = self;
        self = b;

        if (self.health <= 0)
        {
            if (time > self.ar_respawntime)
                Argus_Respawn ();
        }
        else
        {
            Argus_AI ();
            Argus_Physics ();
        }

        if (self.frags > self.ar_lastfrags && self.health > 0)
        {
            // a kill re-opens the shopping list (Shane's review): the
            // victim's pack is on the floor right there, and marching
            // on to a stale errand while it despawns is the least
            // human move available. The next maintenance tick
            // re-picks with the pack scored by its contents.
            self.ar_goal = world;

            if (self.ar_nemkills >= 3)
            {
                // vendetta discharged: a kill vents the tilt (OPM)
                self.ar_nemkills = 0;
                Argus_Chat (3);
            }
            else
                Argus_Chat (1);
        }

        if (refresh)
        {
            Argus_ScoreName ();
            Argus_ScoreFrags ();
        }
        else if (self.frags != self.ar_lastfrags)
            Argus_ScoreFrags ();

        if (fraglimit > 0 && self.frags >= fraglimit && !intermission_running)
            NextLevel ();

        self = oself;
        b = b.ar_chain;
    }

    // human tracks (2026-08-20, Shane: "are you able to see what I
    // do? and where I go?" - until now, no). Real clients get the
    // same ARGLOG line as bots at the same cadence, under their own
    // netname: st/gl/mode read zero, hp and frags are real. Every
    // parser is name-agnostic, so the review battery, roam and
    // route tooling see the human as one more track - the reference
    // circuit to compare bots against. Camera flights are skipped:
    // a noclip ghost's trail is not play.
    b = find (world, classname, "player");
    while (b != world)
    {
        if (!b.ar_isbot && (b.flags & FL_CLIENT) && b.health > 0
            && !b.cam_active && time > b.ar_nextlog)
        {
            b.ar_nextlog = time + 0.5;
            oself = self;
            self = b;
            Argus_Telemetry ();
            self = oself;
        }
        b = find (b, classname, "player");
    }
};

// ---------------------------------------------------------------- spawn

void(string bname) Argus_SpawnOne =
{
    local entity bot, spot;
    local entity oself;

    spot = Argus_SpawnSpot ();

    bot = spawn ();
    bot.classname = "player";       // the whole 1.06 machinery now applies
    bot.ar_isbot = 1;
    bot.netname = bname;
    bot.ar_slot = argus_spawncount;
    // claim scoreboard slots from the top of the real client range;
    // slot 0 is left for the host, and no slot at all beats a slot the
    // client will Host_Error on (svc_updatename > MAX_SCOREBOARD)
    bot.ar_clientno = argus_maxclients - 1 - argus_spawncount;
    if (bot.ar_clientno < 1)
        bot.ar_clientno = -1;
    // colormap points software-renderer engines at our fake scoreboard
    // slot's shirt/pants translation. GL-lineage engines (QuakeSpasm
    // included) ignore the value: they key the translation by entity
    // number and only paint entities 1..maxclients, which a spawned
    // bot can never be. There the colours come from the skin field
    // below, backed by the extra skins tools/mdl_skins.py bakes into
    // the installed player.mdl (skin 0 untouched for humans).
    bot.colormap = bot.ar_clientno + 1;
    bot.skin = bot.ar_slot + 1;
    argus_spawncount = argus_spawncount + 1;
    bot.ar_chain = argus_bots;
    argus_bots = bot;

    // capture both model indexes the way PutClientInServer does; they
    // are otherwise only initialised when a human client spawns, and
    // stock code (PlayerDie, powerup model swaps) reads them
    setmodel (bot, "progs/eyes.mdl");
    modelindex_eyes = bot.modelindex;
    setmodel (bot, "progs/player.mdl");
    modelindex_player = bot.modelindex;
    setsize (bot, '-16 -16 -24', '16 16 32');
    setorigin (bot, spot.origin + '0 0 1');
    spawn_tfog (bot.origin);
    spawn_tdeath (bot.origin, bot);
    bot.angles_y = spot.angles_y;
    bot.ar_moveyaw = bot.angles_y;
    bot.ar_lastpos = bot.origin;
    bot.ar_nextstall = time + 2;

    oself = self;
    self = bot;
    Argus_BaseStats ();
    droptofloor ();
    Argus_ScoreName ();
    Argus_ScoreFrags ();
    Argus_Event ("spawned");
    self = oself;
};

string(float idx) Argus_RosterName =
{
    idx = idx % 18;
    if (idx == 0) return "Carmack";
    if (idx == 1) return "Romero";
    if (idx == 2) return "Mr Elusive";
    if (idx == 3) return "Joe Rogan";
    if (idx == 4) return "Trent Reznor";
    if (idx == 5) return "American McGee";
    if (idx == 6) return "Sarge";
    if (idx == 7) return "Thresh";
    if (idx == 8) return "Killcreek";
    if (idx == 9) return "Sandy Petersen";
    if (idx == 10) return "Gabe Newell";
    if (idx == 11) return "Crash";
    if (idx == 12) return "Ranger";
    if (idx == 13) return "Tim Willits";
    if (idx == 14) return "Reap";
    if (idx == 15) return "Omi";
    if (idx == 16) return "Zeus";
    return "Ares";
};

void() Argus_Init =
{
    dprint ("ARGUS init on ");
    dprint (mapname);
    dprint ("\n");

    ar_opm_ears = 1;            // OPM slice B live (hearing + soft FOV)

    // netnames MAY contain spaces since v3.37: the python parsers
    // anchor on the grammar keywords (t / pos / event words) instead
    // of splitting on whitespace. The Rust MCP parser needs the same
    // treatment on Shane's next rebuild; until then spaced names are
    // invisible to it (v3.36 tape: all of Joe Rogan's lines dropped).
    Argus_SpawnOne ("Carmack");
    Argus_SpawnOne ("Romero");
    Argus_SpawnOne ("Joe Rogan");

    remove (self);
};

// ---------------------------------------------------------------- roster

// Runtime add/remove on the FrikBot impulse convention (100 add,
// 102 remove), wired from ImpulseCommands. The cap is the nav
// next-hop slot count (4) or the spare scoreboard rows, whichever
// bites first. Cycles through the homage and legacy roster.
void() Argus_AddBot =
{
    local float cap;
    local string bname;

    cap = argus_maxclients - 1;
    if (cap > 4)
        cap = 4;
    if (argus_spawncount >= cap)
    {
        sprint (self, PRINT_HIGH, "no free bot slots\n");
        return;
    }
    bname = Argus_RosterName (argus_spawncount);
    Argus_SpawnOne (bname);
};

void() Argus_RemoveBot =
{
    local entity b;

    b = argus_bots;
    if (b == world)
    {
        sprint (self, PRINT_HIGH, "no bots to remove\n");
        return;
    }
    if (b.ar_clientno >= 0 && b.ar_clientno >= Argus_HumanCount ())
    {
        // blank the scoreboard row before the entity goes away â€” but
        // never a slot a human has since occupied (Shane's
        // correctness list: five humans plus impulse 102 used to
        // erase the fifth human's TAB row)
        WriteByte (MSG_ALL, SVC_UPDATENAME);
        WriteByte (MSG_ALL, b.ar_clientno);
        WriteString (MSG_ALL, "");
        WriteByte (MSG_ALL, SVC_UPDATEFRAGS);
        WriteByte (MSG_ALL, b.ar_clientno);
        WriteShort (MSG_ALL, 0);
    }
    bprint (PRINT_HIGH, b.netname);
    bprint (PRINT_HIGH, " has left the arena\n");
    if (an_busy && an_bot == b)
        an_busy = 0;                // abort its in-flight route search
    argus_bots = b.ar_chain;
    argus_spawncount = argus_spawncount - 1;
    remove (b);
};
