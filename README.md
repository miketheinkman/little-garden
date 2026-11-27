# Little Garden

A free, donation-supported homeschool web app. Every lesson, learner profile, planning tool, and progress report on the official service is free. Donations are optional and unlock no features.

For the hosted alpha, see the [deployment punchlist](deploy/ALPHA-PUNCHLIST.md) and [first-host setup](deploy/alpha/README.md).

## Try the family pilot on Linux

With Python 3.10+ and its venv module installed, run these commands from the checkout.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver
```

Open http://127.0.0.1:8000/ and create a parent account. Add a learner nickname, queue a few lessons, and open the learner’s garden. This signs the adult out on that browser. Sign back in to change learners, move work to the front of a queue, or review the last seven days. Finished lessons and partially completed steps survive a browser restart on the server. For a first session, try Ladybug lookout, Meet the letter keys, and Five real beans.

### Start the home-network pilot at boot

On a Linux host with systemd, choose the home network interface from `ip -brief -4 address`. The example uses `wlp3s0`. After setting up the checkout and database above, run these commands from the checkout as the account that owns it.

```sh
mkdir -p ~/.local/share ~/.config/systemd/user
ln -s "$PWD" ~/.local/share/little-garden-pilot
install -m 0644 deploy/little-garden@.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now little-garden@localhost little-garden@wlp3s0
loginctl enable-linger "$USER"
```

Open `http://127.0.0.1:8137/` on the host or use its home-network IPv4 address on port 8137 from another device. The Wi-Fi service retries until the selected interface has a private IPv4 address. The loopback service works offline. Both use the checkout’s database, saved mail settings and local secret. This HTTP setup is for a trusted home network. For status, run `systemctl --user status little-garden@localhost little-garden@wlp3s0`. After code updates and migrations, restart both with `systemctl --user restart little-garden@localhost little-garden@wlp3s0`.

Accounts with dashboard access can open **Admin dashboard → Technical** for host CPU, memory, disk space, uptime, unexpired sessions, accounts, and aggregate lesson usage. Returning families practiced on at least two distinct local dates in the last 30 days. The seven-day chart counts rounds with every step answered. Refresh the snapshot for current figures.

## Pilot scope

Eighty-six draft lessons and three placement check-ins for approximately ages 4–8 are grouped by subject and adult involvement. The lesson library filters by subject, adult involvement, difficulty tier, and fit for the selected learner. Open the tier key for the meaning of each label, preview any step, and assign an activity. Preview attempts leave learner progress untouched. Adding an activity removes it from that learner’s available shelf. **Add all** queues the current filtered selection. Parents can choose one of nine illustrated lesson themes per learner on the family dashboard. The setting changes the lesson’s objects, examples, and artwork while keeping the same skills and scoring. Queued lessons take the selected theme when first opened, and started lessons retain it through completion. Activities include steering a winding trail, filling a berry basket, typing garden signs, reading short scenes, and investigating shadows together. Parent reports summarize completion and retries. Shared reading and offline activities use family confirmation. These records describe participation and do not establish mastery.

Django renders household, planner, and learner screens. Small browser activities handle keyboard input, pointer paths, and optional spoken instructions. Hear directions and Hear the word play local Piper recordings at the family-tested pace. Recordings follow the displayed prompt and word across themes and variations. If a recording cannot play, the written directions or target word stay available and the button can retry. The local pilot uses SQLite. Keep the database, local secret, and backups private. The development server is intended for local use.

Each learner has a **Play directions automatically** setting in the family garden. During child play, enabled lessons read each new question aloud and follow listening prompts with the target word, number, or animal call when available. In Pip’s independent story lesson, the recording includes the passage before the question. The speaker and headphones replay recordings on demand. Browsers that require a gesture highlight the sound button to tap. Parent previews and co-view remain quiet unless the parent requests playback in preview.

Run checks with `.venv/bin/python manage.py test`. Curriculum lives in `content/lessons.json`. Keep published lesson IDs immutable and add a new version when revising a lesson used by families.

The picture and listening activities include holiday clues and traditions, color sorting, same and different, spoken numerals, number and alphabet dot trails, addition and subtraction within ten, U.S. coins and bills, size and position comparisons, and real-life versus imaginary scenarios. Each has five questions per round and 320 repeatable round variations.

## Next milestones

1. Observe families using the full queue and collect educator feedback on lessons, accessibility, and learning evidence.
2. Before hosted enrollment, implement retention, export and deletion workflows, parental consent as applicable, and offsite PostgreSQL backups. Verify restoration and the hosted deployment on the VPS. Expand reviewed sequences toward ages 7–8 after the family workflow is tested.
## Sandbox donations

The mission page supports two Stripe-hosted Payment Links. In the same Stripe sandbox, create a one-time price and a monthly recurring price, then create a separate Payment Link for each. Stripe hosts the checkout and confirmation and records the payment or subscription. Little Garden sends no family profile or lesson data.

Set `GARDEN_STRIPE_TEST_ONE_TIME_LINK` and `GARDEN_STRIPE_TEST_MONTHLY_LINK` to the respective public URLs. Use plain sandbox links starting with `https://buy.stripe.com/test_` or `https://donate.stripe.com/test_`. The Linux pilot service reads these settings from `~/.config/little-garden/donations.env`, one `NAME=value` per line. After updating an existing service installation, reinstall the unit as described above, reload systemd and restart the pilot listeners. The page can display either configured option individually. Child sessions do not see the donation section.

For an account-level check, use Stripe’s test Visa on each checkout and verify a successful one-time payment and an active monthly subscription with a paid first invoice in the same sandbox. [Stripe test cards](https://docs.stripe.com/testing)

## Licensing

Application code, templates, styles, and scripts are licensed under [AGPL-3.0-only](LICENSE). Original curriculum and media under `content/`, the milestone artwork under `static/brand/`, the lesson recordings under `static/phonics/`, and the activity sounds under `static/sounds/` are licensed under [CC BY-SA 4.0](LICENSES/CC-BY-SA-4.0.txt). Attribute original lessons to Little Garden contributors, identify changes, and include the license when redistributing them. The Ogg Vorbis lesson recordings use Piper’s en_US-lessac-medium voice. Earlier WAV word clips use Flite’s CMU US SLT voice. Dependencies keep their own licenses. These public grants cover project materials; private family records are outside their scope.

Third parties may host the project commercially under the applicable licenses. The official service’s donation policy is independent of those permissions.

## Parent password recovery

New parents enter a recovery email at signup. Existing parents can add one from Family garden while signed in. Use **Forgot password?** at parent sign-in to request a single-use link, valid for one hour. For a legacy parent who has lost the password and has no recovery email, the Linux host owner can use Django’s interactive `manage.py changepassword USERNAME` command from the project environment.

For inbox delivery, configure your SMTP provider on the server using `GARDEN_SMTP_HOST`, `GARDEN_SMTP_PORT` (default 587), `GARDEN_SMTP_USER`, `GARDEN_SMTP_PASSWORD`, and `GARDEN_FROM_EMAIL`, then restart the app. STARTTLS is enabled by default. Without SMTP, reset messages are written to the host-private, Git-ignored `.private-mail/` folder. Keep it private and clear expired messages. A LAN reset URL works from the home network while the host is running.

For a local Gmail sender with Google 2-Step Verification and app passwords enabled, run `.venv/bin/python manage.py setup_gmail SENDER_ADDRESS TEST_RECIPIENT` in a private terminal. The command prompts for the app password without displaying it, sends a test message, then saves the working credential in the owner-only file `.private-mail/gmail.json`. The pilot uses it on subsequent sends. Removing that file restores the private outbox fallback. Revoke the app password at Google when retiring the sender.

## Planning ahead

Select **Schedule** beside a queue button or **Schedule all** for the filtered library selection. The lesson planner also opens this same library and its subject, adult involvement, tier, and fit filters. Schedule one date, every day, weekdays, or selected days of the week, with an optional last date. **Schedule this round** in a lesson preview preserves the displayed first round and any chosen letters. Later sessions draw fresh rounds. The weekly view shows upcoming dates alongside scheduled sessions already in the queue or completed. Parents can edit or cancel upcoming dates separately from assignments already in the queue.

Open **Family calendar** from the parent dashboard for a Monday-first month of scheduled lessons across all children. Select a child to filter, or select a date to see each lesson and its queue status. Current and future dates open the lesson library with that date selected. Saving a schedule returns to the calendar. Past dates show scheduled sessions that reached the queue.

The queue makes due lessons available when the family next opens it, using the pilot’s local calendar date. A one-time lesson waits for the learner even after a missed day. After time away, each recurring plan offers its latest due session. It keeps one unfinished session from that plan at a time.

## Practice rounds

Each new run selects distinct problems. Keyboard hunts use five different keys. The introductory counting activities use three different quantities. Addition treats reversed operands as the same problem. A small target set ends when its distinct problems run out. Retrying a question or resuming a started round keeps the same problem on screen.

Parents can remove one copy of an assignment from a learner’s queue, including after it has started. Previously scored answers remain in the skill history. A learner can skip any question, including a check-in question. Skipping adds no answer score or retry. The weekly record lists answered and skipped steps separately.

Each learner’s Assignment history opens from the family garden or lesson library. Filter by month, lesson, and status to find earlier rounds. Expand **Question details** to see numbered submissions, correct and incorrect responses, skips, and keyboard pace where measured. Scored drawings show overlap and observed activities show completion. Older rounds display the evidence available from that date. A library card’s last-completed date links to that lesson’s history and counts rounds finished with every step answered. The pilot uses Central time for calendar dates; other hosts can set `GARDEN_TIME_ZONE` to their local time zone. Older assignments retain their recorded finish or removal dates.

The first assignment uses the original round. When the lesson comes up again, the planner samples unused rounds and favors those with fewer questions in common with the child’s three most recent assignments for that lesson. After using every round, it draws from the least recently used ones. Parents can browse in order, choose **Shuffle round**, or assign the exact preview on screen. Assignments store their questions and answers together so retries and resumed sessions are consistent. Older assignments continue using their original version. Stories and guided investigations keep related scenes, materials, predictions and outcomes together. Letter activities draw from A–Z, digit activities from 0–9, and arithmetic within ten includes empty groups. Route puzzles have 40 five-board rounds each, with different routes, decision positions and directions. Sound Memory includes 40 melody patterns. Practice stays within the original skill. Preview feedback records the round and step.

Art & drawing includes coloring, reflection, and creative drawing on a 32-by-24 grid. Coloring measures the fraction of the target filled and the fraction of painted cells outside it. Mirror match measures intersection over union with the reflected reference. These are descriptive practice measures; any nonempty valid picture completes the step. Creative drawings receive no numeric score. Finished child assignments store the picture in the family database and display it in the parent’s weekly record.

Memory games offer five boards each for letters and words, shapes and numbers, or sounds. A missed pair turns face down after a brief pause. Matched pairs stay visible. The sound cards play recorded counts or short melodies, with optional written clues. Finishing a memory board records participation. Seesaw Balance gives immediate feedback as children move number and animal blocks. The first submitted balance check contributes to number-sense placement.

In Art & drawing, Match the Paint starts with a visible sample and Find That Color gives a spoken target. Paint Mixing Studio lets a child try two paints, see the result, and undo a choice before checking. Each round explores three primary-color pairs and two tints made with white.

The animal activities include identification, completing names, and matching original synthesized animal-call effects. Alphabet Stepping Stones practices letter order. In My Letter Patch, a parent can choose the target letters in preview and queue that exact round. Each selected letter appears once, including when a parent chooses just one or two. Sorting Baskets changes the sorting rule each round and lets children move items before checking. Families can also set an accent color and font per learner in the parent dashboard.

Parents can open **Weekly learning record** from the dashboard or assignment history. The report includes completions, answered and skipped questions, and scored practice for the selected calendar week. Private, dated observations can describe a lesson or the child’s week. Printing or saving the report as a PDF includes observations only when the parent selects that option.

Tracing supports a drag or a sequence of arrow presses along the same path. Sign copying accepts a keyboard or on-screen letter, space, and erase buttons.

### Logic puzzles

Water Works and Train Tracks each have five untimed boards. Children can rotate pieces, place a spare bend, open valves or flip switches, and press Go to see the result. The same boards appear in parent preview and live co-view. Each repeat rotates the map a quarter turn. Board layouts and directions live in `content/route_puzzles.json`.

Light Paths uses movable mirrors to direct a beam. Bridges and Crossings asks children to choose bridge lengths and directions. Delivery Routes uses arrows to collect parcels before reaching the destination. Gears and Motion explores how neighboring gears turn. Gates and Switches links shaped switches to matching gates. Each game offers 40 five-board rounds. The board definitions live in `content/workshop_puzzles.json`.

Children can try as many routes as they like before choosing Continue. Grown-ups can mark when they helped. The progress report counts independent solves, solves with hints, solves with a grown-up, and solves with both. Independent solves contribute to placement in causal reasoning.

## Placement and suggestions

Tiers 1–5 describe local curriculum difficulty within a strand. Three untimed check-ins (number sense, keyboard use and letter sounds) sample increasing difficulty, advancing after each answer. Assign them from the parent dashboard. The **Placement & reviews** link on each child’s dashboard covers all 86 lessons and the three multi-tier checks across 22 skill areas. A parent can queue an initial placement for the exact lesson or schedule it as a review. Answer-based checks advance after the first submitted answer. Art checks use overlap, and puzzles track independent solves and assistance. Parent-observed checks use the actual activity followed by a private, assignment-linked observation. A fully answered check with evidence for each step establishes its baseline. Ordinary practice, incomplete checks, and helped puzzle solves remain visible separately from a complete baseline.

A review is suggested after four weeks, or sooner after eight subsequent fully scored rounds in that skill area. Observation-based checks use the four-week interval. Scheduling a review defaults to every four weeks and supports the planner’s one-time and other repeat options. The calendar, queue, assignment history and weekly record carry the session purpose. When initial placement is scheduled to repeat, later sessions become reviews. Guided arrow mazes and parent-led side identification use observations for placement. Older scores for these activities remain in the assignment timeline. Normal practice still allows retries. The first submitted answer per step supplies one accuracy observation; coloring and mirror tasks use shape overlap. Adult confirmations, guided tracing, simple clicks, and free drawing supply participation records only. Earlier rounds without recorded first responses retain their completion history.

Keyboard lessons and check-ins measure focused time to submit a physical key or typed answer. The parent report shows median seconds per key for correct first responses. After three timed first-try successes, placement considers pace alongside accuracy. The pilot uses a gradual adjustment between five and sixty seconds per key. These are provisional settings. Learners have unlimited time, and a correct answer earns full accuracy credit at any speed.

Each strand’s estimate fits the latest 24 observations, weighting recent ones more heavily and limiting the estimate to one tier above the highest attempted task. The family and learner views plot the most recent 12 scored-round checkpoints on a fixed 1–5 scale. These pilot estimates are provisional. After initial placement, a first-time gain to a higher whole tier in a skill triggers a two-second beanstalk climb on the learner screen and the parent mirror. The reduced-motion view shows the climber at the top. The dated round history shows raw scores and changes for comparable tasks. Suggestions stay within one tier of the current estimate, prioritize practice after difficulty, rotate among strands, and rest a lesson for two weeks following two recent fluent rounds. The parent queue always takes priority. A child can opt into a suggested activity when the parent queue is empty.

### Practice focus and skill details

In **Family garden**, open **Practice focus** beside a learner. Choose a subject for a broad preference, or narrow it to a skill, letters, numbers, operations, colors, shapes or words. Separate focuses can run together and can have different dates, activity weights and context settings. A focus is optional. An empty selection of active focuses uses the original round generator and recommendations.

**Selected targets** previews a short round from eligible questions. **With familiar targets** mixes in review supported by the same skill. A weekly plan proposes five editable days and enters the family calendar when a parent saves it. A recurring assignment can follow future focus changes or keep its settings. Automatic targets use direct evidence to advance. Interests can influence interchangeable pictures without adding assignments or earning credit.

For example, a focus on 5 can produce a basket order for five, a pile of five beside another pile, or ten counters shared between two helpers. Focused baskets and piles support 0–12. Equal sharing uses whole shares and at most twelve counters. A letter focus can bring matching animals into Animal Lookout, with the frequency set by **Use focus in other lesson examples**. Animal recognition supplies the evidence for that activity.

Of the 89 catalog activities, 36 accept specific practice targets, 39 more can use context in their examples, and word blending can use demonstrated sounds in automatic mode. The three multi-tier check-ins keep their standard sampling. Ten motor and logic activities keep their original paths, boards and cues. Linked readings and experiments use whole authored versions so their questions, materials and directions stay together. Existing assignments keep their saved questions.

Open **Skill details**, choose initial placement or review, then expand a subject and skill area. Select an objective to inspect question attempts, parent observations, and available targeted checks. Scores roll up once per question. Historical scores without a reliably frozen question remain broad. “Demonstrated” is a practice estimate using up to six recent independent scores, averaging at least 80% across two or more rounds.

## Capacity testing

The [two-vCPU lesson benchmark](qa/CAPACITY.md) includes measured concurrency, answer latency, memory use, and instructions for repeating the trial with synthetic families.

## Visual review

Install the optional browser tests with `.venv/bin/pip install -r requirements-visual.txt` and `.venv/bin/python -m playwright install chromium`. Run `.venv/bin/python manage.py test` and `.venv/bin/python manage.py test qa.visual`. On Linux with Chrome already installed, you can use `PLAYWRIGHT_CHROME_PATH=/usr/bin/google-chrome .venv/bin/python manage.py test qa.visual` for the browser run.

The suite exercises a disposable family’s parent, child, library, art, feedback, sign-in, and admin screens. It captures 375px and 1200px layouts in both light and dark, checks for horizontal overflow and browser exceptions, and checks theme persistence and device changes. Open the screenshots in `visual-results/` and inspect the screens changed by each feature. GitHub Actions also runs the suites on pushes and pull requests and retains the screenshot artifact for seven days.

## Welcome and brand assets

The signed-out home page opens an illustrated garden. Visit `/welcome/` to replay it from any account. Entry is available throughout the animation and the reduced-motion setting displays the finished scene. The mission page links to the downloadable Book Sprout brand kit, including source SVGs, light and dark wordmarks, PNG icons, a favicon, palette, attribution, and license. Original brand and opening-scene artwork is released under CC BY-SA 4.0.

## Watching a learner live

Choose **Watch live** in the parent’s Family garden. Open each learner’s garden on another device or in a separate browser profile. Choose one learner or **All learners together**. Wide screens tile the selected gardens. A child sees a notice while their garden is being watched.

Co-viewing recreates the visible Little Garden activity, including the prompt, typed answer, basket, tracing path, artwork, and the latest submitted response. The parent view is read-only.

The server matches the signed-in parent with each selected learner. Their browsers try a WebRTC data channel using local host candidates and no external STUN or TURN service. Each tile shows **Live · Direct** or **Live · Server relay**. During matching or after a connection fails, the server carries updates roughly once a second. On a healthy direct connection, drawing and typing updates travel between browsers. The server continues to check household access and supply lesson context and submitted responses. The learner keeps the same connection when answering, skipping, or moving between the queue and lessons. The mirror plays each celebration beside the answered question for two seconds, including when a relay update arrives after the child advances. Browser or Wi-Fi restrictions can keep a tile on the relay.

Leaving the child page or losing its connection causes the live frame to expire after eight seconds. Temporary snapshots are scoped to the household and shared between the two Linux pilot listeners through the user’s private runtime directory. The app does not capture the device screen, camera, microphone, or activity in other tabs.
