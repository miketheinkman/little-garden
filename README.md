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

## Pilot scope

Twelve draft lessons for approximately ages 4–6 cover pointer control, physical and onscreen keys, tracing, counting, phonics, a short shared text, and a hands-on counting activity. Parent reports summarize completion and retries. Shared reading and offline activities use family confirmation. These records describe participation and do not establish mastery.

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
