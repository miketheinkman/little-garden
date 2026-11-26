# Little Garden Deployment Punchlist

Alpha starts with an empty PostgreSQL database. Treat accounts and learning history as durable family records from the first invitation. The home pilot stays independent. A checked local rehearsal is labeled explicitly. Check live-host items only after verifying them on the VPS.

## 1. Infrastructure provisioning

- [x] Identify an existing Ed25519 public key on the operator workstation for provisioning.
- [x] Choose fresh alpha data and keep pilot accounts, progress, feedback, sessions and credentials local.
- [x] Prepare the [first-host setup and private deployment procedure](alpha/README.md).
- [ ] Recover or create the Linode account. Enable MFA, store recovery codes offline, and verify billing notifications.
- [ ] Confirm region, actual plan resources and monthly cost. Keep PostgreSQL and Django on the same 2-vCPU, 8 GB host.
- [ ] Prepare the SSH public key and attach a default-deny cloud firewall at provisioning. Verify the host fingerprint through the provider console.
- [ ] Provision Linode VPS (initial 2-core instance)
- [ ] Configure SSH key authentication
- [ ] Create non-root deployment user and verify key login and sudo in a second session.
- [ ] Verify console recovery, then disable root SSH and password authentication. Test a new session before disconnecting.
- [ ] Configure firewall (restrict SSH; allow HTTP/HTTPS)
- [ ] Enable automatic OS security updates
- [ ] Install Docker and Docker Compose
- [x] Configure restart policies and bounded container logs in Compose.
- [ ] Configure swap and log rotation. Check disk headroom and the security-update reboot window.

## 2. Domain and networking

- [ ] Verify domain ownership, registrar and Cloudflare MFA, recovery codes, auto-renewal and billing contacts.
- [ ] Configure littlegarden.academy DNS
- [ ] Configure Cloudflare proxy
- [ ] Configure reverse proxy (Caddy or Nginx)
- [ ] Provision trusted TLS certificate
- [ ] Configure Cloudflare Full (strict) TLS
- [ ] Redirect HTTP to HTTPS
- [ ] Configure canonical domain and redirects
- [ ] Prevent direct public access to backend and database ports. Verify firewall behavior with Docker running over IPv4 and IPv6.
- [ ] Restrict origin web ingress to the intended proxy path. Overwrite forwarded scheme headers at the trusted proxy.
- [ ] Cache public static assets only. Bypass caching for family pages, co-view, login and resets. Check through the public hostname with two unrelated families.
- [ ] Test certificate renewal and alert before expiry.

## 3. Application deployment

- [x] Prepare private-backend Compose configuration with PostgreSQL and Gunicorn.
- [ ] Deploy it behind the trusted HTTPS origin proxy on the VPS.
- [x] Separate hosted Django settings from the LAN pilot. Require a hostname, signing key, PostgreSQL and authenticated SMTP settings.
- [x] Restrict Docker build inputs and run the web app as a non-root user with a read-only filesystem.
- [ ] Generate production secrets and signing keys
- [ ] Remove development credentials and debug endpoints
- [ ] Create and record the durable alpha database volume on the VPS. Verify its identity on every redeploy.
- [x] Rehearse a fresh PostgreSQL initialization locally. Confirm the app role is limited and a test parent survives recreating both containers.
- [ ] Initialize PostgreSQL and apply migrations on the VPS.
- [x] Package curriculum and Piper recordings in the application image.
- [ ] Verify spoken directions, word clips, artwork and CSS through the public hostname. Publish the running release’s source link and curriculum attribution.
- [ ] Create initial administrator account
- [x] Add an isolated alpha backend rehearsal to GitHub Actions.
- [ ] Configure automated deployment from tested Git releases. Protect deploy credentials and verify the deployed image version.
- [ ] Run migrations once per release and verify application readiness before switching traffic.
- [ ] Rehearse rollback across a schema change. Account for answers saved after deployment before restoring any older database.
- [ ] Verify application survives VPS reboot

## 4. Transactional email

- [ ] Test outbound mail connectivity from the Linode and request an SMTP unblock if needed.
- [ ] Create SES, Resend or equivalent account
- [ ] Verify sending domain
- [ ] Configure SPF, DKIM and DMARC
- [ ] Request production sending access if required
- [ ] Configure noreply sender
- [ ] Configure support email forwarding
- [ ] Implement parent email verification at enrollment.
- [x] Implement parent password reset in the pilot.
- [ ] Test a real reset email from production with the canonical HTTPS link, expiry and single use. Verify opt-out behavior for feedback email.
- [ ] Configure bounce and complaint handling
- [ ] Test delivery to Gmail, Outlook and Yahoo

## 5. Security and privacy

- [ ] Before recruiting, map data sent to hosting, DNS/CDN, mail, monitoring and backup providers. Record purposes, retention and deletion windows.
- [ ] Review COPPA applicability, parental notice and consent requirements. Document the decision before collecting alpha family data.
- [ ] Publish privacy policy
- [ ] Publish terms of service
- [ ] Enforce parent-controlled account registration
- [ ] Minimize collection of children's personal information
- [ ] Verify family-to-family data isolation
- [ ] Verify authorization on every protected API endpoint
- [x] Verify secure session and CSRF cookies, canonical host enforcement, and HTTPS redirects in the isolated backend rehearsal.
- [ ] Verify session expiry and the same HTTP protections through the hosted proxy.
- [ ] Configure CSRF protection where applicable
- [ ] Configure authentication and API rate limiting
- [ ] Verify password hashing
- [ ] Implement account and child data deletion, including how deletions are honored after a backup restore.
- [ ] Implement and verify parent access to a usable family data export.
- [ ] Inspect proxy logs, app errors, diagnostics and reporting vendors for reset tokens, emails, typed answers, drawings and feedback text. Exclude them.
- [ ] Protect privileged app and provider accounts with MFA and test recovery. Schedule expired-session cleanup.
- [ ] Run dependency and container vulnerability scans

## 6. Backups and disaster recovery

- [ ] Agree on acceptable data loss and downtime, assign an incident owner, and verify the alert contact.
- [ ] Before the first invitation, schedule automated PostgreSQL backups.
- [ ] Back up uploaded assets and persistent application data
- [ ] Configure encrypted offsite backup storage
- [ ] Configure backup retention policy
- [ ] Before the first invitation, restore onto a separate instance, measure recovery time, and verify parent login, progress, assignments, feedback and future writes. Record the date and repeat the drill.
- [ ] Configure backup failure alerts
- [ ] Document complete server rebuild, access to backup keys during an outage, how to pause enrollment, revoke sessions and contact families.

## 7. Monitoring and performance

- [ ] Configure external uptime monitoring
- [ ] Monitor CPU, RAM, disk and network utilization
- [ ] Monitor database connections and slow queries
- [ ] Monitor API latency and error rates
- [ ] Configure application error reporting
- [ ] Configure resource exhaustion alerts
- [ ] Run load tests against production-equivalent infrastructure using disposable families. Record the 3,000-entry co-view cache, worker count, direct/relay ratio, latency and saved attempts.
- [ ] Verify performance degradation and recovery under load
- [ ] Configure hosting and email spending alerts

## 8. Client compatibility

- [ ] Test Android Chrome
- [ ] Test iPhone and iPad Safari
- [ ] Test desktop Chrome, Firefox and Edge
- [ ] Test touchscreen interactions
- [ ] Test small-screen and large-screen activity restrictions
- [ ] If installed or offline use is planned, verify the PWA manifest and installability after closed alpha.
- [ ] With PWA delivery, verify service worker updates and household cache isolation on shared devices.
- [ ] Test audio playback and browser permissions
- [ ] Disconnect immediately after a correct answer. Reconnect and verify exactly one saved attempt and the right next question.
- [ ] Test local direct co-view, cellular relay, multiple workers, and reconnection after a restart.

## 9. Closed-alpha preparation

- [ ] Implement invitation-only registration
- [ ] Create alpha tester onboarding instructions
- [ ] Add visible alpha designation
- [x] Add in-app feedback submission, exact-round replay and reopening.
- [ ] Verify the full feedback loop through the hosted origin with a disposable family.
- [ ] Attach activity and device context to bug reports without unnecessary personal data
- [ ] Create known-issues page
- [ ] Establish bug and feature request backlog
- [ ] Create test accounts with representative skill levels
- [ ] Test complete parent and child onboarding flow
- [ ] Test assignment creation and completion
- [ ] Test adaptive difficulty and progress persistence
- [ ] Test parental reporting accuracy

## 10. Alpha launch

- [ ] On the public domain, accept an invite, reset a password, schedule and finish a watched lesson, interrupt connectivity, verify history and rehearse restoration.
- [ ] Recruit 5–10 homeschool families
- [ ] Include children across intended age and skill ranges
- [ ] Distribute invitations and onboarding instructions
- [ ] Explain alpha limitations, retention, export and deletion. Plan for continued family access to progress as the service moves toward beta.
- [ ] Monitor initial registration and onboarding
- [ ] Collect feedback after first few sessions
- [ ] Collect feedback after two weeks
- [ ] Prioritize usability blockers over new features
- [ ] Review infrastructure utilization
- [ ] Determine readiness for expanded beta
