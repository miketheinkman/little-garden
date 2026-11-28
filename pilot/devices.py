"""Parent-approved, proof-of-possession login to an individual learner app."""
import base64
import binascii
import hashlib
import hmac
import secrets
from uuid import UUID
from datetime import timedelta

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, utils
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.http import FileResponse, Http404, JsonResponse
from django.middleware.csrf import rotate_token
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .models import Learner, LearnerDevice


def digest(code):
    return hashlib.sha256(code.replace("-", "").strip().upper().encode()).hexdigest()


@login_required
@never_cache
@require_http_methods(["GET","POST"])
def devices(request, pk):
    child = get_object_or_404(Learner, parent=request.user, pk=pk)
    context = {"child":child, "devices":child.devices.order_by("label"), "now":timezone.now()}
    if request.method == "POST":
        if request.POST.get("action") == "revoke":
            try:
                device_id = UUID(request.POST.get("device",""))
            except ValueError as exc:
                raise Http404 from exc
            device = get_object_or_404(child.devices, pk=device_id)
            device.delete()
            return redirect("devices", pk)
        label = request.POST.get("label","").strip()
        if not label or len(label) > 60:
            context["error"] = "Give the device a name of up to 60 characters."
        elif not request.is_secure() and request.get_host().split(":")[0] not in {"localhost","127.0.0.1"}:
            context["error"] = "Open Little Garden over HTTPS to issue a setup code."
        else:
            code = base64.b32encode(secrets.token_bytes(10)).decode()
            device = child.devices.create(label=label, code_digest=digest(code), expires=timezone.now()+timedelta(minutes=15))
            context.update(code="-".join(code[n:n+4] for n in range(0,len(code),4)),
                           link=request.build_absolute_uri(f"/g/{device.pk}/"))
    return render(request,"devices.html",context)


def current_device(request):
    return get_object_or_404(LearnerDevice, pk=request.garden_device, learner__parent__is_active=True,
                             expires__gt=timezone.now())


@require_GET
@ensure_csrf_cookie
def launch(request):
    available = LearnerDevice.objects.filter(pk=request.garden_device, learner__parent__is_active=True,
                                             expires__gt=timezone.now()).values_list("code_digest",flat=True).first()
    return render(request,"learner_launch.html",{"available":available is not None,"pending":bool(available)})


@require_GET
def worker(request):
    return FileResponse((settings.BASE_DIR / "static/learner-worker.js").open("rb"),content_type="text/javascript")


@require_GET
def manifest(request):
    start = reverse("device_launch")
    return JsonResponse({"id":start,"start_url":start,"scope":start,"name":"Little Garden",
                         "short_name":"Little Garden","display":"standalone","background_color":"#f7f6ed",
                         "theme_color":"#28563e","icons":[{"src":f"/static/brand/icon-{size}.png",
                         "sizes":f"{size}x{size}","type":"image/png"} for size in (192,512)]},
                        content_type="application/manifest+json")


def issue(device, public_key, now, expiry):
    # Domain-separated application issuer. Only the exact certificate enrolled
    # for this device is trusted, even if another document has the same subject.
    seed = hmac.digest(settings.SECRET_KEY.encode(), b"little-garden/device-issuer/v1", "sha256")
    issuer = ed25519.Ed25519PrivateKey.from_private_bytes(seed)
    cert = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,str(device.pk))]))
            .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,"Little Garden learner devices")]))
            .serial_number(x509.random_serial_number()).public_key(public_key)
            .not_valid_before(now).not_valid_after(expiry)
            .add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]),critical=False)
            .sign(issuer,None))
    return cert.public_bytes(serialization.Encoding.DER)


@require_POST
def pair(request):
    device = current_device(request)
    code = request.POST.get("code","")
    if len(code) > 32 or not device.code_digest or not hmac.compare_digest(device.code_digest,digest(code)):
        return JsonResponse({"error":"Check the setup code or ask your parent for a new one."},status=403)
    try:
        raw = base64.b64decode(request.POST.get("public_key","")[:512],validate=True)
        public_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(),raw)
    except (ValueError,binascii.Error):
        return JsonResponse({"error":"This device could not create its key."},status=400)
    now = timezone.now()
    expiry = now+timedelta(days=365)
    certificate = issue(device,public_key,now,expiry)
    changed = LearnerDevice.objects.filter(pk=device.pk,code_digest=device.code_digest,expires__gt=now).update(
        certificate=certificate,code_digest="",expires=expiry)
    if not changed:
        return JsonResponse({"error":"This code has already been used or expired."},status=403)
    return JsonResponse({"certificate":base64.b64encode(certificate).decode()})


@require_POST
def prove(request):
    device = current_device(request)
    if not device.certificate:
        raise Http404
    salt = "learner-device-login-v1"
    binding = request.session.get("device_binding")
    if "signature" not in request.POST:
        if not binding:
            binding = secrets.token_urlsafe(24)
            request.session["device_binding"] = binding
        token = signing.dumps([str(device.pk),device.generation,binding,secrets.token_hex(16)],salt=salt)
        reply = {"challenge":token}
        if request.POST.get("recover_certificate") == "1":
            # Public material only. This also recovers an interrupted enrollment
            # after the server consumed the code and before the browser saved the certificate.
            reply["certificate"] = base64.b64encode(device.certificate).decode()
        return JsonResponse(reply)
    token = request.POST.get("challenge","")
    denied = JsonResponse({"error":"Could not open this garden. Try again or ask your parent to reconnect it."},status=403)
    try:
        encoded_cert = request.POST.get("certificate","")
        if len(token)>1024 or len(encoded_cert)>2048 or len(request.POST["signature"])!=88:
            return denied
        presented = base64.b64decode(encoded_cert,validate=True)
        if not hmac.compare_digest(presented,bytes(device.certificate)):
            return denied
        identity, generation, session, nonce = signing.loads(token,salt=salt,max_age=90)
        if not binding or (identity,generation,session) != (str(device.pk),device.generation,binding):
            return denied
        sig = base64.b64decode(request.POST["signature"],validate=True)
        if len(sig) != 64:
            return denied
        der = utils.encode_dss_signature(int.from_bytes(sig[:32],"big"),int.from_bytes(sig[32:],"big"))
        cert = x509.load_der_x509_certificate(presented)
        cert.public_key().verify(der, token.encode(), ec.ECDSA(hashes.SHA256()))
    except (signing.BadSignature, ValueError, TypeError, InvalidSignature):
        return denied
    now = timezone.now()
    if not LearnerDevice.objects.filter(pk=device.pk,generation=generation,expires__gt=now).update(
            generation=generation+1,last_used=now):
        return denied
    request.session.flush()
    request.session["device"] = str(device.pk)
    request.session["child"] = device.learner_id
    request.session.set_expiry(12*3600)
    rotate_token(request)
    return JsonResponse({"garden":reverse("home")})
