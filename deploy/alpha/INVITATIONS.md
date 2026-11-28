# Invite a parent to the hosted alpha

Run the following in the operator's SSH session after deploying the invitation migration and verifying that the hosted signup page asks for a code. Replace the example address with the invited parent's email.

```sh
sudo docker exec little-garden-alpha-web-1 python manage.py invite_parent parent@example.org
```

The parent receives a link to the registration page and a single-use code valid for seven days. They enter the code, choose a username and password, and sign in with a regular parent account. The invited address becomes the recovery address. Codes are stored as digests. The local home pilot continues to use open signup.

Running the same command again sends a replacement and invalidates the previous code. To withdraw an unused invitation:

```sh
sudo docker exec little-garden-alpha-web-1 python manage.py invite_parent --revoke parent@example.org
```

For the public cutover, first verify the invite gate through Nginx, enable Cloudflare-only HTTPS ingress to the origin, and set Cloudflare to Full (strict). Publish the proxied A record when that path is ready. Verify signup, sign-in, password resets and private-page caching through the public hostname before sending family invitations.

Parents can also request a place at `/request-invite/`. In the private alpha environment, set `GARDEN_INVITE_REQUEST_RECIPIENTS` to the comma-separated staff inboxes and recreate the web container when changing it. Check **Admin dashboard → Invite requests** for every submission. Requests are deduplicated by email. During a burst, automatic reviewer emails pause after 20 accepted notifications in ten minutes. Staff can retry a notification or send the actual invitation from the queue. The command above also marks the matching request as invited.
