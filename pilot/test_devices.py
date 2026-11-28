import base64
import json
from datetime import timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone
from .models import Learner, LearnerDevice


class DeviceTests(TestCase):
    def setUp(self):
        self.parent = get_user_model().objects.create_user("parent")
        self.child = Learner.objects.create(parent=self.parent,nickname="Fern")
        self.client.force_login(self.parent)
        self.manage = f"/children/{self.child.pk}/devices/"
        resp = self.client.post(self.manage,{"label":"Tablet"},secure=True)
        self.code = resp.context["code"]
        self.device = self.child.devices.get()
        self.start = f"/g/{self.device.pk}/"
        self.key = ec.generate_private_key(ec.SECP256R1())

    def pair(self,code=None):
        key = self.key.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)
        return self.client.post(self.start+"pair/",{"code":code or self.code,"public_key":base64.b64encode(key).decode()},secure=True)

    def challenge(self):
        return self.client.post(self.start+"prove/",secure=True).json()["challenge"]

    def proof(self,challenge,key=None):
        sig = (key or self.key).sign(challenge.encode(),ec.ECDSA(hashes.SHA256()))
        a,b = utils.decode_dss_signature(sig)
        self.device.refresh_from_db()
        return {"challenge":challenge,"certificate":base64.b64encode(self.device.certificate).decode(),"signature":base64.b64encode(a.to_bytes(32,"big")+b.to_bytes(32,"big")).decode()}

    def test_pair_prove_and_revoke(self):
        self.assertEqual(self.pair("wrong").status_code,403)
        self.assertEqual(self.pair().status_code,200)
        self.assertEqual(self.pair().status_code,403)
        self.device.refresh_from_db()
        self.assertEqual(x509.load_der_x509_certificate(self.device.certificate).public_key().public_numbers(),
                         self.key.public_key().public_numbers())
        token = self.challenge()
        self.assertEqual(self.client.post(self.start+"prove/",self.proof(token,ec.generate_private_key(ec.SECP256R1())),secure=True).status_code,403)
        self.assertEqual(self.client.post(self.start+"prove/",{**self.proof(token),"certificate":"AAAA"},secure=True).status_code,403)
        response = self.client.post(self.start+"prove/",self.proof(token),secure=True)
        self.assertEqual(response.json()["garden"],self.start+"garden/")
        self.assertEqual(response.cookies["lg_app_session"]["path"],self.start)
        self.assertContains(self.client.get(self.start+"garden/",secure=True),"Fern’s garden")
        self.assertEqual(self.client.post(self.start+"prove/",self.proof(token),secure=True).status_code,403)
        self.assertContains(self.client.get("/",secure=True),"Family garden")
        self.assertEqual(self.client.get(self.start+"children/add/",secure=True).status_code,404)
        self.client.post(self.manage,{"action":"revoke","device":self.device.pk},secure=True)
        self.assertEqual(self.client.get(self.start+"garden/",secure=True).url,self.start)
        self.assertEqual(self.client.post(self.start+"prove/",secure=True).status_code,404)

    def test_expiry_binding_ownership_and_csrf(self):
        stranger = get_user_model().objects.create_user("elsewhere")
        other = Client()
        other.force_login(stranger)
        self.assertEqual(other.post(self.manage,{"action":"revoke","device":self.device.pk},secure=True).status_code,404)
        strict = Client(enforce_csrf_checks=True)
        self.assertEqual(strict.post(self.start+"pair/",secure=True).status_code,403)
        self.pair()
        payload = self.proof(self.challenge())
        self.assertEqual(other.post(self.start+"prove/",payload,secure=True).status_code,403)
        LearnerDevice.objects.filter(pk=self.device.pk).update(expires=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.client.post(self.start+"prove/",payload,secure=True).status_code,404)

    def test_pending_and_install_metadata(self):
        self.assertEqual(self.client.get(self.start).status_code,403)
        page = self.client.get(self.start,secure=True)
        self.assertContains(page,"One-time setup code")
        self.assertNotContains(page,self.code)
        self.assertNotContains(page,self.child.nickname)
        manifest = self.client.get(self.start+"manifest.webmanifest",secure=True)
        data = json.loads(manifest.content)
        self.assertEqual([data[k] for k in ("id","scope","start_url")],[self.start]*3)
        self.assertEqual(self.client.get(self.start+"garden/",secure=True).url,self.start)
