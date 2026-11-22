# Little Garden

A free, donation-supported homeschool web app. Every lesson, learner profile, planning tool, and progress report on the official service is free. Donations are optional and unlock no features.

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

## Pilot scope

Twenty-seven draft lessons for approximately ages 4–8 are grouped by subject and adult involvement. Open a learner’s lesson library to filter, preview any step, and assign an activity. Preview attempts leave learner progress untouched. Activities include steering a winding trail, filling a berry basket, typing garden signs, reading short scenes, and investigating shadows together. Parent reports summarize completion and retries. Shared reading and offline activities use family confirmation. These records describe participation and do not establish mastery.

Django renders household, planner, and learner screens. Small browser activities handle keyboard input, pointer paths, and optional spoken instructions. The local pilot uses SQLite. Keep the database, local secret, and backups private. The development server is intended for local use.

Run checks with `.venv/bin/python manage.py test`. Curriculum lives in `content/lessons.json`. Keep published lesson IDs immutable and add a new version when revising a lesson used by families.

## Next milestones

1. Observe families using the full queue and collect educator feedback on lessons, accessibility, and learning evidence.
2. Add adult observations, printable weekly exports, equivalent input options, lesson previews, and account recovery.
3. Before hosted enrollment, implement retention, export and deletion workflows, parental consent as applicable, production settings, PostgreSQL backups and verified restoration. Expand reviewed sequences toward ages 7–8 after the family workflow is tested.

## Licensing

Application code, templates, styles, and scripts are licensed under [AGPL-3.0-only](LICENSE). Original curriculum and media under `content/` are licensed under [CC BY-SA 4.0](LICENSES/CC-BY-SA-4.0.txt). Attribute original lessons to Little Garden contributors, identify changes, and include the license when redistributing them. Dependencies keep their own licenses. These public grants cover project materials; private family records are outside their scope.

Third parties may host the project commercially under the applicable licenses. The official service’s donation policy is independent of those permissions.

## Parent password recovery

New parents enter a recovery email at signup. Existing parents can add one from Family garden while signed in. Use **Forgot password?** at parent sign-in to request a single-use link, valid for one hour. For a legacy parent who has lost the password and has no recovery email, the Linux host owner can use Django’s interactive `manage.py changepassword USERNAME` command from the project environment.

For inbox delivery, configure your SMTP provider on the server using `GARDEN_SMTP_HOST`, `GARDEN_SMTP_PORT` (default 587), `GARDEN_SMTP_USER`, `GARDEN_SMTP_PASSWORD`, and `GARDEN_FROM_EMAIL`, then restart the app. STARTTLS is enabled by default. Without SMTP, reset messages are written to the host-private, Git-ignored `.private-mail/` folder. Keep it private and clear expired messages. A LAN reset URL works from the home network while the host is running.

For a local Gmail sender with Google 2-Step Verification and app passwords enabled, run `.venv/bin/python manage.py setup_gmail SENDER_ADDRESS TEST_RECIPIENT` in a private terminal. The command prompts for the app password without displaying it, sends a test message, then saves the working credential in the owner-only file `.private-mail/gmail.json`. The pilot uses it on subsequent sends. Removing that file restores the private outbox fallback. Revoke the app password at Google when retiring the sender.

## Practice rounds

Parents can remove one copy of an assignment from a learner’s queue, including after it has started. Previously scored answers remain in the skill history. A learner can skip any question, including a check-in question. Skipping adds no answer score or retry. The weekly record lists answered and skipped steps separately.

The first assignment uses the original round. Reassigning a lesson from the library advances from the learner’s most recently assigned round. In preview, browse rounds and assign the exact one on screen. Assignments store their questions and answers together so retries and resumed sessions are consistent. Older assignments continue using their original version. Stories and guided investigations rotate through three authored sequences. Practice activities use repeatable variations within the lesson’s skill and difficulty range. Preview feedback records the round and step.

Art & drawing includes coloring, reflection, and creative drawing on a 32-by-24 grid. Coloring measures the fraction of the target filled and the fraction of painted cells outside it. Mirror match measures intersection over union with the reflected reference. These are descriptive practice measures; any nonempty valid picture completes the step. Creative drawings receive no numeric score. Finished child assignments store the picture in the family database and display it in the parent’s weekly record.

## Placement and suggestions

Tiers 1–5 describe local curriculum difficulty within a strand. Three untimed check-ins (number sense, keyboard use and letter sounds) sample increasing difficulty, advancing after each answer. Assign them from the parent dashboard. A recheck is suggested after four weeks or eight subsequently scored rounds in the strand. Normal practice still allows retries. The first submitted answer per step supplies one accuracy observation; coloring and mirror tasks use shape overlap. Adult confirmations, guided tracing, simple clicks, and free drawing supply participation records only. Earlier rounds without recorded first responses retain their completion history.

Keyboard lessons and check-ins measure focused time to submit a physical key or typed answer. The parent report shows median seconds per key for correct first responses. After three timed first-try successes, placement considers pace alongside accuracy. The pilot uses a gradual adjustment between five and sixty seconds per key. These are provisional settings. Learners have unlimited time, and a correct answer earns full accuracy credit at any speed.

Each strand’s estimate fits the latest 24 observations, weighting recent ones more heavily and limiting the estimate to one tier above the highest attempted task. The family and learner views plot the most recent 12 scored-round checkpoints on a fixed 1–5 scale. These pilot estimates are provisional. The dated round history shows raw scores and changes for comparable tasks. Suggestions stay within one tier of the current estimate, prioritize practice after difficulty, rotate among strands, and rest a lesson for two weeks following two recent fluent rounds. The parent queue always takes priority. A child can opt into a suggested activity when the parent queue is empty.

## Visual review

Install the optional browser tests with `.venv/bin/pip install -r requirements-visual.txt` and `.venv/bin/python -m playwright install chromium`. Run `.venv/bin/python manage.py test` and `.venv/bin/python manage.py test qa.visual`. On Linux with Chrome already installed, you can use `PLAYWRIGHT_CHROME_PATH=/usr/bin/google-chrome .venv/bin/python manage.py test qa.visual` for the browser run.

The suite exercises a disposable family’s parent, child, library, art, feedback, sign-in, and admin screens. It captures 375px and 1200px layouts in both light and dark, checks for horizontal overflow and browser exceptions, and checks theme persistence and device changes. Open the screenshots in `visual-results/` and inspect the screens changed by each feature. GitHub Actions also runs the suites on pushes and pull requests and retains the screenshot artifact for seven days.

## Welcome and brand assets

The signed-out home page opens an illustrated garden. Visit `/welcome/` to replay it from any account. Entry is available throughout the animation and the reduced-motion setting displays the finished scene. The mission page links to the downloadable Book Sprout brand kit, including source SVGs, light and dark wordmarks, PNG icons, a favicon, palette, attribution, and license. Original brand and opening-scene artwork is released under CC BY-SA 4.0.
